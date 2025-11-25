import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .path_utils import resolve_within_root
from .tool_spec import ToolSpec


def _run_git(repo_root: Path, args: List[str]) -> str:
    try:
        completed = subprocess.run(
            ["git"] + args,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return completed.stderr.strip() or f"git {' '.join(args)} failed."
        return completed.stdout.strip() or "(no output)"
    except FileNotFoundError:
        return "git executable not available on this system."
    except Exception as exc:
        return f"Error running git {' '.join(args)}: {exc}"


def _run_git_checked(repo_root: Path, args: List[str]) -> Tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git"] + args,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "git executable not available on this system."
    except Exception as exc:
        return False, f"Error running git {' '.join(args)}: {exc}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    output = stdout or stderr or "(no output)"
    if completed.returncode != 0:
        if not stderr:
            output = f"git {' '.join(args)} failed."
        return False, output
    return True, output


def git_status(repo_root: Path) -> str:
    return _run_git(repo_root, ["status", "--short", "--branch"])


def git_diff(repo_root: Path, diff_target: str = "--stat") -> str:
    args = ["diff"]
    if diff_target.strip():
        args.append(diff_target.strip())
    return _run_git(repo_root, args)


def _format_git_command(args: List[str]) -> str:
    try:
        formatter = shlex.join  # type: ignore[attr-defined]
    except AttributeError:
        formatter = lambda tokens: " ".join(tokens)
    return f"git {formatter(args)}"


def _resolve_repo_file(repo_root: Path, file_path: str) -> Tuple[Path, str]:
    try:
        candidate = resolve_within_root(repo_root, file_path)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    relative = candidate.relative_to(repo_root.resolve())
    return candidate, str(relative)


def _ensure_backup_file(
    repo_root: Path, target: Path, relative_target: str
) -> Tuple[bool, str]:
    backup_path = target.with_name(target.name + ".orig")
    base = repo_root.resolve()
    try:
        backup_relative = str(backup_path.resolve().relative_to(base))
    except ValueError:
        backup_relative = str(backup_path)

    if backup_path.exists():
        return True, f"Backup already exists at '{backup_relative}'."

    try:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
    except OSError as exc:
        return False, f"Failed to create backup file: {exc}"

    return True, f"Copied '{relative_target}' to '{backup_relative}'."


def _commit_files(repo_root: Path, commit_message: str, files: List[str]) -> str:
    message = commit_message.strip()
    if not message:
        return "Provide 'commit_message' describing the changes."

    if files:
        add_args = ["add"] + files
    else:
        add_args = ["add", "-A"]

    run_log = []
    success, output = _run_git_checked(repo_root, add_args)
    run_log.append(f"$ {_format_git_command(add_args)}\n{output}")
    if not success:
        return "GitCommitFiles aborted while staging changes:\n\n" + "\n\n".join(run_log)

    commit_args = ["commit", "-m", message]
    success, output = _run_git_checked(repo_root, commit_args)
    run_log.append(f"$ {_format_git_command(commit_args)}\n{output}")
    if not success:
        return "GitCommitFiles aborted while committing changes:\n\n" + "\n\n".join(run_log)

    return "Changes committed successfully.\n\n" + "\n\n".join(run_log)


def _parse_edit_directives(
    edits: List[Dict[str, Any]]
) -> Tuple[bool, str, List[Tuple[int, str, str]]]:
    directives: List[Tuple[int, str, str]] = []
    if not edits:
        return False, "Provide at least one edit directive.", []

    for idx, entry in enumerate(edits):
        if not isinstance(entry, dict):
            return False, f"Edit entry at index {idx} must be an object.", []

        line_value = entry.get("line")
        try:
            line_no = int(line_value)
        except (TypeError, ValueError):
            return False, f"'line' for edit entry at index {idx} must be an integer.", []
        if line_no <= 0:
            return False, f"'line' for edit entry at index {idx} must be positive.", []

        op_value = entry.get("op")
        if not isinstance(op_value, str) or op_value not in {"+", "-"}:
            return False, f"'op' for edit entry at index {idx} must be '+' or '-'.", []

        text_value = entry.get("text", "")
        if text_value is None:
            text_str = ""
        elif isinstance(text_value, str):
            text_str = text_value
        else:
            text_str = str(text_value)
        text_str = text_str.rstrip("\r\n")

        directives.append((line_no, op_value, text_str))

    return True, "", directives


def _prepare_edit_state(
    repo_root: Path, file_path: str, edits: List[Dict[str, Any]]
) -> Tuple[Optional[Path], Optional[str], Optional[str], List[Tuple[int, str, str]], str]:
    if not file_path.strip():
        return None, None, None, [], "Provide 'file_path' for the file you want to edit."
    if not edits:
        return None, None, None, [], "Provide 'edits' containing at least one directive."
    try:
        target, relative = _resolve_repo_file(repo_root, file_path)
    except ValueError as exc:
        return None, None, None, [], str(exc)
    if not target.exists():
        return None, None, None, [], f"File '{relative}' does not exist."
    if not target.is_file():
        return None, None, None, [], f"Path '{relative}' is not a regular file."

    success, backup_msg = _ensure_backup_file(repo_root, target, relative)
    if not success:
        return None, None, None, [], backup_msg

    ok, error_msg, directives = _parse_edit_directives(edits)
    if not ok:
        return None, None, None, [], error_msg

    return target, relative, backup_msg, directives, ""


def _read_file_lines(target: Path, relative: str) -> Tuple[List[str], bool, str]:
    try:
        original_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return [], False, f"Failed to read '{relative}': {exc}"

    lines = original_text.splitlines()
    had_trailing_newline = original_text.endswith("\n")
    return lines, had_trailing_newline, ""


def _apply_line_directives(
    lines: List[str], directives: List[Tuple[int, str, str]]
) -> Tuple[bool, str, int, int]:
    additions = 0
    removals = 0
    directives.sort(key=lambda item: (-item[0], 0 if item[1] == "-" else 1))

    for line_no, op, content in directives:
        if line_no <= 0:
            return False, f"Line numbers must be positive. Invalid entry: {line_no}.", 0, 0
        index = line_no - 1
        if op == "-":
            if index >= len(lines):
                return (
                    False,
                    f"Cannot remove line {line_no}: file has only {len(lines)} lines.",
                    0,
                    0,
                )
            existing = lines[index]
            if content and existing != content:
                return (
                    False,
                    f"Line {line_no} mismatch for removal.\nExpected: {content}\nFound: {existing}",
                    0,
                    0,
                )
            del lines[index]
            removals += 1
        else:
            if index > len(lines):
                return (
                    False,
                    f"Cannot insert at line {line_no}: file has only {len(lines)} lines.",
                    0,
                    0,
                )
            lines.insert(index, content)
            additions += 1

    return True, "", additions, removals


def _write_updated_file(
    target: Path, relative: str, lines: List[str], had_trailing_newline: bool
) -> str:
    new_text = "\n".join(lines)
    if had_trailing_newline:
        new_text += "\n"

    try:
        target.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return f"Failed to write '{relative}': {exc}"
    return ""


def _edit_file_with_directives(
    repo_root: Path, file_path: str, edits: List[Dict[str, Any]]
) -> str:
    target, relative, backup_msg, directives, error = _prepare_edit_state(
        repo_root, file_path, edits
    )
    if error:
        return error
    assert target is not None and relative is not None and backup_msg is not None

    lines, had_trailing_newline, error = _read_file_lines(target, relative)
    if error:
        return error

    ok, error, additions, removals = _apply_line_directives(lines, directives)
    if not ok:
        return error

    error = _write_updated_file(target, relative, lines, had_trailing_newline)
    if error:
        return error

    return (
        f"{backup_msg}\nApplied {additions} addition(s) and {removals} removal(s) to '{relative}'."
    )



def build_git_tools(project_root: Path, repo_root: Path, base_branch: str) -> List[ToolSpec]:
    _ = base_branch  # retained for compatibility; not needed without patch workflow.
    status_tool = ToolSpec(
        name="GitStatus",
        description="Show the current git status and branch information.",
        parameters={"type": "object", "properties": {}},
        func=lambda _: git_status(repo_root),
    )

    def _diff_tool(args: Dict[str, str]) -> str:
        target = args.get("target", "--stat").strip() or "--stat"
        return git_diff(repo_root, target)

    diff_tool = ToolSpec(
        name="GitDiff",
        description="Run 'git diff'. Provide optional 'target' like '--stat' or '-- path/to/file'.",
        parameters={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Extra argument passed to git diff (default '--stat').",
                }
            },
        },
        func=_diff_tool,
    )

    def _edit_tool(args: Dict[str, Any]) -> str:
        file_path_value = args.get("file_path") or ""
        file_path = str(file_path_value)
        edits_value = args.get("edits")
        if not isinstance(edits_value, list):
            return "'edits' must be a list of directive objects."
        return _edit_file_with_directives(project_root, file_path, edits_value)

    edit_tool = ToolSpec(
        name="GitEditFile",
        description=(
            "Apply targeted edits to a file using structured directives. "
            "Automatically writes '<file>.orig' before modifying the original."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the repository file to modify.",
                },
                "edits": {
                    "type": "array",
                    "description": (
                        "List of directive objects that specify a line number, an operation ('+' or '-'), "
                        "and optional text when inserting or validating removals. Use '-' to remove the "
                        "specified line and '+' to insert the provided text before that line number. "
                        "Append by targeting the total line count + 1."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "line": {
                                "type": "integer",
                                "description": "1-indexed line number where the directive applies.",
                            },
                            "op": {
                                "type": "string",
                                "enum": ["+", "-"],
                                "description": "Operation to perform: '+' insert, '-' remove.",
                            },
                            "text": {
                                "type": "string",
                                "description": "Text to insert or to match when removing a line.",
                            },
                        },
                        "required": ["line", "op"],
                    },
                },
            },
            "required": ["file_path", "edits"],
        },
        func=_edit_tool,
    )

    def _commit_tool(args: Dict[str, str]) -> str:
        commit_message = args.get("commit_message") or ""
        files_arg = args.get("files")
        files: List[str] = []
        if files_arg is None:
            files = []
        elif isinstance(files_arg, list):
            files = [str(item) for item in files_arg if str(item).strip()]
        else:
            return "'files' must be an array of relative file paths."
        return _commit_files(repo_root, commit_message, files)

    commit_tool = ToolSpec(
        name="GitCommitFiles",
        description=(
            "Stage specified files (or everything if omitted) and create a commit with the provided message."
        ),
        parameters={
            "type": "object",
            "properties": {
                "commit_message": {
                    "type": "string",
                    "description": "Commit message describing the changes.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of file paths to pass to 'git add'. If omitted, 'git add -A' is used.",
                },
            },
            "required": ["commit_message"],
        },
        func=_commit_tool,
    )

    return [
        status_tool,
        diff_tool,
        edit_tool,
        commit_tool,
    ]
