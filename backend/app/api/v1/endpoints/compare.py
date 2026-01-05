"""
Temporary endpoint for comparing two contract clauses using LLM.

This is a simplified, isolated endpoint that directly compares two clauses
using a custom prompt and the hosted Qwen2 model.
"""
import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ClauseComparisonRequest(BaseModel):
    """Request model for clause comparison."""
    
    clause_a: str = Field(..., min_length=1, description="First contract clause to compare")
    clause_b: str = Field(..., min_length=1, description="Second contract clause to compare")
    prompt: str = Field(
        ..., 
        min_length=1, 
        description="The prompt/instruction for the LLM on how to compare the clauses"
    )


class ClauseComparisonResponse(BaseModel):
    """Response model for clause comparison."""
    
    response: str = Field(..., description="LLM's analysis of the two clauses")
    model: str = Field(..., description="Model used for analysis")


@router.post("/clauses", response_model=ClauseComparisonResponse)
async def compare_clauses(request: ClauseComparisonRequest) -> ClauseComparisonResponse:
    """
    Compare two contract clauses using the LLM with a custom prompt.
    
    This endpoint sends both clauses along with a user-provided prompt to the
    Qwen2.5:32b model hosted on Ollama and returns the LLM's analysis.
    
    Args:
        request: Contains clause_a, clause_b, and the comparison prompt
        
    Returns:
        The LLM's response analyzing the clauses based on the prompt
        
    Raises:
        HTTPException: If LLM communication fails
    """
    logger.info("Comparing two clauses with custom prompt")
    logger.debug(f"Clause A length: {len(request.clause_a)} chars")
    logger.debug(f"Clause B length: {len(request.clause_b)} chars")
    logger.debug(f"Prompt: {request.prompt[:100]}...")
    
    # Build the full prompt for the LLM
    full_prompt = f"""{request.prompt}

**Clause A:**
{request.clause_a}

**Clause B:**
{request.clause_b}

Please analyze these two clauses according to the instructions above."""
    
    # Call the Ollama LLM
    try:
        ollama_response = await _call_ollama(full_prompt)
        
        logger.info("✅ LLM comparison completed successfully")
        
        return ClauseComparisonResponse(
            response=ollama_response,
            model="qwen2.5:32b"
        )
        
    except Exception as e:
        logger.error(f"❌ Error calling LLM: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get LLM response: {str(e)}"
        )


async def _call_ollama(prompt: str, model: str = "qwen2.5:32b") -> str:
    """
    Call the Ollama API with the given prompt.
    
    Args:
        prompt: The complete prompt to send to the LLM
        model: The model name to use (default: qwen2.5:32b)
        
    Returns:
        The LLM's text response
        
    Raises:
        Exception: If the API call fails
    """
    ollama_url = settings.OLLAMA_URL.rstrip("/")
    endpoint = f"{ollama_url}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",  # Keep model in memory for 30 minutes
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        }
    }
    
    logger.debug(f"Calling Ollama at {endpoint}")
    
    async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout
        try:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if "response" not in result:
                raise ValueError(f"Unexpected Ollama response format: {result}")
            
            return result["response"]
            
        except httpx.TimeoutException:
            raise Exception("LLM request timed out after 5 minutes")
        except httpx.HTTPStatusError as e:
            raise Exception(f"LLM API returned error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise Exception(f"Failed to communicate with LLM: {str(e)}")
