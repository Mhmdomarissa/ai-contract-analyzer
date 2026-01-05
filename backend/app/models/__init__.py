"""ORM models."""

# Import all models so they are registered with SQLAlchemy
from app.models.clause import Clause, ClauseGroup  # noqa
from app.models.conflict import AnalysisRun, Conflict, ConflictHighlight  # noqa
from app.models.contract import Contract, ContractFile, ContractVersion  # noqa

__all__ = [
    "AnalysisRun",
    "Clause",
    "ClauseGroup",
    "Conflict",
    "ConflictHighlight",
    "Contract",
    "ContractFile",
    "ContractVersion",
]
