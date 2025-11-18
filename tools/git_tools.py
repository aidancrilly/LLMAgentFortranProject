import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List

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


def git_status(repo_root: Path) -> str:
    return _run_git(repo_root, ["status", "--short", "--branch"])


def git_diff(repo_root: Path, diff_target: str = "--stat") -> str:
    args = ["diff"]
    if diff_target.strip():
        args.append(diff_target.strip())
    return _run_git(repo_root, args)


def _slugify(text: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return "-".join(tokens[:6]) or "update"


def propose_git_plan(request: str, base_branch: str = "main") -> str:
    slug = _slugify(request)
    branch_name = f"LLMfeat/{slug}"
    commit_message = request[:60].strip().rstrip(".") or "Update Fortran sources"
    return (
        f"# Proposed git workflow for: {request}\n"
        f"git checkout {base_branch}\n"
        f"git pull --ff-only\n"
        f"git checkout -b {branch_name}\n"
        "# Apply the necessary edits, for example via `git apply`:\n"
        "cat <<'PATCH' > change.patch\n"
        "# ...populate patch content here...\n"
        "PATCH\n"
        "git apply change.patch\n"
        "git status\n"
        "git add <updated files>\n"
        f'git commit -m "{commit_message}"\n'
        f"git push --set-upstream origin {branch_name}\n"
        "# Open a merge request / pull request."
    )


def _parse_git_commands(plan_text: str) -> List[List[str]]:
    commands: List[List[str]] = []
    for raw_line in plan_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.lower().startswith("git "):
            continue
        try:
            parts = shlex.split(stripped)
        except ValueError as exc:
            raise ValueError(f"Unable to parse git command '{stripped}': {exc}")
        if len(parts) < 2:
            continue
        commands.append(parts[1:])
    return commands


def _format_git_command(args: List[str]) -> str:
    try:
        formatter = shlex.join  # type: ignore[attr-defined]
    except AttributeError:
        formatter = lambda tokens: " ".join(tokens)
    return f"git {formatter(args)}"


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

    def _plan_tool(args: Dict[str, str]) -> str:
        request = args.get("request", "").strip()
        if not request:
            return "Provide a 'request' describing the desired change."
        return propose_git_plan(request, base_branch)

    plan_tool = ToolSpec(
        name="GitPlan",
        description=(
            "Generate a step-by-step git command sequence for implementing the requested change. "
            "Call this once you understand what edits are needed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "Summary of the change that requires a git plan.",
                }
            },
            "required": ["request"],
        },
        func=_plan_tool,
    )

    def _execute_plan_tool(args: Dict[str, str]) -> str:
        plan_text = args.get("plan", "").strip()
        confirm_raw = args.get("confirm")
        confirm = False
        if isinstance(confirm_raw, bool):
            confirm = confirm_raw
        elif isinstance(confirm_raw, str):
            confirm = confirm_raw.strip().lower() in {"true", "1", "yes", "y"}

        if not plan_text:
            return "Provide the full git plan text (for example, from GitPlan) via the 'plan' field."

        try:
            commands = _parse_git_commands(plan_text)
        except ValueError as exc:
            return str(exc)

        if not commands:
            return "No git commands were detected in the provided plan."

        command_preview = "\n".join(_format_git_command(cmd) for cmd in commands)
        if not confirm:
            return (
                "Confirmation required before executing the git plan.\n\n"
                "Commands that would run:\n"
                f"{command_preview}\n\n"
                "Re-run GitExecutePlan with confirm=true only after the user agrees."
            )

        results = []
        for cmd in commands:
            output = _run_git(repo_root, cmd)
            results.append(f"$ {_format_git_command(cmd)}\n{output}")
        return "\n\n".join(results)

    execute_plan_tool = ToolSpec(
        name="GitExecutePlan",
        description=(
            "Execute each git command contained in a previously generated plan. "
            "You must secure user confirmation before passing confirm=true."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "Full text of the proposed git plan.",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Set to true only after the user explicitly approves running the commands.",
                },
            },
            "required": ["plan"],
        },
        func=_execute_plan_tool,
    )

    return [status_tool, diff_tool, plan_tool, execute_plan_tool]
