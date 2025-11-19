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


def _resolve_patch_path(repo_root: Path, patch_path: str) -> Tuple[Path, str]:
    candidate = Path(patch_path.strip() or "agent.patch").expanduser()
    base = repo_root.resolve()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        raise ValueError("Patch path must stay within the repository root.")
    return candidate, str(relative)


def _write_patch_file(repo_root: Path, patch_content: str, patch_path: str) -> str:
    if not patch_content.strip():
        return "Provide non-empty unified diff content via the 'patch' field."
    try:
        patch_file, relative_path = _resolve_patch_path(repo_root, patch_path)
    except ValueError as exc:
        return str(exc)

    try:
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_content.rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        return f"Failed to write patch file: {exc}"

    return f"Wrote patch file to {relative_path}"


def _apply_patch_to_branch(
    repo_root: Path, base_branch: str, branch_name: str, commit_message: str, patch_path: str
) -> str:
    branch = branch_name.strip()
    if not branch:
        return "Provide 'branch_name' for the branch that will receive the patch."
    commit_msg = commit_message.strip()
    if not commit_msg:
        return "Provide 'commit_message' describing the applied changes."

    try:
        patch_file, relative_patch = _resolve_patch_path(repo_root, patch_path)
    except ValueError as exc:
        return str(exc)

    if not patch_file.exists():
        return f"Patch file '{relative_patch}' does not exist. Run GitCreatePatch first."

    commands = [
        ["checkout", base_branch],
        ["checkout", "-b", branch],
        ["apply", str(patch_file)],
        ["add", "-A"],
        ["commit", "-m", commit_msg],
    ]

    run_log = []
    for cmd in commands:
        success, output = _run_git_checked(repo_root, cmd)
        run_log.append(f"$ {_format_git_command(cmd)}\n{output}")
        if not success:
            return (
                "GitApplyPatch aborted due to an error:\n"
                + "\n\n".join(run_log)
            )

    return (
        f"Patch from '{relative_patch}' applied on new branch '{branch}'.\n\n"
        + "\n\n".join(run_log)
    )


def build_git_tools(repo_root: Path, base_branch: str) -> List[ToolSpec]:
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

    def _create_patch_tool(args: Dict[str, str]) -> str:
        patch_content = args.get("patch") or ""
        patch_path = args.get("patch_path") or "agent.patch"
        return _write_patch_file(repo_root, patch_content, patch_path)

    create_patch_tool = ToolSpec(
        name="GitCreatePatch",
        description=(
            "Persist agent-provided unified diff content to a patch file under the repository root. "
            "Call this once you have concrete edits to apply."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "Unified diff output describing the desired edits.",
                },
                "patch_path": {
                    "type": "string",
                    "description": "Relative path for the patch file (default 'agent.patch').",
                },
            },
            "required": ["patch"],
        },
        func=_create_patch_tool,
    )

    def _apply_patch_tool(args: Dict[str, str]) -> str:
        patch_path = args.get("patch_path") or "agent.patch"
        branch_name = args.get("branch_name") or ""
        commit_message = args.get("commit_message") or ""
        return _apply_patch_to_branch(
            repo_root, base_branch, branch_name, commit_message, patch_path
        )

    apply_patch_tool = ToolSpec(
        name="GitApplyPatch",
        description=(
            "Checkout the base branch, create a new branch, apply the stored patch, stage all changes, "
            "and commit with the provided message. No pull is performed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "patch_path": {
                    "type": "string",
                    "description": "Relative path to the patch file produced by GitCreatePatch (default 'agent.patch').",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Name for the new branch that will be created from the base branch.",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Commit message to use after applying the patch.",
                },
            },
            "required": ["branch_name", "commit_message"],
        },
        func=_apply_patch_tool,
    )

    return [status_tool, diff_tool, create_patch_tool, apply_patch_tool]
