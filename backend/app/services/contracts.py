from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.clause import Clause
from app.models.conflict import AnalysisRun, Conflict, ConflictHighlight
from app.models.contract import Contract, ContractFile, ContractVersion
from app.schemas.contract import ContractCreate


@dataclass
class ConflictHighlightPayload:
    clause_id: UUID
    snippet: str
    start_char: int
    end_char: int


@dataclass
class ConflictPayload:
    severity: str
    explanation: str
    contract_version_id: UUID
    left_clause_id: UUID
    right_clause_id: UUID
    score: float | None = None
    summary: str | None = None
    status: str | None = None
    highlights: Sequence[ConflictHighlightPayload] = ()


def create_contract_with_file_and_version(db: Session, data: ContractCreate) -> Contract:
    """Persist a new contract, its backing file, and the initial version."""

    status = data.status or "DRAFT"
    contract = Contract(title=data.title, status=status)

    file_entry = ContractFile(
        storage_path=data.file.storage_path,
        file_name=data.file.file_name,
        mime_type=data.file.mime_type,
        file_size_bytes=data.file.file_size_bytes,
        contract=contract,
    )

    ContractVersion(
        contract=contract,
        file=file_entry,
        version_number=1,
        is_current=True,
    )

    db.add(contract)
    db.flush()
    return contract


def get_contract_with_latest_version(
    db: Session, contract_id: UUID
) -> tuple[Contract | None, ContractVersion | None]:
    stmt = (
        select(Contract)
        .options(
            selectinload(Contract.versions).selectinload(ContractVersion.file),
        )
        .where(Contract.id == contract_id)
    )
    contract = db.scalar(stmt)
    if not contract:
        return None, None

    latest = next((v for v in contract.versions if v.is_current), None)
    if latest is None and contract.versions:
        latest = max(contract.versions, key=lambda v: v.created_at)
    return contract, latest


def list_contracts_paginated(
    db: Session, *, limit: int, offset: int
) -> tuple[list[Contract], int]:
    stmt = (
        select(Contract)
        .options(selectinload(Contract.versions).selectinload(ContractVersion.file))
        .order_by(Contract.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    contracts = list(db.scalars(stmt))
    total = db.scalar(select(func.count()).select_from(Contract)) or 0
    return contracts, total


def list_contract_versions(db: Session, contract_id: UUID) -> list[ContractVersion]:
    stmt = (
        select(ContractVersion)
        .options(selectinload(ContractVersion.file))
        .where(ContractVersion.contract_id == contract_id)
        .order_by(ContractVersion.version_number)
    )
    return list(db.scalars(stmt))


def list_clauses_for_version(db: Session, contract_version_id: UUID) -> list[Clause]:
    stmt = (
        select(Clause)
        .where(Clause.contract_version_id == contract_version_id)
        .order_by(Clause.order_index)
    )
    return list(db.scalars(stmt))


def create_analysis_run_for_version(
    db: Session, *, contract_version_id: UUID, run_type: str, model_name: str
) -> AnalysisRun:
    run = AnalysisRun(
        contract_version_id=contract_version_id,
        type=run_type,
        model_name=model_name,
        status="PENDING",
    )
    db.add(run)
    db.flush()
    return run


def save_conflicts_for_run(
    db: Session,
    *,
    analysis_run: AnalysisRun,
    conflicts_payload: Sequence[ConflictPayload],
) -> list[Conflict]:
    saved: list[Conflict] = []
    for payload in conflicts_payload:
        conflict = Conflict(
            analysis_run=analysis_run,
            severity=payload.severity,
            explanation=payload.explanation,
            contract_version_id=payload.contract_version_id,
            left_clause_id=payload.left_clause_id,
            right_clause_id=payload.right_clause_id,
            score=payload.score,
            summary=payload.summary,
            status=payload.status or "OPEN",
        )
        for highlight in payload.highlights:
            conflict.highlights.append(
                ConflictHighlight(
                    clause_id=highlight.clause_id,
                    snippet=highlight.snippet,
                    start_char=highlight.start_char,
                    end_char=highlight.end_char,
                )
            )
        db.add(conflict)
        saved.append(conflict)

    db.flush()
    return saved


def list_conflicts_for_contract(db: Session, contract_id: UUID) -> list[Conflict]:
    stmt = (
        select(Conflict)
        .join(ContractVersion, Conflict.contract_version_id == ContractVersion.id)
        .options(
            selectinload(Conflict.left_clause),
            selectinload(Conflict.right_clause),
            selectinload(Conflict.highlights),
        )
        .where(ContractVersion.contract_id == contract_id)
        .order_by(Conflict.created_at.desc())
    )
    return list(db.scalars(stmt))
