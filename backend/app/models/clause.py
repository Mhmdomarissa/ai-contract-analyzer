from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
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
    number_normalized: Mapped[str | None] = mapped_column(String(length=128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contract_version: Mapped["ContractVersion"] = relationship(
        "ContractVersion", back_populates="clauses"
    )
    clause_group: Mapped[ClauseGroup | None] = relationship(
        "ClauseGroup", back_populates="clauses"
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
