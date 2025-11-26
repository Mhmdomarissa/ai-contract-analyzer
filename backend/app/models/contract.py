from sqlalchemy import Column, DateTime, Integer, String, func

from app.db.base_class import Base


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(length=255), nullable=False)
    upload_date = Column(DateTime(timezone=True), nullable=False, default=func.now())
    status = Column(String(length=50), nullable=False, default="PENDING")

