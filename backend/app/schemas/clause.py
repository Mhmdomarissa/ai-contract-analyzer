from __future__ import annotations

from datetime import datetime
from typing import Any
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
    arabic_text: str | None = None
    is_bilingual: bool = False
    number_normalized: str | None
    analysis_results: dict | None = None
    analysis_status: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClauseExtractionJobRead(BaseModel):
    run: AnalysisRunRead
    clauses: list[ClauseRead] | None = None

    model_config = ConfigDict(from_attributes=True)
