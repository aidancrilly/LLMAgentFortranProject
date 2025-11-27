import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

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


def build_git_tools(project_root: Path, repo_root: Path, base_branch: str) -> List[ToolSpec]:
    _ = project_root  # retained for compatibility; editing tools now live elsewhere.
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
        commit_tool,
    ]
