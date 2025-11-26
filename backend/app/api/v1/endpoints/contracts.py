from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_db
from app.schemas.contract import ContractCreate, ContractResponse

router = APIRouter()


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/", response_model=ContractResponse, status_code=201)
def create_contract(contract_in: ContractCreate, db: Session = Depends(get_db)) -> ContractResponse:
    """Stub implementation that simulates contract creation."""
    _ = db  # placeholder to show dependency usage.
    return ContractResponse(
        id=0,
        title=contract_in.title,
        upload_date=datetime.now(tz=timezone.utc),
        status="PENDING",
    )

