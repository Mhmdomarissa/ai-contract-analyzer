"""Clause schemas."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ClauseBase(BaseModel):
    """Base clause schema."""
    clause_number: str
    content: str
    title: Optional[str] = None
    level: int = 0
    order_index: int


class ClauseCreate(ClauseBase):
    """Schema for creating a clause."""
    contract_id: UUID
    version_id: UUID
    uuid_from_extractor: Optional[UUID] = None
    parent_clause_id: Optional[UUID] = None
    word_count: Optional[int] = None


class ClauseInDB(ClauseBase):
    """Clause schema with database fields."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    contract_id: UUID
    version_id: UUID
    uuid_from_extractor: Optional[UUID] = None
    parent_clause_id: Optional[UUID] = None
    word_count: Optional[int] = None
    created_at: datetime


class Clause(ClauseInDB):
    """Public clause schema."""
    pass


class ClauseWithSubClauses(Clause):
    """Clause with nested sub-clauses."""
    sub_clauses: List['ClauseWithSubClauses'] = []
