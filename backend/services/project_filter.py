"""Helpers for filtering by one or many project IDs."""


def parse_project_ids(project_ids: str | None, project_id: int | None = None) -> list[int] | None:
    """Return list of IDs, or None meaning all projects."""
    if project_ids:
        ids = [int(x.strip()) for x in project_ids.split(",") if x.strip()]
        return ids if ids else None
    if project_id is not None:
        return [project_id]
    return None


def sql_in(column: str, ids: list[int] | None) -> tuple[str, tuple]:
    if not ids:
        return "", ()
    if len(ids) == 1:
        return f" AND {column}=?", (ids[0],)
    ph = ",".join("?" * len(ids))
    return f" AND {column} IN ({ph})", tuple(ids)
