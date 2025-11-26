from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["get_db", "get_current_user"]

