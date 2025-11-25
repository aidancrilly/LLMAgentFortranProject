from pathlib import Path
from typing import Dict, Optional

from .path_utils import resolve_within_root
from .snippet_utils import format_numbered_snippet, iter_numbered_lines
from .tool_spec import ToolSpec


def read_file(
    project_root: Path,
    file_path: str,
    start_line: int = 1,
    max_lines: Optional[int] = 400,
) -> str:
    """Reads a slice of a file and returns it with line numbers for grounding."""
    start = max(1, start_line)
    try:
        path = resolve_within_root(project_root, file_path)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"Path not found: {path}"
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            sliced = iter_numbered_lines(handle, start_line=start, max_lines=max_lines)
    except OSError as exc:
        return f"Error reading file: {exc}"
    numbered = format_numbered_snippet(sliced, start_line=start)
    header = f"# File: {path}"
    return header if not numbered else f"{header}\n{numbered}"


def build_file_reader_tools(project_root: Path) -> ToolSpec:
    """Factory that binds the project root to the ReadFile tool."""

    def _snippet_tool(args: Dict[str, int]) -> str:
        path = args.get("path", ".")
        start = int(args.get("start_line", 1) or 1)
        max_lines_value = args.get("max_lines")
        max_lines_int = (
            int(max_lines_value) if max_lines_value is not None else 400
        )
        return read_file(project_root, path, start_line=start, max_lines=max_lines_int)

    read_file_snippet_tool = ToolSpec(
        name="ReadFileSnippet",
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
        func=_snippet_tool,
    )

    def _whole_file_tool(args: Dict) -> str:
        path = args.get("path", ".")
        return read_file(project_root, path, start_line=1, max_lines=10000)

    read_whole_file_tool = ToolSpec(
        name="ReadWholeFile",
        description=(
            "Read entirety of a project file. Provide 'path' only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file.",
                },
            },
            "required": ["path"],
        },
        func=_whole_file_tool,
    )

    return [read_file_snippet_tool,read_whole_file_tool]