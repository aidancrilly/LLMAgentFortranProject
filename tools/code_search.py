from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .fortran_utils import FORTRAN_SOURCE_SUFFIXES, FORTRAN_KEYWORDS, DECLARATION_PATTERN, END_PATTERN, FortranEntity, iter_fortran_sources
from .path_utils import resolve_within_root
from .snippet_utils import format_numbered_snippet
from .tool_spec import ToolSpec

def _remove_inline_comment(line: str) -> str:
    """Strip trailing ! comments while respecting quoted strings."""
    result: List[str] = []
    in_single = False
    in_double = False
    for char in line:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "!" and not in_single and not in_double:
            break
        result.append(char)
    return "".join(result)


def _analyze_fortran_file(content: str) -> Tuple[FortranEntity, List[str]]:
    """Return the parsed entity tree plus the original lines."""
    lines = content.splitlines()
    root = FortranEntity(kind="__root__", name="root", start_line=0, start_index=0)
    stack: List[FortranEntity] = [root]

    for idx, raw_line in enumerate(lines):
        stripped = _remove_inline_comment(raw_line).strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("contains"):
            continue
        if lowered.startswith("end"):
            if END_PATTERN.match(stripped) and len(stack) > 1:
                entity = stack.pop()
                entity.end_line = idx + 1
                entity.end_index = idx
            continue

        matches = list(DECLARATION_PATTERN.finditer(stripped))
        if not matches:
            continue
        match = matches[-1]
        kind = match.group(1).lower()
        name = match.group(2)
        if kind == "module":
            trailing = stripped[match.end() :].strip()
            if trailing:
                # Skip lines such as "module procedure foo".
                continue
        entity = FortranEntity(
            kind=kind, name=name, start_line=idx + 1, start_index=idx
        )
        stack[-1].children.append(entity)
        stack.append(entity)

    while len(stack) > 1:
        entity = stack.pop()
        entity.end_line = len(lines)
        entity.end_index = max(len(lines) - 1, entity.start_index)

    return root, lines


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
    root, _ = _analyze_fortran_file(content)
    structure_lines = _format_entity_tree(root)
    if not structure_lines:
        return f"No program/module/subroutine/function declarations found in {path}."
    header = f"# Structure of {path}"
    return header + "\n" + "\n".join(structure_lines)


def _find_entity_by_name(
    entity: FortranEntity, symbol_name: str, symbol_kind: Optional[str]
) -> Optional[FortranEntity]:
    normalized_name = symbol_name.lower()
    normalized_kind = symbol_kind.lower() if symbol_kind else None
    for child in entity.children:
        if child.name.lower() == normalized_name:
            if normalized_kind is None or child.kind == normalized_kind:
                return child
        result = _find_entity_by_name(child, symbol_name, symbol_kind)
        if result:
            return result
    return None


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
    root, lines = _analyze_fortran_file(content)
    entity = _find_entity_by_name(root, symbol_name, symbol_kind)
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
    max_matches: int = 5,
    preview_chars: int = 1000,
) -> str:
    """Return snippets of files that match the query string."""
    matches: List[str] = []
    lowered = query.lower()
    suffixes = tuple(ext.lower() for ext in include_extensions)
    candidates: Iterable[Path]
    if suffixes == tuple(FORTRAN_SOURCE_SUFFIXES):
        candidates = iter_fortran_sources(project_root)
    else:
        candidates = (
            path
            for path in project_root.rglob("*")
            if path.is_file() and path.suffix.lower() in suffixes
        )

    for file_path in candidates:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if lowered in content.lower():
                snippet = content[:preview_chars]
                matches.append(f"File: {file_path}\n---\n{snippet}\n...")
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
