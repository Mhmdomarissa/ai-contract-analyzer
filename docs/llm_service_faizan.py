import json
import logging
import os
import re
from typing import Any, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.clause_extractor import extract_clauses as python_extract_clauses

logger = logging.getLogger(__name__)

# Configurable chunk size
MAX_CHUNK_SIZE = int(os.getenv("LLM_MAX_CHUNK_SIZE", "12000"))

# Pattern to detect numbered clause sections
CLAUSE_NUMBER_PATTERN = re.compile(
    r"(?<!\S)("
    r"\d+(?:\.\d+)*\.|\([a-zA-Z]\)"
    r")\s+"
)


class LLMService:
    """Wrapper for LLM endpoints (e.g., Ollama) with multi-step analysis."""

    def __init__(self, base_url: str, model: str = "qwen2.5:32b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def snap_to_word_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
        """
        Adjust start and end indices to fall on word boundaries.
        
        This prevents cutting clauses in the middle of words.
        
        Args:
            text: The full contract text
            start: Proposed start index
            end: Proposed end index (exclusive)
            
        Returns:
            Tuple of (adjusted_start, adjusted_end)
        """
        n = len(text)

        # Clamp indices into [0, n]
        start = max(0, min(start, n))
        end = max(0, min(end, n))

        # Move start left until previous char is non-alphanumeric (whitespace/punct) or start of text
        while start > 0 and text[start - 1].isalnum():
            start -= 1

        # Move end right until last char is non-alphanumeric (whitespace/punct) or end of text
        while end < n and end > 0 and text[end - 1].isalnum():
            end += 1

        return start, min(end, n)

    @staticmethod
    def split_multi_numbered_clause(text: str) -> list[str]:
        """
        If a clause text contains multiple numbered subsections like '9. ... 10. ...',
        split it into separate pieces at each numbering marker.
        
        This ensures that if the LLM incorrectly groups multiple numbered sections
        into one clause, we split them back out.
        
        Args:
            text: The clause text to check and potentially split
            
        Returns:
            List of clause segments (will be [text] if no split needed)
        """
        parts = []
        last_idx = 0

        for match in CLAUSE_NUMBER_PATTERN.finditer(text):
            start = match.start(1)  # start of the actual number token
            if start > last_idx:
                segment = text[last_idx:start].strip()
                if segment:
                    parts.append(segment)
            last_idx = start

        final_seg = text[last_idx:].strip()
        if final_seg:
            parts.append(final_seg)

        return parts if len(parts) > 1 else [text]

    async def extract_clauses(self, text: str) -> List[dict]:
        """
        Step 1: Extract clauses from the text using Python-based extraction.
        Fast, accurate, and deterministic - no LLM calls needed.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for clause extraction.")
            return []

        logger.info(
            "Starting Python-based clause extraction. Total chars: %s",
            len(text),
        )
        logger.info("First 200 chars preview: %s", text[:200].replace("\n", " "))
        logger.info("Last 200 chars preview: %s", text[-200:].replace("\n", " "))
        
        try:
            # Use Python-based extractor (fast, no LLM calls)
            clauses = python_extract_clauses(text, start_index=1)
            
            # Post-process: ensure text is extracted from original text using indices
            # This ensures 100% accuracy - exact text from original document
            normalized_text = text.replace("\r\n", "\n").strip()
            processed_clauses = []
            
            for clause in clauses:
                start_char = clause.get("start_char", 0)
                end_char = clause.get("end_char", 0)
                
                # Validate indices
                if start_char < 0 or end_char > len(normalized_text) or start_char >= end_char:
                    logger.warning(f"Skipping clause {clause.get('id')}: invalid range [{start_char}, {end_char})")
                    continue
                
                # Re-extract text from normalized text to ensure exact match
                exact_text = normalized_text[start_char:end_char].strip()
                
                if not exact_text or len(exact_text) < 5:
                    continue
                
                processed_clauses.append({
                    "id": clause.get("id", ""),
                    "category": clause.get("category", "Uncategorized"),
                    "start_char": start_char,
                    "end_char": end_char,
                    "text": exact_text,
                })
            
            logger.info(f"Total clauses extracted: {len(processed_clauses)}")
            return processed_clauses
            
        except Exception as e:
            logger.error(f"Python-based clause extraction failed: {e}", exc_info=True)
            return []

    async def identify_conflicts(self, clauses: List[dict]) -> List[dict]:
        """
        Step 2: Identify conflicts between extracted clauses.
        """
        if not clauses:
            return []

        logger.info(f"Identifying conflicts among {len(clauses)} clauses")
        # Ensure we can see this in container logs even if logger is configured differently
        try:
            print(f"IDENTIFY_CONFLICTS_CALLED: {len(clauses)} clauses")
        except Exception:
            pass
        
        # TODO: If clauses list is too huge, we might need to chunk this too.
        # For now, assuming metadata fits in context.
        
        prompt = self._build_conflict_detection_prompt(clauses)
        response = await self._call_llm(prompt)
        # Debug: log raw response text to help diagnose parsing/format issues
        try:
            logger.info("LLM raw identify_conflicts response (trunc): %s", (response or '')[:1000])
        except Exception:
            logger.exception("Failed to log raw LLM response for identify_conflicts")
        # Also print to stdout to ensure visibility in container logs
        try:
            print('RAW_LLM_IDENTIFY_RESPONSE:', repr(response)[:2000])
        except Exception:
            pass

        result = self._parse_llm_response(response)
        conflicts = result.get("conflicts", [])
        logger.info(f"Found {len(conflicts)} potential conflicts")
        return conflicts

    async def generate_explanations(self, conflicts: List[dict], clauses: List[dict]) -> List[dict]:
        """
        Step 3: Generate detailed explanations for identified conflicts.
        """
        if not conflicts:
            return []

        logger.info(f"Generating explanations for {len(conflicts)} conflicts")
        
        # Enrich conflicts with explanations
        # We can do this in one go or per conflict. 
        # Doing it in one go is faster but might lose detail.
        # Let's try one go first.
        
        prompt = self._build_explanation_prompt(conflicts, clauses)
        response = await self._call_llm(prompt)
        
        result = self._parse_llm_response(response)
        explanations = result.get("explanations", [])
        
        # Merge explanations back into conflicts
        # Assuming the LLM returns a list of objects with conflict_id or similar reference
        # Or we just trust the order? 
        # Better to ask LLM to return the full conflict object with explanation added.
        
        return explanations

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _call_llm(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                logger.info(f"Calling LLM: {self.model} at {self.base_url}")
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        # Removed "format": "json" to give LLM more freedom in response structure
                    }
                )
                response.raise_for_status()
                result = response.json()
                # Debug: log the raw JSON returned by the LLM endpoint (truncated)
                try:
                    logger.info("LLM endpoint returned keys: %s", list(result.keys()))
                    # If the endpoint wraps the actual response as a string, log its length
                    if isinstance(result.get("response"), str):
                        logger.info("LLM 'response' field length: %s", len(result.get("response") or ""))
                except Exception:
                    logger.exception("Failed to log raw LLM JSON result")
                return result.get("response", "")
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                raise

    async def _run_clause_extraction(self, text: str, start_index: int) -> List[dict]:
        """
        Extract clauses from contract text using Python-based extraction.
        This method is kept for backward compatibility but now uses Python extractor.
        """
        # Use Python-based extractor instead of LLM
        clauses = python_extract_clauses(text, start_index=start_index)
        
        # Post-process to ensure exact text extraction
        normalized_text = text.replace("\r\n", "\n").strip()
        processed_clauses = []
        
        for clause in clauses:
            start_char = clause.get("start_char", 0)
            end_char = clause.get("end_char", 0)
            
            # Validate indices
            if start_char < 0 or end_char > len(normalized_text) or start_char >= end_char:
                logger.warning(f"Skipping clause {clause.get('id')}: invalid range [{start_char}, {end_char})")
                continue
            
            # Re-extract text to ensure exact match
            exact_text = normalized_text[start_char:end_char].strip()
            
            if not exact_text:
                continue
            
            processed_clauses.append({
                "id": clause.get("id", ""),
                "category": clause.get("category", "Uncategorized"),
                "start_char": start_char,
                "end_char": end_char,
                "text": exact_text,
            })
        
        return processed_clauses

    def _build_conflict_detection_prompt(self, clauses: List[dict]) -> str:
        # We send a simplified version of clauses to save tokens
        simplified_clauses: List[dict[str, Any]] = []
        for clause in clauses:
            payload: dict[str, Any] = {
                "id": clause.get("id"),
                "text": clause.get("text", ""),
            }
            if clause.get("category"):
                payload["category"] = clause["category"]
            if clause.get("clause_number"):
                payload["clause_number"] = clause["clause_number"]
            simplified_clauses.append(payload)

        clauses_text = json.dumps(simplified_clauses, indent=2, ensure_ascii=False)
        
        # Build example with actual IDs from the input if we have at least 2 clauses
        example_id_1 = simplified_clauses[0]["id"] if len(simplified_clauses) > 0 else "example-uuid-1"
        example_id_2 = simplified_clauses[1]["id"] if len(simplified_clauses) > 1 else "example-uuid-2"
        
        return f"""Identify pairs of conflicting clauses from the contract clause list below.

IMPORTANT: Two clauses conflict when they:
1. Contain contradictory terms (one says X, another says NOT X)
2. Have incompatible obligations (cannot both be fulfilled simultaneously)
3. Create logically inconsistent provisions (violate basic logic or legal principles)
4. Have mutually exclusive conditions or requirements

ANALYZE ALL {len(simplified_clauses)} CLAUSES for conflicts with each other.

INPUT CLAUSES:
{clauses_text}

REQUIRED OUTPUT FORMAT - You must return a JSON object with exactly this structure:
{{
  "conflicts": [
    {{
      "clause_id_1": "{example_id_1}",
      "clause_id_2": "{example_id_2}",
      "type": "LOGICAL"
    }}
  ]
}}

RULES:
- clause_id_1 and clause_id_2 must be the exact "id" values from the input clauses (UUID strings)
- type must be either "LOGICAL" or "LEGAL"
- Check EVERY clause against EVERY other clause
- If no conflicts exist, return {{"conflicts": []}}
- Do NOT return the input clauses
- Do NOT add extra fields

Your JSON response:"""

    def _build_explanation_prompt(self, conflicts: List[dict], clauses: List[dict]) -> str:
        # Map IDs to text/metadata for context
        clause_map = {
            c["id"]: {
                "text": c.get("text", ""),
                "clause_number": c.get("clause_number"),
                "heading": c.get("heading"),
            }
            for c in clauses
            if c.get("id")
        }
        
        conflicts_context = []
        for c in conflicts:
            c1_ctx = clause_map.get(c["clause_id_1"], {})
            c2_ctx = clause_map.get(c["clause_id_2"], {})
            conflicts_context.append({
                "clause_id_1": c["clause_id_1"],
                "clause_number_1": c1_ctx.get("clause_number"),
                "clause_id_2": c["clause_id_2"],
                "clause_number_2": c2_ctx.get("clause_number"),
                "text_1": c1_ctx.get("text", "Unknown"),
                "text_2": c2_ctx.get("text", "Unknown"),
            })
            
        return f"""
        Generate detailed explanations for the following conflicts.
        Return a JSON object with an "explanations" key.
        Use the provided clause numbers (if present) when referencing the clauses so the
        explanation text aligns with the contract numbering (e.g., "Clause 4" vs "Clause 6").
        Each item should have:
        - "clause_id_1": ID of the first clause.
        - "clause_id_2": ID of the second clause.
        - "explanation": A clear, human-readable explanation of why these clauses conflict that
          explicitly references their clause numbers when available.
        - "severity": "HIGH", "MEDIUM", or "LOW".
        
        Conflicts:
        {json.dumps(conflicts_context, indent=2)}
        """

    def _chunk_text(self, text: str) -> List[str]:
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            return []

        paragraphs = [p.strip() for p in re.split(r"\n{2,}", normalized) if p.strip()]
        if not paragraphs:
            paragraphs = [normalized]

        chunks: List[str] = []
        buffer: List[str] = []
        buffer_len = 0

        def flush_buffer() -> None:
            nonlocal buffer, buffer_len
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer = []
                buffer_len = 0

        for para in paragraphs:
            segments = (
                self._split_large_segment(para, MAX_CHUNK_SIZE)
                if len(para) > MAX_CHUNK_SIZE
                else [para]
            )
            for segment in segments:
                segment = segment.strip()
                if not segment:
                    continue
                addition = len(segment) if buffer_len == 0 else len(segment) + 2
                if buffer_len and buffer_len + addition > MAX_CHUNK_SIZE:
                    flush_buffer()
                if len(segment) > MAX_CHUNK_SIZE:
                    flush_buffer()
                    chunks.append(segment)
                    continue
                buffer.append(segment)
                buffer_len = len(segment) if buffer_len == 0 else buffer_len + len(segment) + 2

        flush_buffer()
        return chunks

    def _split_large_segment(self, segment: str, max_size: int) -> List[str]:
        pieces: List[str] = []
        remaining = segment
        while len(remaining) > max_size:
            split_at = self._find_split_index(remaining, max_size)
            pieces.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].lstrip()
        if remaining.strip():
            pieces.append(remaining.strip())
        return pieces

    def _find_split_index(self, text: str, max_size: int) -> int:
        window = text[:max_size]
        preferred_boundaries = ["\n\n", "\n", ". ", "; "]
        for boundary in preferred_boundaries:
            idx = window.rfind(boundary)
            if idx != -1 and idx > max_size * 0.3:
                return idx + len(boundary)
        return max_size

    def _parse_llm_response(self, response_text: str) -> dict[str, Any]:
        try:
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            parsed = json.loads(cleaned_text)
            # Some LLM endpoints return a JSON wrapper where the useful payload is under
            # a "content" field (or the whole payload is a JSON string). Attempt to
            # extract and parse that if present.
            if isinstance(parsed, dict) and "content" in parsed and isinstance(parsed["content"], str):
                inner = parsed["content"].strip()
                if inner.startswith("{") or inner.startswith("["):
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        # If inner isn't valid JSON, fall back to the outer parsed dict
                        return parsed
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return {}



