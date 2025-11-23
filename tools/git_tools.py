import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from .tool_spec import ToolSpec

LINE_DIRECTIVE_HEADER = re.compile(r"^\s*(\d+)\s*([+-])")


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
    candidate = Path(file_path.strip()).expanduser()
    base = repo_root.resolve()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        raise ValueError("File path must stay within the repository root.")
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


def _parse_edit_directives(edit_script: str) -> Tuple[bool, str, List[Tuple[int, str, str]]]:
    directives: List[Tuple[int, str, str]] = []
    for raw_line in edit_script.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        header = LINE_DIRECTIVE_HEADER.match(line)
        if not header:
            return False, f"Could not parse edit directive '{raw_line}'. Expected 'LINE +/- content'."
        line_no = int(header.group(1))
        op = header.group(2)
        remainder = line[header.end():]
        if remainder.startswith((" ", "\t")):
            if len(remainder) == 1:
                remainder = ""
            elif remainder[1] not in (" ", "\t"):
                remainder = remainder[1:]
        directives.append((line_no, op, remainder))
    if not directives:
        return False, "Provide at least one non-empty edit directive."
    return True, "", directives


def _edit_file_with_directives(repo_root: Path, file_path: str, edit_script: str) -> str:
    if not file_path.strip():
        return "Provide 'file_path' for the file you want to edit."
    if not edit_script.strip():
        return "Provide 'edits' containing line-number directives."
    try:
        target, relative = _resolve_repo_file(repo_root, file_path)
    except ValueError as exc:
        return str(exc)
    if not target.exists():
        return f"File '{relative}' does not exist."
    if not target.is_file():
        return f"Path '{relative}' is not a regular file."

    success, backup_msg = _ensure_backup_file(repo_root, target, relative)
    if not success:
        return backup_msg

    ok, error_msg, directives = _parse_edit_directives(edit_script)
    if not ok:
        return error_msg

    try:
        original_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Failed to read '{relative}': {exc}"

    lines = original_text.splitlines()
    had_trailing_newline = original_text.endswith("\n")

    directives.sort(key=lambda item: (-item[0], 0 if item[1] == "-" else 1))

    additions = 0
    removals = 0
    for line_no, op, content in directives:
        if line_no <= 0:
            return f"Line numbers must be positive. Invalid entry: {line_no}."
        index = line_no - 1
        if op == "-":
            if index >= len(lines):
                return f"Cannot remove line {line_no}: file has only {len(lines)} lines."
            existing = lines[index]
            if content and existing != content:
                return (
                    f"Line {line_no} mismatch for removal.\nExpected: {content}\nFound: {existing}"
                )
            del lines[index]
            removals += 1
        else:
            if index > len(lines):
                return f"Cannot insert at line {line_no}: file has only {len(lines)} lines."
            lines.insert(index, content)
            additions += 1

    new_text = "\n".join(lines)
    if had_trailing_newline:
        new_text += "\n"

    try:
        target.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return f"Failed to write '{relative}': {exc}"

    return (
        f"{backup_msg}\nApplied {additions} addition(s) and {removals} removal(s) to '{relative}'."
    )


def build_git_tools(repo_root: Path, base_branch: str) -> List[ToolSpec]:
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

    def _edit_tool(args: Dict[str, str]) -> str:
        file_path = args.get("file_path") or ""
        edits = args.get("edits") or ""
        return _edit_file_with_directives(repo_root, file_path, edits)

    edit_tool = ToolSpec(
        name="GitEditFile",
        description=(
            "Apply targeted edits to a file using 'line +/- content' directives. "
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
                    "type": "string",
                    "description": (
                        "Edit directives, one per line, formatted as 'LINE +/- text'. "
                        "Use '-' to remove the specified line and '+' to insert before that line number. "
                        "Append by targeting the total line count + 1."
                    ),
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
