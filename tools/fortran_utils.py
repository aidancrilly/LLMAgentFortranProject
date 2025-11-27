from pathlib import Path
import re
from typing import Iterable, Iterator, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class FortranEntity:
    kind: str
    name: str
    start_line: int
    start_index: int
    end_line: Optional[int] = None
    end_index: Optional[int] = None
    children: List["FortranEntity"] = field(default_factory=list)

FORTRAN_SOURCE_SUFFIXES: Iterable[str] = (
    ".f",
    ".for",
    ".f90",
    ".f95",
    ".f03",
    ".f08",
)

FORTRAN_KEYWORDS = ("program", "module", "subroutine", "function")
DECLARATION_PATTERN = re.compile(
    r"(program|module|subroutine|function)\s+([A-Za-z_]\w*)", re.IGNORECASE
)
END_PATTERN = re.compile(
    r"^end\s*(program|module|subroutine|function)(?:\s+([A-Za-z_]\w*))?",
    re.IGNORECASE,
)

def iter_fortran_sources(project_root: Path) -> Iterator[Path]:
    for path in project_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in FORTRAN_SOURCE_SUFFIXES:
            yield path


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


def parse_fortran_entities(content: str) -> Tuple[FortranEntity, List[str]]:
    """
    Parse the provided source text and return the root entity tree plus the split lines.
    """
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
        entity = FortranEntity(kind=kind, name=name, start_line=idx + 1, start_index=idx)
        stack[-1].children.append(entity)
        stack.append(entity)

    while len(stack) > 1:
        entity = stack.pop()
        entity.end_line = len(lines)
        entity.end_index = max(len(lines) - 1, entity.start_index)

    return root, lines


def find_entity_by_name(
    entity: FortranEntity, symbol_name: str, symbol_kind: Optional[str]
) -> Optional[FortranEntity]:
    normalized_name = symbol_name.lower()
    normalized_kind = symbol_kind.lower() if symbol_kind else None
    for child in entity.children:
        if child.name.lower() == normalized_name:
            if normalized_kind is None or child.kind == normalized_kind:
                return child
        result = find_entity_by_name(child, symbol_name, symbol_kind)
        if result:
            return result
    return None
