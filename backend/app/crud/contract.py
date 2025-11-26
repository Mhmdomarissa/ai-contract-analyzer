from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.schemas.contract import ContractCreate


def get_contract(db: Session, contract_id: int) -> Contract | None:
    return db.get(Contract, contract_id)


def create_contract(db: Session, contract_in: ContractCreate) -> Contract:
    contract = Contract(title=contract_in.title, status="PENDING")
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract

