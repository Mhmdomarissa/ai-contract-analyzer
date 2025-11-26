from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)


@app.get("/healthz", tags=["health"])
def root_health() -> dict[str, str]:
    """Basic health endpoint."""
    return {"status": "ok"}


app.include_router(api_router, prefix="/api/v1")

