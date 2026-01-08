"""Clause model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Clause(Base):
    """Clause model storing extracted contract clauses."""
    
    __tablename__ = "clauses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Clause identifiers
    clause_number = Column(String, nullable=False, index=True)  # e.g., "1.", "1.a)"
    uuid_from_extractor = Column(String, nullable=True)  # UUID from extraction script as string
    
    # Clause content
    content = Column(Text, nullable=False)
    
    # Hierarchy
    parent_clause_id = Column(UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=True, index=True)
    order_index = Column(Integer, nullable=False, index=True)  # Preserve original order
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    contract = relationship("Contract", back_populates="clauses")
    version = relationship("ContractVersion", back_populates="clauses")
    parent = relationship("Clause", remote_side=[id], backref="sub_clauses")
