from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.conflict import AnalysisRunRead


class ClauseGroupRead(BaseModel):
    id: UUID
    contract_id: UUID
    label: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClauseRead(BaseModel):
    id: UUID
    contract_version_id: UUID
    clause_number: str | None
    heading: str | None
    order_index: int
    language: str | None
    clause_group_id: UUID | None
    text: str
    number_normalized: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClauseExtractionJobRead(BaseModel):
    run: AnalysisRunRead
    clauses: list[ClauseRead] | None = None

    model_config = ConfigDict(from_attributes=True)
