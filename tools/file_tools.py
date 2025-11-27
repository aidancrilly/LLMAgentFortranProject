import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def _resolve_project_file(project_root: Path, file_path: str) -> Tuple[Optional[Path], str]:
    if not file_path.strip():
        return None, "Provide 'file_path' for the target file."
    try:
        path = resolve_within_root(project_root, file_path)
    except ValueError as exc:
        return None, str(exc)
    relative = str(path.relative_to(project_root.resolve()))
    return path, relative


def _ensure_backup(project_root: Path, target: Path, relative: str) -> Tuple[bool, str]:
    backup_path = target.with_name(target.name + ".orig")
    try:
        backup_relative = str(backup_path.relative_to(project_root.resolve()))
    except ValueError:
        backup_relative = str(backup_path)

    if backup_path.exists():
        return True, f"Backup already exists at '{backup_relative}'."

    try:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
    except OSError as exc:
        return False, f"Failed to create backup file: {exc}"

    return True, f"Copied '{relative}' to '{backup_relative}'."


def write_whole_file(project_root: Path, file_path: str, content: str) -> str:
    path, relative_or_error = _resolve_project_file(project_root, file_path)
    if path is None:
        return relative_or_error

    backup_msg = ""
    if path.exists():
        if not path.is_file():
            return f"Path '{relative_or_error}' is not a regular file."
        ok, backup_msg = _ensure_backup(project_root, path, relative_or_error)
        if not ok:
            return backup_msg

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Failed to create parent directory for '{relative_or_error}': {exc}"

    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"Failed to write '{relative_or_error}': {exc}"

    if backup_msg:
        return f"{backup_msg}\nWrote {len(content)} byte(s) to '{relative_or_error}'."
    return f"Wrote {len(content)} byte(s) to new file '{relative_or_error}'."


def build_file_reader_tools(project_root: Path) -> List[ToolSpec]:
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

    def _write_whole_file_tool(args: Dict) -> str:
        file_path_value = args.get("file_path") or ""
        content_value = args.get("content")
        if content_value is None:
            return "Provide 'content' with the complete new file contents."
        return write_whole_file(project_root, str(file_path_value), str(content_value))

    write_whole_file_tool = ToolSpec(
        name="WriteWholeFile",
        description=(
            "Overwrite or create a file with the exact text you provide. "
            "If the file exists, a '<file>.orig' backup is written first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the repository file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Complete new contents of the file.",
                },
            },
            "required": ["file_path", "content"],
        },
        func=_write_whole_file_tool,
    )

    return [read_file_snippet_tool, read_whole_file_tool, write_whole_file_tool]
