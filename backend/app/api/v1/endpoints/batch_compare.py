"""
Endpoint for comparing one clause against multiple clauses (1 → N comparison).

This endpoint streams results as they are computed, allowing the UI to display
partial results without waiting for all comparisons to complete.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class BatchComparisonRequest(BaseModel):
    """Request model for batch clause comparison."""
    
    source_clause: str = Field(..., min_length=1, description="Source clause to compare against all others")
    target_clauses: List[str] = Field(..., min_items=1, max_items=100, description="List of target clauses to compare")
    prompt: str = Field(
        ..., 
        min_length=1, 
        description="The prompt/instruction for the LLM on how to compare clauses"
    )


class ComparisonResult(BaseModel):
    """Individual comparison result."""
    
    index: int = Field(..., description="Index of the target clause")
    conflict: bool = Field(..., description="Whether a conflict was detected")
    explanation: str = Field(..., description="LLM's explanation")
    severity: str = Field(default="Unknown", description="Conflict severity (High/Medium/Low)")
    performance: Dict[str, Any] = Field(..., description="Performance metrics")


class PerformanceMetrics(BaseModel):
    """Performance metrics for LLM call."""
    
    time_to_first_token: float = Field(..., description="Time to receive first token (seconds)")
    tokens_per_second: float = Field(..., description="Average tokens per second")
    total_time: float = Field(..., description="Total response time (seconds)")
    total_tokens: int = Field(..., description="Total tokens generated")


async def _call_ollama_with_metrics(prompt: str, model: str = "qwen2.5:32b") -> tuple[str, PerformanceMetrics]:
    """
    Call Ollama API and track performance metrics.
    
    Args:
        prompt: The complete prompt to send to the LLM
        model: The model name to use
        
    Returns:
        Tuple of (response text, performance metrics)
    """
    ollama_url = settings.OLLAMA_URL.rstrip("/")
    endpoint = f"{ollama_url}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,  # Enable streaming for token tracking
        "keep_alive": "30m",  # Keep model in memory for 30 minutes
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        }
    }
    
    start_time = time.time()
    first_token_time = None
    response_text = ""
    token_count = 0
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            async with client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            
                            if "response" in chunk:
                                if first_token_time is None:
                                    first_token_time = time.time() - start_time
                                
                                response_text += chunk["response"]
                                token_count += 1  # Approximate token count
                            
                            if chunk.get("done", False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
            
            total_time = time.time() - start_time
            
            # Calculate metrics
            metrics = PerformanceMetrics(
                time_to_first_token=first_token_time or total_time,
                tokens_per_second=token_count / total_time if total_time > 0 else 0,
                total_time=total_time,
                total_tokens=token_count
            )
            
            return response_text, metrics
            
        except httpx.TimeoutException:
            raise Exception("LLM request timed out after 5 minutes")
        except httpx.HTTPStatusError as e:
            raise Exception(f"LLM API returned error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise Exception(f"Failed to communicate with LLM: {str(e)}")


async def _compare_single_clause(
    source_clause: str,
    target_clause: str,
    prompt: str,
    index: int
) -> ComparisonResult:
    """
    Compare source clause against a single target clause.
    
    Args:
        source_clause: The source clause
        target_clause: The target clause to compare
        prompt: The comparison prompt
        index: Index of the target clause
        
    Returns:
        ComparisonResult with conflict detection and metrics
    """
    full_prompt = f"""{prompt}

**Clause A (Source):**
{source_clause}

**Clause B (Target #{index + 1}):**
{target_clause}

Please analyze these two clauses according to the instructions above.
Format your response to clearly indicate:
1. Conflict: Yes/No
2. Explanation
3. Severity: High/Medium/Low"""
    
    try:
        response_text, metrics = await _call_ollama_with_metrics(full_prompt)
        
        # Parse response to extract conflict and severity
        response_lower = response_text.lower()
        conflict = "conflict: yes" in response_lower or "a conflict exists" in response_lower
        
        severity = "Unknown"
        if "severity: high" in response_lower or "high severity" in response_lower:
            severity = "High"
        elif "severity: medium" in response_lower or "medium severity" in response_lower:
            severity = "Medium"
        elif "severity: low" in response_lower or "low severity" in response_lower:
            severity = "Low"
        
        return ComparisonResult(
            index=index,
            conflict=conflict,
            explanation=response_text,
            severity=severity,
            performance={
                "time_to_first_token": metrics.time_to_first_token,
                "tokens_per_second": metrics.tokens_per_second,
                "total_time": metrics.total_time,
                "total_tokens": metrics.total_tokens
            }
        )
        
    except Exception as e:
        logger.error(f"Error comparing clause {index}: {e}")
        return ComparisonResult(
            index=index,
            conflict=False,
            explanation=f"Error: {str(e)}",
            severity="Error",
            performance={
                "time_to_first_token": 0,
                "tokens_per_second": 0,
                "total_time": 0,
                "total_tokens": 0
            }
        )


async def _generate_comparison_stream(request: BatchComparisonRequest):
    """
    Generator that yields comparison results as Server-Sent Events.
    
    Args:
        request: The batch comparison request
        
    Yields:
        SSE-formatted comparison results
    """
    logger.info(f"Starting batch comparison: 1 source clause vs {len(request.target_clauses)} target clauses")
    
    # Send initial status
    yield f"data: {json.dumps({'type': 'status', 'message': 'Starting comparison...', 'total': len(request.target_clauses)})}\n\n"
    
    # Process each comparison sequentially to avoid overloading the LLM
    for idx, target_clause in enumerate(request.target_clauses):
        logger.info(f"Comparing clause {idx + 1}/{len(request.target_clauses)}")
        
        result = await _compare_single_clause(
            request.source_clause,
            target_clause,
            request.prompt,
            idx
        )
        
        # Send result as SSE
        result_data = {
            'type': 'result',
            'data': result.dict()
        }
        yield f"data: {json.dumps(result_data)}\n\n"
    
    # Send completion status
    logger.info("Batch comparison completed")
    yield f"data: {json.dumps({'type': 'complete', 'message': 'All comparisons completed'})}\n\n"


@router.post("/batch")
async def compare_one_to_many(request: BatchComparisonRequest) -> StreamingResponse:
    """
    Compare one source clause against multiple target clauses.
    
    This endpoint streams results as they are computed, allowing the UI to display
    partial results without waiting for all comparisons to complete.
    
    The response is sent as Server-Sent Events (SSE) with the following event types:
    - status: Initial status and progress updates
    - result: Individual comparison result
    - complete: All comparisons finished
    
    Args:
        request: Contains source_clause, list of target_clauses, and comparison prompt
        
    Returns:
        StreamingResponse with SSE events
    """
    return StreamingResponse(
        _generate_comparison_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
