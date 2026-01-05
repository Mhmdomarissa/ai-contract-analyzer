from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class ClauseGroup(Base):
    """Logical grouping of related clauses within a contract."""

    __tablename__ = "clause_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="clause_groups")
    clauses: Mapped[list["Clause"]] = relationship(
        "Clause",
        back_populates="clause_group",
        cascade="all, delete-orphan",
        order_by="Clause.order_index",
    )


class Clause(Base):
    """Represents a single clause extracted from a contract version."""

    __tablename__ = "clauses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False
    )
    clause_number: Mapped[str | None] = mapped_column(String(length=50))
    heading: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(String(length=32))
    clause_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clause_groups.id", ondelete="SET NULL")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    arabic_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_bilingual: Mapped[bool] = mapped_column(default=False, nullable=False)
    number_normalized: Mapped[str | None] = mapped_column(String(length=128))
    analysis_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_status: Mapped[str | None] = mapped_column(String(length=32), nullable=True)
    
    # Hierarchy fields
    parent_clause_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True
    )
    depth_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_override_clause: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contract_version: Mapped["ContractVersion"] = relationship(
        "ContractVersion", back_populates="clauses"
    )
    clause_group: Mapped[ClauseGroup | None] = relationship(
        "ClauseGroup", back_populates="clauses"
    )
    
    # Self-referencing relationship for hierarchy
    parent_clause: Mapped["Clause | None"] = relationship(
        "Clause",
        remote_side=[id],
        back_populates="child_clauses",
        foreign_keys=[parent_clause_id]
    )
    child_clauses: Mapped[list["Clause"]] = relationship(
        "Clause",
        back_populates="parent_clause",
        foreign_keys=[parent_clause_id],
        cascade="all, delete-orphan"
    )
    
    left_conflicts: Mapped[list["Conflict"]] = relationship(
        "Conflict",
        back_populates="left_clause",
        foreign_keys="[Conflict.left_clause_id]",
    )
    right_conflicts: Mapped[list["Conflict"]] = relationship(
        "Conflict",
        back_populates="right_clause",
        foreign_keys="[Conflict.right_clause_id]",
    )
    highlights: Mapped[list["ConflictHighlight"]] = relationship(
        "ConflictHighlight",
        back_populates="clause",
        cascade="all, delete-orphan",
    )
