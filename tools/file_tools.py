from pathlib import Path
from typing import Dict, Optional

from .tool_spec import ToolSpec


def _resolve_path(project_root: Path, file_path: str) -> Path:
    """Resolve the requested path relative to the Fortran project root."""
    request_path = Path(file_path.strip()).expanduser()
    if not request_path.is_absolute():
        request_path = project_root / request_path
    try:
        request_path.relative_to(project_root)
    except ValueError:
        raise ValueError(
            f"Requested path {request_path} is outside the project root {project_root}"
        )
    return request_path


def read_file(
    project_root: Path,
    file_path: str,
    start_line: int = 1,
    max_lines: Optional[int] = 400,
) -> str:
    """Reads a slice of a file and returns it with line numbers for grounding."""
    try:
        path = _resolve_path(project_root, file_path)
        if not path.exists():
            return f"Path not found: {path}"
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        start = max(1, start_line)
        end = len(lines) if max_lines is None else min(len(lines), start + max_lines - 1)
        sliced = lines[start - 1 : end]
        numbered = [f"{start + idx:05d}: {line}" for idx, line in enumerate(sliced)]
        return f"# File: {path}\n" + "\n".join(numbered)
    except Exception as exc:
        return f"Error reading file: {exc}"


def build_file_reader_tool(project_root: Path) -> ToolSpec:
    """Factory that binds the project root to the ReadFile tool."""

    def _tool(args: Dict[str, int]) -> str:
        path = args.get("path", ".")
        start = int(args.get("start_line", 1) or 1)
        max_lines = args.get("max_lines")
        max_lines_int = int(max_lines) if max_lines is not None else 400
        return read_file(project_root, path, start_line=start, max_lines=max_lines_int)

    return ToolSpec(
        name="ReadFile",
        description=(
            "Read a specific slice of a project file. Provide 'path' plus optional "
            "'start_line' and 'max_lines' integers."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based starting line number (default 1).",
                },
                "max_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of lines to read (default 400).",
                },
            },
            "required": ["path"],
        },
        func=_tool,
    )
