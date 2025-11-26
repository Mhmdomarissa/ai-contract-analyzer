from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContractBase(BaseModel):
    title: str


class ContractCreate(ContractBase):
    file_path: str


class ContractResponse(ContractBase):
    id: int
    upload_date: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)

