from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Contract(Base):
    """Represents a logical contract uploaded to the system."""

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(length=50), nullable=False, server_default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    files: Mapped[list["ContractFile"]] = relationship(
        "ContractFile",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ContractFile.uploaded_at",
    )
    versions: Mapped[list["ContractVersion"]] = relationship(
        "ContractVersion",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="desc(ContractVersion.created_at)",
    )
    clause_groups: Mapped[list["ClauseGroup"]] = relationship(
        "ClauseGroup",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ClauseGroup.created_at",
    )


class ContractFile(Base):
    """Represents a stored file that belongs to a contract."""

    __tablename__ = "contract_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(length=255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="files")
    versions: Mapped[list["ContractVersion"]] = relationship(
        "ContractVersion",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="ContractVersion.version_number",
    )


class ContractVersion(Base):
    """Concrete, versioned representation of a contract file."""

    __tablename__ = "contract_versions"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "version_number",
            name="uq_contract_version_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    is_current: Mapped[bool] = mapped_column(default=False, nullable=False)
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="versions")
    file: Mapped["ContractFile"] = relationship("ContractFile", back_populates="versions")
    clauses: Mapped[list["Clause"]] = relationship(
        "Clause",
        back_populates="contract_version",
        cascade="all, delete-orphan",
        order_by="Clause.order_index",
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        "AnalysisRun",
        back_populates="contract_version",
        cascade="all, delete-orphan",
        order_by="desc(AnalysisRun.started_at)",
    )
    conflicts: Mapped[list["Conflict"]] = relationship(
        "Conflict",
        back_populates="contract_version",
        cascade="all, delete-orphan",
        order_by="desc(Conflict.created_at)",
    )
