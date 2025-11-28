from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractFileCreate(BaseModel):
    storage_path: str
    file_name: str
    mime_type: str
    file_size_bytes: int


class ContractCreate(BaseModel):
    title: str
    status: str | None = Field(default=None, description="Optional status override")
    file: ContractFileCreate


class ContractFileRead(BaseModel):
    id: UUID
    storage_path: str
    file_name: str
    mime_type: str
    file_size_bytes: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContractVersionRead(BaseModel):
    id: UUID
    contract_id: UUID
    file_id: UUID
    version_number: int
    is_current: bool
    created_at: datetime
    file: ContractFileRead

    model_config = ConfigDict(from_attributes=True)


class ContractRead(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: ContractVersionRead | None = None

    model_config = ConfigDict(from_attributes=True)


class ContractsPage(BaseModel):
    items: list[ContractRead]
    total: int
    limit: int
    offset: int
