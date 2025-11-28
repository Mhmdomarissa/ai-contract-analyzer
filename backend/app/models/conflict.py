from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class AnalysisRun(Base):
    """Task that runs AI analysis for a contract version."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False
    )

    contract_version: Mapped["ContractVersion"] = relationship(
        "ContractVersion", back_populates="analysis_runs"
    )
    conflicts: Mapped[list["Conflict"]] = relationship(
        "Conflict",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )


class Conflict(Base):
    """Represents a detected conflict between two clauses."""

    __tablename__ = "conflicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    summary: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(length=16), nullable=False, server_default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    left_clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )
    right_clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )

    analysis_run: Mapped[AnalysisRun] = relationship("AnalysisRun", back_populates="conflicts")
    contract_version: Mapped["ContractVersion"] = relationship(
        "ContractVersion", back_populates="conflicts"
    )
    left_clause: Mapped["Clause"] = relationship(
        "Clause",
        foreign_keys=[left_clause_id],
        back_populates="left_conflicts",
    )
    right_clause: Mapped["Clause"] = relationship(
        "Clause",
        foreign_keys=[right_clause_id],
        back_populates="right_conflicts",
    )
    highlights: Mapped[list["ConflictHighlight"]] = relationship(
        "ConflictHighlight",
        back_populates="conflict",
        cascade="all, delete-orphan",
    )


class ConflictHighlight(Base):
    """Highlights a particular text span implicated in a conflict."""

    __tablename__ = "conflict_highlights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conflict_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conflicts.id", ondelete="CASCADE"), nullable=False
    )
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
    )
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)

    conflict: Mapped[Conflict] = relationship("Conflict", back_populates="highlights")
    clause: Mapped["Clause"] = relationship("Clause", back_populates="highlights")
