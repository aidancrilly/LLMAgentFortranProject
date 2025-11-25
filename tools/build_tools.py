import subprocess
from pathlib import Path
from typing import Dict, List

from .tool_spec import ToolSpec


def _capture_make_output(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["make"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "Build failed: 'make' executable is not available on this system."
    except Exception as exc:
        return f"Build failed to run: {exc}"

    stderr_lines = completed.stderr.splitlines() if completed.stderr else []

    if completed.returncode == 0:
        return "Build succeeded."

    return (
        f"Build failed with status {completed.returncode}. "
        "Relevant output:\n" + "\n".join(stderr_lines)
    )


def build_build_tools(repo_root: Path) -> List[ToolSpec]:
    def _make_tool(_: Dict[str, str]) -> str:
        return _capture_make_output(repo_root)

    build_tool = ToolSpec(
        name="BuildProject",
        description=(
            "Execute 'make' from the project root. Only reports success or lines containing errors."
        ),
        parameters={"type": "object", "properties": {}},
        func=_make_tool,
    )
    return [build_tool]
