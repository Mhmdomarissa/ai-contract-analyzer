"""
Chat endpoint for direct interaction with Qwen2 model.

This endpoint provides a chatbot interface for testing and evaluating
the LLM's performance and behavior in real-time.
"""
import json
import logging
import time
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message model."""
    
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request model for chat."""
    
    message: str = Field(..., min_length=1, description="User's message")
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous messages in the conversation"
    )


class ChatResponse(BaseModel):
    """Response model for chat."""
    
    response: str = Field(..., description="Assistant's response")
    performance: Dict[str, Any] = Field(..., description="Performance metrics")


class PerformanceMetrics(BaseModel):
    """Performance metrics for chat response."""
    
    time_to_first_token: float = Field(..., description="Time to first token (seconds)")
    tokens_per_second: float = Field(..., description="Tokens per second")
    total_time: float = Field(..., description="Total response time (seconds)")
    total_tokens: int = Field(..., description="Total tokens generated")


async def _generate_chat_stream(
    message: str,
    conversation_history: List[ChatMessage],
    model: str = "qwen2.5:32b"
):
    """
    Generate streaming chat response with performance metrics.
    
    Args:
        message: User's current message
        conversation_history: Previous conversation messages
        model: Model to use
        
    Yields:
        SSE-formatted chat chunks and performance data
    """
    ollama_url = settings.OLLAMA_URL.rstrip("/")
    endpoint = f"{ollama_url}/api/generate"
    
    # Build conversation context
    context = ""
    for msg in conversation_history[-10:]:  # Keep last 10 messages for context
        context += f"{msg.role.capitalize()}: {msg.content}\n"
    
    full_prompt = f"""{context}User: {message}
Assistant:"""
    
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": True,
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
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            
                            if "response" in chunk:
                                chunk_text = chunk["response"]
                                
                                if first_token_time is None:
                                    first_token_time = time.time() - start_time
                                    # Send time to first token metric
                                    yield f"data: {json.dumps({'type': 'metric', 'metric': 'time_to_first_token', 'value': first_token_time})}\n\n"
                                
                                response_text += chunk_text
                                token_count += 1
                                
                                # Send token chunk
                                yield f"data: {json.dumps({'type': 'token', 'content': chunk_text})}\n\n"
                            
                            if chunk.get("done", False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
        
        total_time = time.time() - start_time
        tokens_per_second = token_count / total_time if total_time > 0 else 0
        
        # Send final performance metrics
        performance = {
            "time_to_first_token": first_token_time or total_time,
            "tokens_per_second": tokens_per_second,
            "total_time": total_time,
            "total_tokens": token_count
        }
        
        yield f"data: {json.dumps({'type': 'complete', 'performance': performance, 'response': response_text})}\n\n"
        
        logger.info(f"Chat response completed - Time: {total_time:.2f}s, Tokens: {token_count}, TPS: {tokens_per_second:.2f}")
        
    except httpx.TimeoutException:
        error_data = {"type": "error", "message": "Request timed out after 5 minutes"}
        yield f"data: {json.dumps(error_data)}\n\n"
    except httpx.HTTPStatusError as e:
        error_data = {"type": "error", "message": f"LLM API error {e.response.status_code}: {e.response.text}"}
        yield f"data: {json.dumps(error_data)}\n\n"
    except Exception as e:
        error_data = {"type": "error", "message": f"Failed to communicate with LLM: {str(e)}"}
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Chat with Qwen2 model with streaming response.
    
    This endpoint streams the response token-by-token and provides real-time
    performance metrics including time to first token, tokens per second,
    and total response time.
    
    SSE event types:
    - metric: Performance metric update (time_to_first_token)
    - token: Individual response token/chunk
    - complete: Final response with full performance metrics
    - error: Error message if something goes wrong
    
    Args:
        request: Contains user message and conversation history
        
    Returns:
        StreamingResponse with SSE events
    """
    logger.info(f"Chat request received: {request.message[:50]}...")
    
    return StreamingResponse(
        _generate_chat_stream(request.message, request.conversation_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest) -> ChatResponse:
    """
    Chat with Qwen2 model (non-streaming version).
    
    This is a simpler version that returns the complete response at once
    along with performance metrics.
    
    Args:
        request: Contains user message and conversation history
        
    Returns:
        Complete chat response with performance metrics
    """
    logger.info(f"Chat message request: {request.message[:50]}...")
    
    ollama_url = settings.OLLAMA_URL.rstrip("/")
    endpoint = f"{ollama_url}/api/generate"
    
    # Build conversation context
    context = ""
    for msg in request.conversation_history[-10:]:
        context += f"{msg.role.capitalize()}: {msg.content}\n"
    
    full_prompt = f"""{context}User: {request.message}
Assistant:"""
    
    payload = {
        "model": "qwen2.5:32b",
        "prompt": full_prompt,
        "stream": True,
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
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
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
                                token_count += 1
                            
                            if chunk.get("done", False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
        
        total_time = time.time() - start_time
        tokens_per_second = token_count / total_time if total_time > 0 else 0
        
        performance = {
            "time_to_first_token": first_token_time or total_time,
            "tokens_per_second": tokens_per_second,
            "total_time": total_time,
            "total_tokens": token_count
        }
        
        logger.info(f"✅ Chat completed - Time: {total_time:.2f}s, Tokens: {token_count}, TPS: {tokens_per_second:.2f}")
        
        return ChatResponse(
            response=response_text,
            performance=performance
        )
        
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timed out after 5 minutes")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to communicate with LLM: {str(e)}")
