"""Data plane: query construction and execution.

Public API:
  - select(Model) -> Select
  - and_(*exprs) -> Expression
  - or_(*exprs) -> Expression
  - AsyncSession(engine, state)
  - Session(engine, state)  # sync wrapper around AsyncSession
"""

from pensum.query.expr import Column, Expression, and_, not_, or_
from pensum.query.select import Select, select
from pensum.query.session import AsyncSession, CommitResult
from pensum.query.sync import Session

__all__ = [
    "AsyncSession",
    "Column",
    "CommitResult",
    "Expression",
    "Select",
    "Session",
    "and_",
    "not_",
    "or_",
    "select",
]
