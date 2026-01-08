"""Contract version model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ContractVersion(Base):
    """Contract version storing parsed text and metadata."""
    
    __tablename__ = "contract_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    raw_text = Column(Text, nullable=False)  # Raw extracted text
    parsed_text = Column(Text, nullable=False)  # Cleaned/normalized text
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    contract = relationship("Contract", back_populates="versions")
    clauses = relationship("Clause", back_populates="version", cascade="all, delete-orphan")
