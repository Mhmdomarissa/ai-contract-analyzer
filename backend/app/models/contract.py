"""Contract model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base_class import Base


class ContractStatus(str, enum.Enum):
    """Contract processing status."""
    UPLOADING = "uploading"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    IDENTIFYING_PARTIES = "identifying_parties"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


class Contract(Base):
    """Contract model storing uploaded contract files."""
    
    __tablename__ = "contracts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False, index=True)
    original_filename = Column(String, nullable=False)  # Original uploaded filename
    file_type = Column(String, nullable=False)  # pdf, docx, txt, etc.
    file_size = Column(Integer, nullable=False)  # File size in bytes
    status = Column(
        SQLEnum(ContractStatus),
        nullable=False,
        default=ContractStatus.UPLOADING,
        index=True
    )
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    versions = relationship("ContractVersion", back_populates="contract", cascade="all, delete-orphan")
    parties = relationship("Party", back_populates="contract", cascade="all, delete-orphan")
    clauses = relationship("Clause", back_populates="contract", cascade="all, delete-orphan")
