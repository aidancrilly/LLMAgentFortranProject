from pathlib import Path
from typing import Dict, Iterable, List

from .tool_spec import ToolSpec


def _iter_fortran_files(project_root: Path, max_files: int) -> Iterable[Path]:
    count = 0
    for file_path in sorted(project_root.rglob("*")):
        if file_path.suffix.lower() in (".f90", ".f95", ".f") and file_path.is_file():
            yield file_path
            count += 1
            if count >= max_files:
                break


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
    files = [str(path.relative_to(project_root)) for path in _iter_fortran_files(project_root, max_files)]
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
