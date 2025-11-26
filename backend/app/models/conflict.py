from sqlalchemy import Column, Integer

from app.db.base_class import Base


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True)
    # TODO: expand conflict model with relationships & metadata.

