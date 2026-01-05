from fastapi import APIRouter

from app.api.v1.endpoints import bilingual, contracts
from app.api.v1.endpoints import compare, batch_compare, chat

api_router = APIRouter()

# ============================================================================
# TEMPORARILY COMMENTED OUT - Original functionality preserved for later reuse
# ============================================================================
# api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
# api_router.include_router(bilingual.router, prefix="/bilingual", tags=["bilingual"])
# ============================================================================

# New temporary endpoints for testing
api_router.include_router(compare.router, prefix="/compare", tags=["compare"])
api_router.include_router(batch_compare.router, prefix="/compare", tags=["batch-compare"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
