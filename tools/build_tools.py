import subprocess
from pathlib import Path
from typing import Dict, List

from .tool_spec import ToolSpec


def _capture_make_output(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["make"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "Build failed: 'make' executable is not available on this system."
    except Exception as exc:
        return f"Build failed to run: {exc}"

    stdout_lines = completed.stdout.splitlines() if completed.stdout else []
    stderr_lines = completed.stderr.splitlines() if completed.stderr else []
    combined_lines = stdout_lines + stderr_lines

    if completed.returncode == 0:
        return "Build succeeded."

    error_lines = [line for line in combined_lines if "error" in line.lower()]
    if not error_lines:
        error_lines = combined_lines[-20:]
    if not error_lines:
        error_lines = ["(no output captured)"]

    return (
        f"Build failed with status {completed.returncode}. "
        "Relevant output:\n" + "\n".join(error_lines)
    )


def build_build_tools(project_root: Path) -> List[ToolSpec]:
    def _make_tool(_: Dict[str, str]) -> str:
        return _capture_make_output(project_root)

    build_tool = ToolSpec(
        name="BuildProject",
        description=(
            "Execute 'make' from the project root. Only reports success or lines containing errors."
        ),
        parameters={"type": "object", "properties": {}},
        func=_make_tool,
    )
    return [build_tool]
