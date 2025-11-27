from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .file_tools import write_whole_file
from .fortran_utils import FortranEntity, find_entity_by_name, parse_fortran_entities
from .path_utils import resolve_within_root
from .tool_spec import ToolSpec


def _resolve_existing_file(project_root: Path, file_path: str) -> Tuple[Optional[Path], str]:
    if not file_path.strip():
        return None, "Provide 'file_path' pointing to the Fortran file to update."
    try:
        target = resolve_within_root(project_root, file_path)
    except ValueError as exc:
        return None, str(exc)
    relative = str(target.relative_to(project_root.resolve()))
    if not target.exists():
        return None, f"File '{relative}' does not exist."
    if not target.is_file():
        return None, f"Path '{relative}' is not a regular file."
    return target, ""


def _locate_parent_entity(
    root: FortranEntity, parent_name: Optional[str]
) -> Tuple[Optional[FortranEntity], str]:
    if not parent_name:
        return root, "file root"
    parent = find_entity_by_name(root, parent_name, None)
    if not parent:
        return None, f"Parent module/program '{parent_name}' not found."
    if parent.kind not in {"module", "program"}:
        return None, f"Parent '{parent_name}' is a {parent.kind}, expected module or program."
    return parent, f"{parent.kind} {parent.name}"


def _find_child(
    parent: FortranEntity, child_name: str, allowed_kinds: Optional[List[str]] = None
) -> Optional[FortranEntity]:
    normalized = child_name.lower()
    for child in parent.children:
        if child.name.lower() != normalized:
            continue
        if allowed_kinds and child.kind not in allowed_kinds:
            continue
        return child
    return None


def _ensure_contains_section(
    lines: List[str], parent: FortranEntity, insertion_index: int
) -> int:
    if parent.kind not in {"module", "program"}:
        return 0
    start = parent.start_index
    end = min(parent.end_index if parent.end_index is not None else len(lines), len(lines))
    for idx in range(start, end):
        if lines[idx].strip().lower().startswith("contains"):
            return 0
    block = ["contains", ""]
    insert_pos = min(insertion_index, len(lines))
    lines[insert_pos:insert_pos] = block
    return len(block)


def _insert_callable_lines(
    lines: List[str], insertion_index: int, callable_lines: List[str]
) -> int:
    if not callable_lines:
        return insertion_index

    block: List[str] = callable_lines[:]
    if insertion_index > 0 and lines[insertion_index - 1].strip() and block[0].strip():
        block.insert(0, "")
    if insertion_index < len(lines) and lines[insertion_index].strip() and block[-1].strip():
        block.append("")

    lines[insertion_index:insertion_index] = block
    return insertion_index


def _create_callable_text(
    project_root: Path,
    file_path: str,
    callable_type: str,
    name: str,
    parent_name: Optional[str],
    append_after: Optional[str],
    callable_content: str,
) -> Tuple[Optional[str], str]:
    file_path_obj, error = _resolve_existing_file(project_root, file_path)
    if not file_path_obj:
        return None, error

    try:
        original_text = file_path_obj.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"Failed to read '{file_path}': {exc}"
    had_trailing_newline = original_text.endswith("\n")
    root, lines = parse_fortran_entities(original_text)
    parent, parent_desc = _locate_parent_entity(root, parent_name)
    if not parent:
        return None, parent_desc

    normalized_type = callable_type.lower()
    if normalized_type not in {"subroutine", "function"}:
        return None, "callable_type must be 'subroutine' or 'function'."
    normalized_name = name.lower()
    for child in parent.children:
        if child.name.lower() == normalized_name and child.kind == normalized_type:
            return None, f"{normalized_type.title()} '{name}' already exists in {parent_desc}."

    target_sibling: Optional[FortranEntity] = None
    insertion_index: int
    if append_after:
        target_sibling = _find_child(
            parent, append_after, allowed_kinds=["subroutine", "function"]
        )
        if not target_sibling:
            return None, f"Callable '{append_after}' not found in {parent_desc}."
        end_index = (
            target_sibling.end_index
            if target_sibling.end_index is not None
            else target_sibling.start_index
        )
        insertion_index = min(len(lines), end_index + 1)
    else:
        if parent.kind == "__root__":
            insertion_index = len(lines)
        else:
            parent_end = parent.end_index if parent.end_index is not None else len(lines)
            insertion_index = min(parent_end, len(lines))
        insertion_index += _ensure_contains_section(lines, parent, insertion_index)

    callable_lines = callable_content.splitlines()
    if not callable_lines or not callable_content.strip():
        return None, "callable_content must include the new Fortran code."

    _insert_callable_lines(lines, insertion_index, callable_lines)

    new_text = "\n".join(lines)
    if had_trailing_newline:
        new_text += "\n"

    location = (
        f"after '{append_after}' in {parent_desc}"
        if append_after
        else f"at the end of {parent_desc}"
    )
    summary = f"Inserted {normalized_type} '{name}' {location}."
    return new_text, summary


def build_fortran_edit_tools(project_root: Path) -> List[ToolSpec]:
    def _create_callable_tool(args: Dict[str, str]) -> str:
        file_path = str(args.get("file_path") or "").strip()
        callable_type = str(args.get("callable_type") or "").strip().lower()
        name = str(args.get("name") or "").strip()
        parent_module = args.get("parent_module")
        append_after = args.get("append_after")
        content_value = args.get("callable_content")
        if not file_path:
            return "Provide 'file_path' for the Fortran source file."
        if callable_type not in {"subroutine", "function"}:
            return "Provide 'callable_type' as 'subroutine' or 'function'."
        if not name:
            return "Provide 'name' for the new callable."
        if content_value is None:
            return "Provide 'callable_content' containing the new Fortran code."
        callable_content = str(content_value)

        new_text, summary = _create_callable_text(
            project_root,
            file_path,
            callable_type,
            name,
            str(parent_module).strip() if parent_module else None,
            str(append_after).strip() if append_after else None,
            callable_content,
        )
        if new_text is None:
            return summary

        write_result = write_whole_file(project_root, file_path, new_text)
        if "Wrote" not in write_result:
            return write_result
        return f"{write_result}\n{summary}"

    create_callable_tool = ToolSpec(
        name="CreateFortranCallableInFile",
        description=(
            "Insert a Fortran subroutine or function into an existing source file, "
            "optionally inside a specific module/program and/or after another callable."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the Fortran source file to update.",
                },
                "callable_type": {
                    "type": "string",
                    "enum": ["subroutine", "function"],
                    "description": "Type of callable to insert.",
                },
                "name": {
                    "type": "string",
                    "description": "Name of the new subroutine or function.",
                },
                "parent_module": {
                    "type": ["string", "null"],
                    "description": "Module/program that should contain the new callable.",
                },
                "append_after": {
                    "type": ["string", "null"],
                    "description": "Existing callable name to insert after.",
                },
                "callable_content": {
                    "type": "string",
                    "description": "Full Fortran source text for the new callable.",
                },
            },
            "required": ["file_path", "callable_type", "name", "callable_content"],
        },
        func=_create_callable_tool,
    )

    return [create_callable_tool]
