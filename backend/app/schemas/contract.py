"""Contract schemas."""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.models.contract import ContractStatus

if TYPE_CHECKING:
    from app.schemas.party import Party
    from app.schemas.clause import ClauseWithSubClauses


class ContractBase(BaseModel):
    """Base contract schema."""
    filename: str
    file_type: str


class ContractCreate(ContractBase):
    """Schema for creating a contract."""
    original_filename: str
    file_size: int
    status: Optional[ContractStatus] = None


class ContractUpdate(BaseModel):
    """Schema for updating a contract."""
    status: Optional[ContractStatus] = None
    error_message: Optional[str] = None


class ContractInDB(ContractBase):
    """Contract schema with database fields."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    status: ContractStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Contract(ContractInDB):
    """Public contract schema."""
    pass


class ContractWithDetails(Contract):
    """Contract with related data."""
    
    parties: List['Party'] = []
    clauses: List['ClauseWithSubClauses'] = []
    total_clauses: int = 0
