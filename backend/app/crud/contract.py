"""CRUD operations for contracts."""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.contract import Contract
from app.models.contract_version import ContractVersion
from app.models.clause import Clause
from app.models.party import Party
from app.schemas.contract import ContractCreate, ContractUpdate


def create_contract(db: Session, contract: ContractCreate) -> Contract:
    """Create a new contract."""
    db_contract = Contract(
        filename=contract.filename,
        original_filename=contract.original_filename,
        file_type=contract.file_type,
        file_size=contract.file_size,
        status=contract.status
    )
    db.add(db_contract)
    db.commit()
    db.refresh(db_contract)
    return db_contract


def get_contract(db: Session, contract_id: UUID) -> Optional[Contract]:
    """Get contract by ID."""
    return db.query(Contract).filter(Contract.id == contract_id).first()


def get_contracts(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[Contract]:
    """Get all contracts with pagination."""
    return db.query(Contract).order_by(desc(Contract.created_at)).offset(skip).limit(limit).all()


def update_contract(
    db: Session,
    contract_id: UUID,
    contract_update: ContractUpdate
) -> Optional[Contract]:
    """Update contract."""
    db_contract = get_contract(db, contract_id)
    if not db_contract:
        return None
    
    update_data = contract_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_contract, field, value)
    
    db.commit()
    db.refresh(db_contract)
    return db_contract


def delete_contract(db: Session, contract_id: UUID) -> bool:
    """Delete contract and all related data."""
    db_contract = get_contract(db, contract_id)
    if not db_contract:
        return False
    
    # Delete related data (cascade should handle this, but explicit is better)
    db.query(Clause).filter(Clause.contract_id == contract_id).delete()
    db.query(Party).filter(Party.contract_id == contract_id).delete()
    db.query(ContractVersion).filter(ContractVersion.contract_id == contract_id).delete()
    db.query(Contract).filter(Contract.id == contract_id).delete()
    
    db.commit()
    return True


def get_contract_with_details(db: Session, contract_id: UUID) -> Optional[Contract]:
    """Get contract with all related data (versions, parties, clauses)."""
    return db.query(Contract).filter(Contract.id == contract_id).first()
