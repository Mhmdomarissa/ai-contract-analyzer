"""Celery tasks package.

Import task modules here so Celery autodiscovery registers them when loading
``app.tasks``.
"""

# Explicit imports keep Celery from dropping "unregistered task" messages.
from app.tasks import clause_extraction, conflict_analysis  # noqa: F401

__all__ = [
	"clause_extraction",
	"conflict_analysis",
]

