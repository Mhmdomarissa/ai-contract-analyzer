from __future__ import annotations

from typing import Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db
from app.schemas.conflict import ClauseSummary, ConflictHighlightRead, ConflictRead
from app.schemas.contract import (
    ContractCreate,
    ContractRead,
    ContractVersionRead,
    ContractsPage,
)
from app.services import contracts as contract_service

router = APIRouter()


@router.post("/upload", response_model=ContractRead, status_code=201)
def upload_contract(contract_in: ContractCreate, db: Session = Depends(get_db)) -> ContractRead:
    contract = contract_service.create_contract_with_file_and_version(db, contract_in)
    db.commit()
    db.refresh(contract)
    latest = _get_latest_version(contract.versions)
    return _contract_to_schema(contract, latest)


@router.get("/", response_model=ContractsPage)
def list_contracts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ContractsPage:
    contracts, total = contract_service.list_contracts_paginated(db, limit=limit, offset=offset)
    items = [_contract_to_schema(contract, _get_latest_version(contract.versions)) for contract in contracts]
    return ContractsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{contract_id}", response_model=ContractRead)
def get_contract(contract_id: UUID, db: Session = Depends(get_db)) -> ContractRead:
    contract, latest = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _contract_to_schema(contract, latest)


@router.get("/{contract_id}/versions", response_model=list[ContractVersionRead])
def list_contract_versions(contract_id: UUID, db: Session = Depends(get_db)) -> list[ContractVersionRead]:
    contract, _ = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    versions = contract_service.list_contract_versions(db, contract_id)
    return [ContractVersionRead.model_validate(version, from_attributes=True) for version in versions]


@router.get("/{contract_id}/conflicts", response_model=list[ConflictRead])
def list_contract_conflicts(contract_id: UUID, db: Session = Depends(get_db)) -> list[ConflictRead]:
    contract, _ = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    conflicts = contract_service.list_conflicts_for_contract(db, contract_id)
    return [_conflict_to_schema(conflict) for conflict in conflicts]


def _get_latest_version(versions: Iterable) -> object | None:
    versions_list = list(versions)
    for version in versions_list:
        if getattr(version, "is_current", False):
            return version
    if versions_list:
        return max(versions_list, key=lambda v: v.created_at)
    return None


def _contract_to_schema(contract, latest_version) -> ContractRead:
    latest_schema = (
        ContractVersionRead.model_validate(latest_version, from_attributes=True)
        if latest_version
        else None
    )
    return ContractRead(
        id=contract.id,
        title=contract.title,
        status=contract.status,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        latest_version=latest_schema,
    )


def _conflict_to_schema(conflict) -> ConflictRead:
    left_clause = ClauseSummary.model_validate(conflict.left_clause, from_attributes=True)
    right_clause = ClauseSummary.model_validate(conflict.right_clause, from_attributes=True)
    highlights = [
        ConflictHighlightRead.model_validate(highlight, from_attributes=True)
        for highlight in conflict.highlights
    ]
    return ConflictRead(
        id=conflict.id,
        analysis_run_id=conflict.analysis_run_id,
        severity=conflict.severity,
        score=conflict.score,
        summary=conflict.summary,
        explanation=conflict.explanation,
        contract_version_id=conflict.contract_version_id,
        status=conflict.status,
        created_at=conflict.created_at,
        left_clause=left_clause,
        right_clause=right_clause,
        highlights=highlights,
    )
