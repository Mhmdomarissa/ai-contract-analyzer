"""
Endpoint for comparing all clauses against all other clauses (N → N comparison).

This endpoint generates unique pairs and streams results as they are computed,
allowing the UI to display partial results without waiting for all comparisons.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import json

from app.core.config import settings

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent LLM calls (avoid overloading the LLM server)
# With 2 concurrent calls, we can process 2 comparisons simultaneously
MAX_CONCURRENT_LLM_CALLS = 2
llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

router = APIRouter()


class AllVsAllComparisonRequest(BaseModel):
    """Request model for all-vs-all clause comparison."""
    
    clauses: List[str] = Field(..., min_items=2, max_items=50, description="List of clauses to compare against each other")
    pair_prompt: str = Field(
        ..., 
        min_length=1, 
        description="The prompt for comparing two different clauses (pair check)"
    )
    self_prompt: str = Field(
        ..., 
        min_length=1, 
        description="The prompt for checking a clause against itself (self-consistency check)"
    )


class PairComparisonResult(BaseModel):
    """Result for one pair comparison."""
    
    clause_i_index: int = Field(..., description="Index of first clause in pair")
    clause_j_index: int = Field(..., description="Index of second clause in pair")
    is_self_check: bool = Field(..., description="Whether this is a self-consistency check (i==j)")
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


def _generate_all_pairs(n: int) -> List[Tuple[int, int]]:
    """
    Generate all pairs including self-checks (i, i) and pair-checks (i, j) where i < j.
    
    For n clauses, this generates:
    - n self-checks: (0,0), (1,1), ..., (n-1,n-1)
    - n*(n-1)/2 pair-checks: (0,1), (0,2), ...
    
    Total: n + n*(n-1)/2 = n*(n+1)/2 comparisons
    
    Example for n=3:
    Self-checks: (0,0), (1,1), (2,2)
    Pair-checks: (0,1), (0,2), (1,2)
    Total: 6 comparisons
    
    Args:
        n: Number of clauses
        
    Returns:
        List of (i, j) tuples where i <= j
    """
    pairs = []
    # Add self-checks first
    for i in range(n):
        pairs.append((i, i))
    # Add pair-checks
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((i, j))
    return pairs


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


async def _compare_clause_pair(
    clause_i: str,
    clause_j: str,
    prompt: str,
    i_index: int,
    j_index: int,
    is_self_check: bool = False
) -> PairComparisonResult:
    """
    Compare two clauses against each other, or check a clause for self-consistency.
    
    Args:
        clause_i: First clause (or the only clause for self-check)
        clause_j: Second clause (same as clause_i for self-check)
        prompt: The comparison prompt (different for self-check vs pair-check)
        i_index: Index of first clause
        j_index: Index of second clause (same as i_index for self-check)
        is_self_check: Whether this is a self-consistency check
        
    Returns:
        PairComparisonResult with conflict detection and metrics
    """
    if is_self_check:
        # Self-consistency check prompt
        full_prompt = f"""{prompt}

**Clause {i_index + 1}:**
{clause_i}

Please analyze this clause according to the instructions above.
Format your response to clearly indicate:
1. Conflict: Yes/No
2. Explanation
3. Severity: High/Medium/Low"""
    else:
        # Pair comparison prompt
        full_prompt = f"""{prompt}

**Clause {i_index + 1}:**
{clause_i}

**Clause {j_index + 1}:**
{clause_j}

