"""Storage-independent data-layer errors."""

from {{cookiecutter.project_name}}.core.errors import Problem


class ConcurrencyConflictError(Problem):
    """Raised when an optimistic-lock version check fails."""

    def __init__(
        self,
        resource_id: str,
        expected_version: int,
        actual_version: int | None = None,
    ) -> None:
        detail = (
            f"resource '{resource_id}' was modified concurrently; "
            f"expected version {expected_version}"
        )
        if actual_version is not None:
            detail += f", actual version {actual_version}"
        super().__init__(
            title="Concurrent Modification Conflict",
            status_code=409,
            detail=detail,
        )


__all__ = ["ConcurrencyConflictError"]
