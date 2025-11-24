from pathlib import Path
import re
from typing import Iterable, Iterator, List, Optional
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
    r"^end\s*(program|module|subroutine|function)?(?:\s+([A-Za-z_]\w*))?",
    re.IGNORECASE,
)

def iter_fortran_sources(project_root: Path) -> Iterator[Path]:
    for path in project_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in FORTRAN_SOURCE_SUFFIXES:
            yield path
