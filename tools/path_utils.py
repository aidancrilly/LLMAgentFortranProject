from pathlib import Path


def resolve_within_root(root: Path, requested_path: str) -> Path:
    """
    Resolve a user-provided path and ensure it stays inside the given root.
    """
    if not requested_path:
        requested_path = "."
    candidate = Path(requested_path.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    root_resolved = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Requested path {candidate} is outside the allowed root {root_resolved}"
        ) from exc
    return candidate
