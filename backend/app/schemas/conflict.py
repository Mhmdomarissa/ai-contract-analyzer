from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalysisRunRead(BaseModel):
    id: UUID
    type: str
    model_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None
    contract_version_id: UUID

    model_config = ConfigDict(from_attributes=True)


class ConflictHighlightRead(BaseModel):
    id: UUID
    conflict_id: UUID
    clause_id: UUID
    snippet: str
    start_char: int
    end_char: int

    model_config = ConfigDict(from_attributes=True)


class ClauseSummary(BaseModel):
    id: UUID
    clause_number: str | None = None
    heading: str | None = None
    text: str | None = None  # Include clause text for better UX

    model_config = ConfigDict(from_attributes=True)


class ConflictRead(BaseModel):
    id: UUID
    analysis_run_id: UUID
    severity: str
    score: Decimal | None
    summary: str | None
    explanation: str | None = None
    contract_version_id: UUID
    status: str
    created_at: datetime
    left_clause: ClauseSummary
    right_clause: ClauseSummary
    highlights: list[ConflictHighlightRead] = []

    model_config = ConfigDict(from_attributes=True)
