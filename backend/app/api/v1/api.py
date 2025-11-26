from fastapi import APIRouter

from app.api.v1.endpoints import bilingual, conflicts, contracts, versions

api_router = APIRouter()
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(conflicts.router, prefix="/conflicts", tags=["conflicts"])
api_router.include_router(bilingual.router, prefix="/bilingual", tags=["bilingual"])
api_router.include_router(versions.router, prefix="/versions", tags=["versions"])

