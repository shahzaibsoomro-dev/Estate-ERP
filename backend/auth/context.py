"""Per-request actor, so audit entries record who did what without touching every service."""
from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
current_ip: ContextVar[str | None] = ContextVar("current_ip", default=None)
