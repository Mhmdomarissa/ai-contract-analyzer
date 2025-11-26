from sqlalchemy import Column, Integer

from app.db.base_class import Base


class Clause(Base):
    __tablename__ = "clauses"

    id = Column(Integer, primary_key=True)
    # TODO: define clause fields and relationships.

