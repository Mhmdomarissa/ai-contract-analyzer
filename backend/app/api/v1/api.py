"""
API Router for Testing Lab - Clause Comparison & Analysis

This module defines the API routes for the Contract Clause Testing Lab:
- 1-to-1 clause comparison
- 1-to-N batch comparison
- N-to-N all-vs-all comparison (with self-check)
- AI chatbot for clause analysis
"""
from fastapi import APIRouter

from app.api.v1.endpoints import compare, batch_compare, chat, all_vs_all_compare

api_router = APIRouter()

# Testing Lab endpoints
api_router.include_router(compare.router, prefix="/compare", tags=["1-to-1-compare"])
api_router.include_router(batch_compare.router, prefix="/compare", tags=["1-to-N-compare"])
api_router.include_router(all_vs_all_compare.router, prefix="/compare", tags=["N-to-N-compare"])
api_router.include_router(chat.router, prefix="/chat", tags=["chatbot"])

