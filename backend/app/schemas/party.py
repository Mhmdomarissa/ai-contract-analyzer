"""Party schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PartyBase(BaseModel):
    """Base party schema."""
    name: str
    role: Optional[str] = None
    order_index: int = 0


class PartyCreate(PartyBase):
    """Schema for creating a party."""
    contract_id: UUID


class PartyInDB(PartyBase):
    """Party schema with database fields."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    contract_id: UUID
    created_at: datetime


class Party(PartyInDB):
    """Public party schema."""
    pass