Please analyze these two clauses according to the instructions above.
Format your response to clearly indicate:
1. Conflict: Yes/No
2. Explanation
3. Severity: High/Medium/Low"""
    
    try:
        # Use semaphore to limit concurrent LLM calls
        async with llm_semaphore:
            response_text, metrics = await _call_ollama_with_metrics(full_prompt)
        
        # Parse response to extract conflict and severity - More robust detection
        response_lower = response_text.lower()
        
        # PRIORITY 1: Check for structured format (most reliable)
        structured_conflict_yes = [
            "**conflict:** yes",
            "**conflict: yes",
            "conflict: yes",
            "conflict:yes",
        ]
        
        structured_conflict_no = [
            "**conflict:** no",
            "**conflict: no", 
            "conflict: no",
            "conflict:no",
        ]
        
        # Check structured format first
        has_structured_yes = any(indicator in response_lower for indicator in structured_conflict_yes)
        has_structured_no = any(indicator in response_lower for indicator in structured_conflict_no)
        
        # PRIORITY 2: Check for explicit phrases (if no structured format found)
        explicit_conflict = [
            "there is a conflict",
            "a conflict exists",
            "conflicts exist",
            "this creates a conflict",
            "creates a direct conflict"
        ]
        
        explicit_no_conflict = [
            "no conflict",
            "no conflicts",
            "does not conflict",
            "not conflict",
            "there is no conflict"
        ]
        
        has_explicit_yes = any(phrase in response_lower for phrase in explicit_conflict)
        has_explicit_no = any(phrase in response_lower for phrase in explicit_no_conflict)
        
        # Determine conflict with priority:
        # 1. Structured format wins (highest priority)
        # 2. Explicit phrases (medium priority)
        # 3. General conflict words (lowest priority - avoid false positives)
        if has_structured_yes or has_structured_no:
            conflict = has_structured_yes and not has_structured_no
        elif has_explicit_yes or has_explicit_no:
            conflict = has_explicit_yes and not has_explicit_no
        else:
            # Fallback: look for general conflict indicators (but be careful)
            general_conflict = ["contradiction", "contradicts", "incompatible with"]
            conflict = any(word in response_lower for word in general_conflict)
        
        # Log for debugging
        logger.info(f"Conflict detection for clause {i_index} vs {j_index}:")
        logger.info(f"  Response snippet: {response_text[:150]}...")
        logger.info(f"  Structured YES: {has_structured_yes}, Structured NO: {has_structured_no}")
        logger.info(f"  Explicit YES: {has_explicit_yes}, Explicit NO: {has_explicit_no}")
        logger.info(f"  Final decision: {'CONFLICT' if conflict else 'NO CONFLICT'}")
        
        severity = "Unknown"
        if "severity: high" in response_lower or "high severity" in response_lower:
            severity = "High"
        elif "severity: medium" in response_lower or "medium severity" in response_lower:
            severity = "Medium"
        elif "severity: low" in response_lower or "low severity" in response_lower:
            severity = "Low"
        
        return PairComparisonResult(
            clause_i_index=i_index,
            clause_j_index=j_index,
            is_self_check=is_self_check,
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
        logger.error(f"Error comparing clause {i_index} vs {j_index}: {e}")
        return PairComparisonResult(
            clause_i_index=i_index,
            clause_j_index=j_index,
            is_self_check=is_self_check,
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


async def _generate_all_vs_all_stream(request: AllVsAllComparisonRequest):
    """
    Generator that yields pair comparison results as Server-Sent Events.
    Includes both self-checks (clause vs itself) and pair-checks (clause vs other).
    
    Uses concurrent processing with semaphore to limit parallel LLM calls.
    Processes in batches for better performance while respecting LLM server limits.
    
    Args:
        request: The all-vs-all comparison request
        
    Yields:
        SSE-formatted comparison results
    """
    n = len(request.clauses)
    pairs = _generate_all_pairs(n)
    total_comparisons = len(pairs)
    
    # Batch size for concurrent processing (must be >= MAX_CONCURRENT_LLM_CALLS)
    BATCH_SIZE = max(10, MAX_CONCURRENT_LLM_CALLS * 2)
    
    logger.info(f"Starting all-vs-all comparison: {n} clauses = {total_comparisons} comparisons")
    logger.info(f"Processing in batches of {BATCH_SIZE} with max {MAX_CONCURRENT_LLM_CALLS} concurrent LLM calls")
    
    # Send initial status
    initial_status = {
        'type': 'status', 
        'message': f'Starting {total_comparisons} comparisons...', 
        'total': total_comparisons, 
        'clause_count': n,
        'batch_size': BATCH_SIZE,
        'max_concurrent': MAX_CONCURRENT_LLM_CALLS
    }
    yield f"data: {json.dumps(initial_status)}\n\n"
    
    # Track streaming statistics
    results_sent = 0
    conflicts_found = 0
    errors_encountered = 0
    start_time = time.time()
    
    try:
        # Process pairs in batches for better performance
        for batch_start in range(0, len(pairs), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(pairs))
            batch_pairs = pairs[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//BATCH_SIZE + 1}: pairs {batch_start+1}-{batch_end}/{total_comparisons}")
            
            # Create tasks for this batch
            tasks = []
            for pair_index_in_batch, (i, j) in enumerate(batch_pairs):
                pair_index = batch_start + pair_index_in_batch
                is_self_check = (i == j)
                prompt = request.self_prompt if is_self_check else request.pair_prompt
                
                task = _compare_clause_pair(
                    request.clauses[i],
                    request.clauses[j],
                    prompt,
                    i,
                    j,
                    is_self_check
                )
                tasks.append((pair_index, i, j, is_self_check, task))
            
            # Execute batch concurrently (limited by semaphore)
            batch_results = await asyncio.gather(*[task for _, _, _, _, task in tasks], return_exceptions=True)
            
            # Yield results as they complete
            for (pair_index, i, j, is_self_check, _), result in zip(tasks, batch_results):
                try:
                    if isinstance(result, Exception):
                        # Handle exception from gather
                        error_msg = f"Failed to compare clause {i+1} vs {j+1}: {str(result)}"
                        logger.error(error_msg, exc_info=result)
                        errors_encountered += 1
                        
                        result = PairComparisonResult(
                            clause_i_index=i,
                            clause_j_index=j,
                            is_self_check=is_self_check,
                            conflict=False,
                            explanation=f"Error during comparison: {str(result)}",
                            severity="Error",
                            performance={
                                "time_to_first_token": 0,
                                "tokens_per_second": 0,
                                "total_time": 0,
                                "total_tokens": 0
                            }
                        )
                    else:
                        # Successful result
                        if result.conflict:
                            conflicts_found += 1
                        
                        if result.severity == "Error":
                            errors_encountered += 1
                    
                    # Send result as SSE
                    result_data = {
                        'type': 'result',
                        'data': result.dict(),
                        'progress': {
                            'current': pair_index + 1,
                            'total': total_comparisons
                        }
                    }
                    
                    results_sent += 1
                    yield f"data: {json.dumps(result_data)}\n\n"
                    
                except Exception as e:
                    logger.error(f"Error processing result for pair {i+1},{j+1}: {e}")
                    errors_encountered += 1
            
            # Log batch completion
            elapsed = time.time() - start_time
            avg_time = elapsed / results_sent if results_sent > 0 else 0
            remaining = (total_comparisons - results_sent) * avg_time
            logger.info(f"Batch complete: {results_sent}/{total_comparisons} results sent, "
                       f"{conflicts_found} conflicts, ETA: {remaining/60:.1f}min")
        
        # Send completion status
        total_time = time.time() - start_time
        completion_msg = (f"All-vs-all comparison completed: {total_comparisons} comparisons, "
                         f"{conflicts_found} conflicts found, {errors_encountered} errors, "
                         f"{results_sent} results sent in {total_time/60:.1f}min")
        logger.info(completion_msg)
        
        completion_data = {
            'type': 'complete', 
            'message': 'All comparisons completed', 
            'total_comparisons': total_comparisons,
            'conflicts_found': conflicts_found,
            'errors_encountered': errors_encountered,
            'results_sent': results_sent,
            'total_time_minutes': total_time / 60
        }
        yield f"data: {json.dumps(completion_data)}\n\n"
        
    except Exception as e:
        # Fatal error - send error event and stop
        error_msg = f"Fatal error in comparison stream: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        error_data = {
            'type': 'error',
            'message': error_msg,
            'results_sent': results_sent,
            'conflicts_found': conflicts_found
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/all-vs-all")
async def compare_all_vs_all(request: AllVsAllComparisonRequest) -> StreamingResponse:
    """
    Compare all clauses against all other clauses (N → N).
    
    This endpoint generates unique pairs (i, j) where i < j and compares each pair.
    Includes self-checks (i, i) and pair-checks (i, j) where i < j.
    For N clauses, this generates N*(N+1)/2 total comparisons.
    
    Results are streamed as they are computed via Server-Sent Events (SSE):
    - status: Initial status and metadata
    - result: Individual pair comparison result
    - complete: All comparisons finished
    - error: Error encountered during processing
    
    Validation:
    - At least 2 clauses required
    - Maximum 50 clauses to prevent resource exhaustion
    - Each clause must be non-empty after stripping whitespace
    - Prompts must be non-empty
    
    Example for 4 clauses:
    - Self-checks: (0,0), (1,1), (2,2), (3,3) = 4
    - Pair-checks: (0,1), (0,2), (0,3), (1,2), (1,3), (2,3) = 6
    Total: 10 comparisons
    
    Args:
        request: Contains list of clauses and comparison prompts
        
    Returns:
        StreamingResponse with SSE events
        
    Raises:
        HTTPException: If validation fails
    """
    # Validate clauses
    n = len(request.clauses)
    
    # Check for empty clauses
    empty_indices = [i for i, clause in enumerate(request.clauses) if not clause.strip()]
    if empty_indices:
        raise HTTPException(
            status_code=400,
            detail=f"Empty clauses found at indices: {empty_indices}. All clauses must contain text."
        )
    
    # Check for very long clauses (> 50KB)
    large_clauses = [i for i, clause in enumerate(request.clauses) if len(clause) > 50000]
    if large_clauses:
        raise HTTPException(
            status_code=400,
            detail=f"Clauses at indices {large_clauses} exceed 50KB. Please shorten them."
        )
    
    # Calculate expected comparisons
    expected_comparisons = n * (n + 1) // 2  # n self-checks + n*(n-1)/2 pair-checks
    
    # Warn if this is a large comparison
    if n > 100:
        logger.warning(f"Large comparison requested: {n} clauses = {expected_comparisons} comparisons (estimated time: {expected_comparisons * 2.5 / 60:.1f} minutes)")
    
    logger.info(f"All-vs-all comparison requested: {n} clauses = {expected_comparisons} comparisons ({n} self-checks + {n*(n-1)//2} pair-checks)")
    
    return StreamingResponse(
        _generate_all_vs_all_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
