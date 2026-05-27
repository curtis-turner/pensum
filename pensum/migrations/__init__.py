"""Migration system (Alembic-style) for pensum.

Public API:
  - Migration: declarative migration unit with revision, down_revision, upgrade, downgrade
  - op: namespace for the operations a migration can perform
  - get_context: current migration context (engine + state) inside an upgrade/downgrade

CLI surface:
  - pensum upgrade --env <name>
  - pensum current --env <name>
  - pensum history
  - pensum revision --autogenerate -m "..."   (deferred to next slice)
  - pensum downgrade --env <name> -r ...       (deferred to next slice)
"""

from pensum.migrations import op
from pensum.migrations.base import Migration
from pensum.migrations.context import MigrationContext, get_context
from pensum.migrations.exceptions import (
    MigrationConflictError,
    MigrationError,
    MigrationGraphError,
    UnsupportedDowngradeError,
)
from pensum.migrations.loader import load_migrations
from pensum.migrations.runner import downgrade, upgrade

__all__ = [
    "Migration",
    "MigrationConflictError",
    "MigrationContext",
    "MigrationError",
    "MigrationGraphError",
    "UnsupportedDowngradeError",
    "downgrade",
    "get_context",
    "load_migrations",
    "op",
    "upgrade",
]
