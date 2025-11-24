from typing import Iterable, List, Optional, Sequence


def format_numbered_snippet(lines: Sequence[str], start_line: int, width: int = 5) -> str:
    """
    Return a string where each line is prefixed with a line number.
    """
    template = f"{{:0{width}d}}: {{}}"
    return "\n".join(
        template.format(start_line + idx, line) for idx, line in enumerate(lines)
    )


def iter_numbered_lines(
    iterable: Iterable[str], start_line: int = 1, max_lines: Optional[int] = None
) -> List[str]:
    collected: List[str] = []
    for idx, line in enumerate(iterable, start=1):
        if idx < start_line:
            continue
        if max_lines is not None and len(collected) >= max_lines:
            break
        collected.append(line.rstrip("\n"))
    return collected
