from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .fortran_utils import (
    FORTRAN_SOURCE_SUFFIXES,
    FORTRAN_KEYWORDS,
    FortranEntity,
    find_entity_by_name,
    iter_fortran_sources,
    parse_fortran_entities,
)
from .path_utils import resolve_within_root
from .snippet_utils import format_numbered_snippet
from .tool_spec import ToolSpec


def _format_entity_tree(entity: FortranEntity, indent: int = 0) -> List[str]:
    lines: List[str] = []
    for child in entity.children:
        label = f"{'  ' * indent}{child.kind.title()} {child.name} (line {child.start_line})"
        lines.append(label)
        lines.extend(_format_entity_tree(child, indent + 1))
    return lines


def _resolve_project_path(project_root: Path, file_path: str) -> Path:
    try:
        return resolve_within_root(project_root, file_path)
    except ValueError as exc:  # pragma: no cover - defensive path check
        raise ValueError(str(exc)) from exc


def summarise_fortran_file(project_root: Path, file_path: str) -> str:
    try:
        path = _resolve_project_path(project_root, file_path)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"File not found: {path}"
    if not path.is_file():
        return f"Path is not a file: {path}"
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return f"Failed to read {path}: {exc}"
    root, _ = parse_fortran_entities(content)
    structure_lines = _format_entity_tree(root)
    if not structure_lines:
        return f"No program/module/subroutine/function declarations found in {path}."
    header = f"# Structure of {path}"
    return header + "\n" + "\n".join(structure_lines)


def extract_fortran_symbol(
    project_root: Path, file_path: str, symbol_name: str, symbol_kind: Optional[str]
) -> str:
    try:
        path = _resolve_project_path(project_root, file_path)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"File not found: {path}"
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return f"Failed to read {path}: {exc}"
    root, lines = parse_fortran_entities(content)
    entity = find_entity_by_name(root, symbol_name, symbol_kind)
    if not entity:
        target = (
            f"{symbol_kind} '{symbol_name}'" if symbol_kind else f"symbol '{symbol_name}'"
        )
        return f"Could not find {target} in {path}."
    end_index = entity.end_index if entity.end_index is not None else entity.start_index
    snippet_lines = lines[entity.start_index : end_index + 1]
    snippet = format_numbered_snippet(
        snippet_lines, start_line=entity.start_index + 1, width=6
    )
    kind_label = entity.kind.title()
    return (
        f"# {kind_label} {entity.name} from {path}"
        f" (lines {entity.start_line}-{entity.end_line or entity.start_line})\n"
        f"{snippet}"
    )


def search_codebase(
    project_root: Path,
    query: str,
    include_extensions: Sequence[str] = FORTRAN_SOURCE_SUFFIXES,
    max_matches: int = 10,
    context_lines: int = 3,
) -> str:
    """Return line-based snippets of all occurrences of `query` in the codebase.

    For each matching line, returns up to `context_lines` lines before and after
    the line containing the query (case-insensitive), up to `max_matches` total
    snippets across all files.
    """
    matches: List[str] = []
    lowered = query.lower()
    suffixes = tuple(ext.lower() for ext in include_extensions)

    if suffixes == tuple(FORTRAN_SOURCE_SUFFIXES):
        candidates: Iterable[Path] = iter_fortran_sources(project_root)
    else:
        candidates = (
            path
            for path in project_root.rglob("*")
            if path.is_file() and path.suffix.lower() in suffixes
        )

    for file_path in candidates:
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)

            # Find all matching line indices in this file
            match_indices: List[int] = [
                i for i, line in enumerate(lines) if lowered in line.lower()
            ]

            if not match_indices:
                continue

            for occurrence_idx, match_index in enumerate(match_indices, start=1):
                start = max(0, match_index - context_lines)
                end = min(len(lines), match_index + context_lines + 1)

                snippet_lines = lines[start:end]
                snippet = "".join(snippet_lines)

                # 1-based line numbers
                match_line_no = match_index + 1
                start_line_no = start + 1
                end_line_no = end

                matches.append(
                    f"File: {file_path} (match {occurrence_idx} at line {match_line_no}, "
                    f"context lines {start_line_no}-{end_line_no})\n"
                    f"---\n"
                    f"{snippet}\n"
                    f"..."
                )

                if len(matches) >= max_matches:
                    break

        except Exception as exc:
            matches.append(f"Error reading {file_path}: {exc}")

        if len(matches) >= max_matches:
            break

    if not matches:
        return f"No references to '{query}' found under {project_root}"
    return "\n\n".join(matches)


def build_code_search_tool(project_root: Path) -> ToolSpec:
    def _tool(args: Dict[str, str]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Provide a non-empty 'query' to search."
        return search_codebase(project_root, query)

    return ToolSpec(
        name="SearchCodebase",
        description=(
            "Search the Fortran project for occurrences of a string. "
            "Useful when hunting for subroutines, variables, or constants."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring to search for (case-insensitive).",
                }
            },
            "required": ["query"],
        },
        func=_tool,
    )


def build_fortran_summary_tool(project_root: Path) -> ToolSpec:
    def _tool(args: Dict[str, str]) -> str:
        file_path = args.get("file_path", "").strip()
        if not file_path:
            return "Provide 'file_path' pointing to a Fortran source file."
        return summarise_fortran_file(project_root, file_path)

    return ToolSpec(
        name="SummariseFortranFile",
        description=(
            "Summarise a Fortran source file by listing its program, module, "
            "subroutine, and function declarations in hierarchical order."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the Fortran source file.",
                }
            },
            "required": ["file_path"],
        },
        func=_tool,
    )


def _build_specific_symbol_tool(project_root: Path, symbol_kind: str) -> ToolSpec:
    kind_title = symbol_kind.title()

    def _tool(args: Dict[str, str]) -> str:
        file_path = args.get("file_path", "").strip()
        symbol_name = args.get("symbol_name", "").strip()
        if not file_path:
            return "Provide 'file_path' for the Fortran source file."
        if not symbol_name:
            return f"Provide 'symbol_name' for the {symbol_kind} to extract."
        return extract_fortran_symbol(
            project_root, file_path, symbol_name, symbol_kind
        )

    return ToolSpec(
        name=f"ReadFortran{kind_title}",
        description=(
            f"Return the exact source code for a specific Fortran {symbol_kind} "
            "identified by name."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to the Fortran source file.",
                },
                "symbol_name": {
                    "type": "string",
                    "description": f"Name of the target Fortran {symbol_kind}.",
                },
            },
            "required": ["file_path", "symbol_name"],
        },
        func=_tool,
    )


def build_fortran_symbol_reader_tools(project_root: Path) -> List[ToolSpec]:
    return [
        _build_specific_symbol_tool(project_root, kind) for kind in FORTRAN_KEYWORDS
    ]
