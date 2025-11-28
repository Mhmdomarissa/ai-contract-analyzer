from fastapi import APIRouter

from app.api.v1.endpoints import bilingual, contracts

api_router = APIRouter()
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(bilingual.router, prefix="/bilingual", tags=["bilingual"])
