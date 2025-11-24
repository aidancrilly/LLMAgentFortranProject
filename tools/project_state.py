from pathlib import Path
from typing import Dict, List

from .fortran_utils import iter_fortran_sources
from .tool_spec import ToolSpec


def describe_project(project_root: Path, max_entries: int = 200) -> str:
    """Return a lightweight tree of the project for grounding."""
    entries = []
    for path in sorted(project_root.iterdir()):
        marker = "[DIR]" if path.is_dir() else "[FILE]"
        entries.append(f"{marker} {path.relative_to(project_root)}")
        if len(entries) >= max_entries:
            break
    return "\n".join(entries) or "Project directory is empty."


def list_fortran_sources(project_root: Path, max_files: int = 30) -> str:
    sorted_paths = sorted(
        (path for path in iter_fortran_sources(project_root)),
        key=lambda path: str(path.relative_to(project_root)),
    )
    files = [str(path.relative_to(project_root)) for path in sorted_paths[:max_files]]
    if not files:
        return f"No Fortran sources found under {project_root}"
    return "Fortran sources:\n" + "\n".join(files)


def build_project_overview_tools(project_root: Path) -> List[ToolSpec]:
    overview_tool = ToolSpec(
        name="ProjectTree",
        description="Show the top-level layout of the Fortran project directory.",
        parameters={"type": "object", "properties": {}},
        func=lambda _: describe_project(project_root),
    )

    def _list_sources(args: Dict[str, int]) -> str:
        max_files = int(args.get("max_files", 30) or 30)
        return list_fortran_sources(project_root, max_files=max_files)

    list_sources_tool = ToolSpec(
        name="ListFortranSources",
        description="List representative Fortran source files under the project root.",
        parameters={
            "type": "object",
            "properties": {
                "max_files": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of files to list (default 30).",
                }
            },
        },
        func=_list_sources,
    )
    return [overview_tool, list_sources_tool]
