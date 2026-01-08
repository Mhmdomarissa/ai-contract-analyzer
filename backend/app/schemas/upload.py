"""Upload progress schemas."""
from typing import Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime


class ProgressEvent(BaseModel):
    """Progress event for SSE streaming."""
    stage: str
    message: str
    progress: int  # 0-100
    timestamp: str
    data: Dict[str, Any] = {}


class UploadResponse(BaseModel):
    """Upload completion response."""
    contract_id: str
    status: str
    message: str
    clause_count: int
    party_count: int
