import json
import logging
import os
import re
from typing import Any, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

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
    def extract_clauses_by_structure(text: str) -> List[dict]:
        """
        Production-ready clause extraction with state-aware parsing.
        
        Features:
        - State tracking (PREAMBLE → MAIN → APPENDIX modes)
        - Hierarchical structures (1., 1.1, 1.1.1)
        - Appendix namespacing (prevents numbering collisions)
        - Complete boundary detection (no missing clauses)
        - All-caps headings (DEFINITIONS, PAYMENT TERMS, etc.)
        - Hierarchical parent-child relationships
        - Override clause detection
        
        Args:
            text: The full contract text
            
        Returns:
            List of clause dicts with clause_number, category, parent_clause_id, depth_level,
            is_override_clause, start_char, end_char, text
        """
        # Use hierarchical extractor with parent-child relationships and override detection
        from app.services.hierarchical_clause_extractor import HierarchicalClauseExtractor
        extractor = HierarchicalClauseExtractor()
        return extractor.extract_clauses(text)
    
    @staticmethod
    def _is_all_caps(text: str) -> bool:
        """Check if text is all uppercase (ignoring spaces and punctuation)."""
        if not text:
            return False
        # Remove spaces and common punctuation
        cleaned = re.sub(r'[\s\-\.,;:!?()&]', '', text)
        if not cleaned:
            return False
        # Count uppercase vs total letters
        letters = [c for c in cleaned if c.isalpha()]
        if not letters:
            return False
        uppercase = sum(1 for c in letters if c.isupper())
        return uppercase / len(letters) > 0.8  # At least 80% uppercase
    
    
    @staticmethod
    def _categorize_clause(text: str, clause_number: str) -> str:
        """
        Categorize clause based on content keywords.
        
        Priority order: Check specific keywords first, generic keywords last.
        This prevents over-categorization (e.g., payment clauses mentioning "client" 
        being wrongly categorized as PARTIES instead of PAYMENT).
        """
        text_upper = text.upper()
        
        # HIGH PRIORITY: Very specific categories (check first)
        specific_categories = {
            'APPENDIX': ['APPENDIX', 'ANNEX', 'SCHEDULE', 'EXHIBIT'],
            'DEFINITIONS': ['DEFINITION', 'DEFINITIONS', 'INTERPRETATION', 'MEANING'],
            'PAYMENT': ['PAYMENT', 'FEE', 'PRICE', 'COMPENSATION', 'INVOICE', 'RATE', 'CHARGEABLE', 'COST', 'TAX', 'VAT', 'DEDUCTION'],
            'CONFIDENTIALITY': ['CONFIDENTIAL', 'NON-DISCLOSURE', 'PRIVACY', 'PROPRIETARY', 'SECRET'],
            'TERMINATION': ['TERMINATION', 'EXPIRATION', 'CANCELLATION', 'END OF AGREEMENT', 'TERMINATE'],
            'LIABILITY': ['LIABILITY', 'INDEMNIFICATION', 'DAMAGES', 'WARRANTY', 'WARRANTIES', 'LIABLE', 'INDEMNIFY'],
            'DISPUTE': ['DISPUTE', 'ARBITRATION', 'GOVERNING LAW', 'JURISDICTION', 'LITIGATION', 'COURT'],
        }
        
        # MEDIUM PRIORITY: Moderately specific categories
        moderate_categories = {
            'TERM': ['TERM', 'DURATION', 'EFFECTIVE DATE', 'COMMENCEMENT', 'SOLE AGREEMENT', 'PERIOD'],
            'SCOPE': ['SCOPE', 'SERVICES', 'WORK', 'DELIVERABLES', 'PROVISION', 'OBLIGATIONS'],
        }
        
        # LOW PRIORITY: Generic categories (check last to avoid false positives)
        generic_categories = {
            'PARTIES': ['PARTIES', 'PARTY', 'CLIENT', 'AGENCY', 'CONTRACTOR', 'VENDOR', 'SUPPLIER'],
            'GENERAL': ['ENTIRE AGREEMENT', 'AMENDMENT', 'NOTICES', 'ASSIGNMENT', 'FORCE MAJEURE', 'SEVERABILITY'],
        }
        
        # Check in priority order: specific → moderate → generic
        for categories in [specific_categories, moderate_categories, generic_categories]:
            for category, keywords in categories.items():
                if any(keyword in text_upper[:200] for keyword in keywords):  # Check first 200 chars
                    return category
        
        return 'Uncategorized'
    
    @staticmethod
    def _detect_table_in_text(text: str) -> bool:
        """Detect if text contains table-like structures."""
        # Look for common table indicators
        table_indicators = [
            r'[│┤├┼┴┬┌┐└┘─]',  # Box drawing characters
            r'\|\s+\w+\s+\|',  # Pipe-separated columns
            r'[-─]{3,}',  # Horizontal lines
            r'(?:\t|  {2,})\w+(?:\t|  {2,})\w+',  # Tab or multi-space separated columns
        ]
        
        for pattern in table_indicators:
            if re.search(pattern, text):
                return True
        return False
    
    @staticmethod
    def _extract_hierarchical_subclauses(clause_text: str, parent_number: str, parent_start_pos: int) -> List[dict]:
        """
        Extract hierarchical sub-clauses (e.g., 4.1, 4.2, 5.1, 5.2) with descriptive titles.
        
        This creates separate clauses for each numbered subsection like:
        - 4.1 Payment Terms - The agency shall...
        - 4.2 Fee Structure - Fees are calculated...
        - 5.1 Equipment - The client provides...
        
        Args:
            clause_text: Text of the parent clause
            parent_number: Number of parent clause (e.g., "4", "5", "AGREEMENT")
            parent_start_pos: Starting position of parent clause in document
            
        Returns:
            List of sub-clause dicts, or empty list if no hierarchical structure found
        """
        subclauses = []
        
        # Try to extract the numeric part of parent_number for matching
        # e.g., "4" stays "4", "TERM" doesn't have a number, "FEE AND PAYMENT" doesn't have a number
        parent_num_match = re.match(r'^(\d+)', str(parent_number))
        
        if not parent_num_match:
            # Parent is not numbered (e.g., "AGREEMENT", "FEE AND PAYMENT"),
            # Look for ANY numbered subsections (X.Y pattern) within this clause
            subclause_pattern = re.compile(
                r'(?:^|\n)\s*(\d+\.\d+)\s+([A-Z][^\n]{0,100})',
                re.MULTILINE
            )
            matches = list(subclause_pattern.finditer(clause_text))
            
            # If we found subsections, they all share the same parent number
            # Extract it from the first match
            if matches and len(matches) >= 2:
                first_num = matches[0].group(1)  # e.g., "4.1"
                detected_parent = first_num.split('.')[0]  # e.g., "4"
                # Re-run with the detected parent number
                return LLMService._extract_hierarchical_subclauses(
                    clause_text, detected_parent, parent_start_pos
                )
            else:
                return []
        
        parent_num = parent_num_match.group(1)
        # Pattern to match numbered subsections with optional descriptive titles
        # Matches: "4.1 Title" or "4.1\tTitle" or "4.1 Title text..." 
        # More flexible - doesn't require immediate newline after title
        subclause_pattern = re.compile(
            r'(?:^|\n)\s*(' + re.escape(parent_num) + r'\.\d+)\s+([A-Z][^\n]{0,100})',
            re.MULTILINE
        )
        logger.info(f"Searching for subclauses with parent number '{parent_num}' in clause '{parent_number}'")
        
        matches = list(subclause_pattern.finditer(clause_text))
        logger.info(f"Found {len(matches)} potential subclauses: {[m.group(1) for m in matches]}")
        
        # Need at least 2 sub-clauses to consider it hierarchical
        if len(matches) < 2:
            return []
        
        # Extract each sub-clause
        for i, match in enumerate(matches):
            subclause_number = match.group(1)  # e.g., "4.1", "5.2"
            raw_title = match.group(2).strip()
            
            # Clean up the title - extract meaningful part
            # If title ends with a sentence, extract just the heading
            title_parts = raw_title.split('.')
            if len(title_parts) > 1 and len(title_parts[0]) < 80:
                # First sentence is likely the title
                title = title_parts[0].strip()
            else:
                title = raw_title[:100].strip()
            
            # Remove trailing punctuation from title
            title = re.sub(r'[:\-\.]+$', '', title).strip()
            
            # If title is too long or looks like body text, try to extract key phrase
            if len(title) > 70 or ' shall ' in title.lower() or ' will ' in title.lower():
                # Extract first few meaningful words as title
                words = title.split()[:7]
                title = ' '.join(words)
                # Clean up trailing common words
                title = re.sub(r'\s+(and|or|the|a|an|to|of|for|in|on|at|by|with)$', '', title, flags=re.IGNORECASE)
            
            # Determine boundaries
            start_pos = match.start()
            
            if i < len(matches) - 1:
                # End at the start of next sub-clause
                end_pos = matches[i + 1].start()
            else:
                # Last sub-clause extends to end of parent clause
                end_pos = len(clause_text)
            
            subclause_text = clause_text[start_pos:end_pos].strip()
            
            # Detect features
            has_table = LLMService._detect_table_in_text(subclause_text)
            cross_refs = LLMService._extract_cross_references(subclause_text)
            
            subclauses.append({
                'clause_number': subclause_number,
                'category': title if title else f"Subsection {subclause_number}",
                'start_char': parent_start_pos + start_pos,
                'end_char': parent_start_pos + end_pos,
                'text': subclause_text,
                'metadata': {
                    'type': 'hierarchical_subsection',
                    'parent_clause': str(parent_number),
                    'has_table': has_table,
                    'cross_references': cross_refs
                }
            })
        
        return subclauses
    
    @staticmethod
    def _extract_subsections(text: str, parent_pattern: str) -> List[dict]:
        """Extract hierarchical subsections from clause text."""
        subsections = []
        
        # Patterns for different subsection levels
        subsection_patterns = [
            (r'\n\s*(\d+\.\d+)\s+([A-Z][^\n]{0,80})', 'numbered_sub'),  # 1.1, 1.2
            (r'\n\s*\(([a-z])\)\s+([^\n]{0,100})', 'lettered'),  # (a), (b)
            (r'\n\s*\(([ivx]+)\)\s+([^\n]{0,100})', 'roman_sub'),  # (i), (ii)
            (r'\n\s*[•●○◦]\s+([^\n]{0,100})', 'bullet'),  # Bullet points
            (r'\n\s*[-–—]\s+([^\n]{0,100})', 'dash'),  # Dash items
        ]
        
        for pattern, subsec_type in subsection_patterns:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                subsections.append({
                    'type': subsec_type,
                    'identifier': match.group(1) if match.lastindex > 1 else None,
                    'text': match.group(2) if match.lastindex > 1 else match.group(1),
                    'position': match.start()
                })
        
        return subsections
    
    @staticmethod
    def _extract_cross_references(text: str) -> List[str]:
        """Extract cross-references to other clauses/sections."""
        cross_refs = []
        
        # Common cross-reference patterns
        ref_patterns = [
            r'(?:Section|Article|Clause|Schedule|Exhibit|Appendix)\s+(\d+(?:\.\d+)?)',
            r'See\s+(?:also\s+)?(?:Section|Article|Clause)\s+(\d+(?:\.\d+)?)',
            r'pursuant to\s+(?:Section|Article|Clause)\s+(\d+(?:\.\d+)?)',
            r'as defined in\s+(?:Section|Article|Clause)\s+(\d+(?:\.\d+)?)',
        ]
        
        for pattern in ref_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                ref = match.group(1) if match.lastindex > 0 else match.group(0)
                if ref not in cross_refs:
                    cross_refs.append(ref)
        
        return cross_refs
    
    @staticmethod
    def _extract_schedules_and_exhibits(text: str, offset: int) -> List[dict]:
        """Extract schedules, exhibits, and appendices as separate clauses."""
        items = []
        
        # Pattern to match schedule/exhibit headers
        schedule_pattern = re.compile(
            r'\n\s*(SCHEDULE|EXHIBIT|APPENDIX|ANNEX|ATTACHMENT)\s+([A-Z\d]+)[:\s\-]+([^\n]{0,100})?',
            re.IGNORECASE | re.MULTILINE
        )
        
        matches = list(schedule_pattern.finditer(text))
        
        for i, match in enumerate(matches):
            sched_type = match.group(1).upper()
            sched_id = match.group(2)
            sched_title = (match.group(3) or '').strip()
            
            start_pos = match.start() + offset
            
            # End is either next schedule or end of text
            if i < len(matches) - 1:
                end_pos = matches[i + 1].start() + offset
            else:
                end_pos = offset + len(text)
            
            full_text = text[match.start():end_pos - offset].strip()
            
            # Detect if schedule contains table
            has_table = LLMService._detect_table_in_text(full_text)
            
            items.append({
                'clause_number': f'{sched_type}_{sched_id}',
                'category': f'{sched_type} {sched_id}: {sched_title}' if sched_title else f'{sched_type} {sched_id}',
                'start_char': start_pos,
                'end_char': end_pos,
                'text': full_text,
                'metadata': {
                    'type': 'schedule',
                    'schedule_type': sched_type,
                    'has_table': has_table
                }
            })
        
        return items

    async def extract_clauses(self, text: str, enable_validation: bool = True) -> List[dict]:
        """
        Step 1: Extract clauses from the text using structure-based parsing.
        
        Workflow:
        1. Extract clauses using regex patterns (fast, reliable)
        2. Apply post-processing filters (remove TOC, duplicates)
        3. Optionally validate with LLM (check boundaries, quality)
        
        Args:
            text: Full contract text
            enable_validation: If True, use LLM to validate extracted clauses
            
        Note: We do NOT chunk the text for structure-based extraction because
        the pattern detection needs to see the entire document to work correctly.
        Chunking would cause later chunks to fail pattern detection and fall back
        to "Full Document" mode.
        """
        if not text or not text.strip():
            logger.warning("No text provided for clause extraction.")
            return []

        logger.info(
            "Starting structure-based clause extraction. Total chars: %s",
            len(text),
        )
        
        try:
            # Step 1: Regex extraction
            clauses = await self._run_clause_extraction(text, start_index=1)
            logger.info(f"Regex extracted: {len(clauses)} clauses")
            
            # Step 2: LLM validation (optional)
            if enable_validation and clauses:
                try:
                    from app.services.clause_validator import ClauseValidator
                    validator = ClauseValidator(self)
                    result = await validator.validate_clauses(clauses, text)
                    
                    logger.info(
                        f"LLM validation: {len(result.validated_clauses)} valid, "
                        f"{len(result.removed_clauses)} removed, "
                        f"quality: {result.overall_quality:.2f}"
                    )
                    
                    # Return validated clauses
                    clauses = result.validated_clauses
                except Exception as e:
                    logger.warning(f"LLM validation failed, using unvalidated clauses: {e}")
                    pass
            
            logger.info(f"Final clause count: {len(clauses)}")
            return clauses
        except Exception as e:
            logger.error(f"Failed to extract clauses: {e}")
            # Return empty list instead of failing completely
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
        
        # Map clause_numbers back to UUIDs if we used simplified IDs
        if hasattr(self, '_clause_id_mapping') and self._clause_id_mapping:
            logger.info(f"Mapping clause IDs using mapping: {self._clause_id_mapping}")
            
            def find_clause_id(clause_ref: str) -> str | None:
                """Find clause UUID by exact match or parent clause for sub-clauses."""
                clause_ref_str = str(clause_ref).strip()
                
                # Try exact match first
                if clause_ref_str in self._clause_id_mapping:
                    return self._clause_id_mapping[clause_ref_str]
                
                # Handle "Clause" prefix (e.g., "Clause2" -> "2")
                if clause_ref_str.startswith("Clause") or clause_ref_str.startswith("clause"):
                    # Remove "Clause" prefix and try again
                    cleaned = clause_ref_str.replace("Clause", "").replace("clause", "").strip()
                    if cleaned in self._clause_id_mapping:
                        logger.info(f"Mapped '{clause_ref_str}' to '{cleaned}'")
                        return self._clause_id_mapping[cleaned]
                    # Also try with the cleaned version for sub-clauses
                    clause_ref_str = cleaned
                
                # If it's a sub-clause (e.g., "2.6", "4.1"), try to find parent clause
                if '.' in clause_ref_str:
                    # Extract parent number (e.g., "2.6" -> "2", "4.1.2" -> "4")
                    parent_parts = clause_ref_str.split('.')
                    if len(parent_parts) >= 2:
                        parent_number = parent_parts[0]
                        if parent_number in self._clause_id_mapping:
                            logger.info(f"Mapped sub-clause '{clause_ref}' to parent clause '{parent_number}'")
                            return self._clause_id_mapping[parent_number]
                
                # Try case-insensitive match
                for key, value in self._clause_id_mapping.items():
                    if key.lower() == clause_ref_str.lower():
                        logger.info(f"Mapped '{clause_ref}' to '{key}' (case-insensitive)")
                        return value
                
                return None
            
            for conflict in conflicts:
                id1 = conflict.get("clause_id_1")
                id2 = conflict.get("clause_id_2")
                
                logger.debug(f"Before mapping: clause_id_1={id1}, clause_id_2={id2}")
                
                # Map back to UUIDs
                mapped_id1 = find_clause_id(str(id1))
                if mapped_id1:
                    conflict["clause_id_1"] = mapped_id1
                    logger.debug(f"Mapped {id1} -> {mapped_id1}")
                else:
                    logger.warning(f"clause_id_1 '{id1}' not found in mapping")
                    
                mapped_id2 = find_clause_id(str(id2))
                if mapped_id2:
                    conflict["clause_id_2"] = mapped_id2
                    logger.debug(f"Mapped {id2} -> {mapped_id2}")
                else:
                    logger.warning(f"clause_id_2 '{id2}' not found in mapping")
        
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
        Extract clauses from contract text using structure-based parsing.
        
        This uses regex to directly detect numbered sections (1., 2., 3., etc.)
        which is more reliable than LLM-provided character indices.
        
        Note: Post-processing is handled in extract_clauses() method.
        """
        # Use structure-based extraction (regex parsing of numbered sections)
        clauses = self.extract_clauses_by_structure(text)
        
        logger.info(f"Extracted {len(clauses)} raw clauses using structure-based parsing")
        return clauses


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
        """
        Parse LLM response, handling various formats including extra text before/after JSON.
        """
        try:
            cleaned_text = response_text.strip()
            
            # Remove markdown code blocks
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            
            cleaned_text = cleaned_text.strip()
            
            # Try to find the first valid JSON object
            # Sometimes LLM adds extra text before or after JSON
            first_brace = cleaned_text.find('{')
            if first_brace != -1:
                # Try to find the matching closing brace
                brace_count = 0
                end_pos = first_brace
                for i, char in enumerate(cleaned_text[first_brace:], start=first_brace):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
                
                # Extract just the JSON part
                json_text = cleaned_text[first_brace:end_pos]
                try:
                    parsed = json.loads(json_text)
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
                except json.JSONDecodeError:
                    # If that fails, try parsing the whole thing
                    pass
            
            # Fallback: try parsing the whole cleaned text
            try:
                parsed = json.loads(cleaned_text)
                if isinstance(parsed, dict) and "content" in parsed and isinstance(parsed["content"], str):
                    inner = parsed["content"].strip()
                    if inner.startswith("{") or inner.startswith("["):
                        try:
                            return json.loads(inner)
                        except json.JSONDecodeError:
                            return parsed
                return parsed
            except json.JSONDecodeError:
                pass
                
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Response text (first 500 chars): {response_text[:500]}")
        
        # If all parsing attempts fail, return empty dict
        logger.warning("Could not parse LLM response as JSON, returning empty result")
        return {}


    def _build_conflict_detection_prompt(self, clauses: List[dict]) -> str:
        """
        Build comprehensive contextual conflict detection prompt.
        The LLM should understand the entire contract context (parties, contract type, jurisdiction, etc.)
        and then identify conflicts between clauses.
        """
        # We send full clause text for complete contextual understanding
        simplified_clauses: List[dict[str, Any]] = []
        id_mapping = {}
        
        for clause in clauses:
            clause_ref = clause.get("clause_number") or clause.get("id")
            id_mapping[clause_ref] = clause.get("id")
            
            payload: dict[str, Any] = {
                "id": clause_ref,
                "text": clause.get("text", ""),  # Full text - never truncated
            }
            if clause.get("clause_number"):
                payload["clause_number"] = clause["clause_number"]
            if clause.get("heading"):
                payload["heading"] = clause["heading"]
            simplified_clauses.append(payload)

        self._clause_id_mapping = id_mapping
        
        clauses_text = json.dumps(simplified_clauses, indent=2, ensure_ascii=False)
        
        example_id_1 = simplified_clauses[0]["id"] if len(simplified_clauses) > 0 else "1"
        example_id_2 = simplified_clauses[1]["id"] if len(simplified_clauses) > 1 else "2"
        
        return f"""You are an expert legal document analyst. Your task is to analyze the ENTIRE contract contextually and identify REAL conflicts between clauses.

STEP 1: UNDERSTAND THE CONTRACT CONTEXT
First, read through ALL {len(simplified_clauses)} clauses to understand:
- What type of contract this is (employment, service, sales, etc.)
- Who the parties are (names, roles, relationships)
- The jurisdiction and governing law
- Key terms, dates, locations, and financial arrangements
- The overall structure and purpose of the agreement

STEP 2: IDENTIFY CONFLICTS BETWEEN CLAUSES
After understanding the full context, identify conflicts where two clauses:
1. Contain contradictory terms (one says X, another says NOT X or contradicts X)
2. Have incompatible obligations (cannot both be fulfilled simultaneously)
3. Create logically inconsistent provisions (violate basic logic or legal principles)
4. Have mutually exclusive conditions or requirements
5. Specify different values for the same thing (dates, amounts, locations, jurisdictions, etc.)

TYPES OF CONFLICTS TO DETECT:
- Geographic/Jurisdictional: One clause says "UAE" and another says "UK" or "USA" for the same context
- Party identification: Inconsistent party names or roles that create confusion
- Date/Time: One clause says "30 days" and another says "60 days" for the same deadline
- Financial: One clause says "Payment due in 30 days" and another says "Payment due in 60 days" for the same payment
- Legal requirements: One clause requires X and another prohibits X
- Term definitions: One clause defines a term one way and another uses it differently
- Obligations: One clause requires Party A to do X, another requires Party B to do X (when they conflict)

WHAT IS NOT A CONFLICT:
- Document titles, headers, preambles, or structural elements
- Clauses with "Gap" as clause number (usually structural, not substantive)
- Complementary clauses or cross-references that clarify each other
- Different clauses covering different topics (not contradictions)
- Table/KPI content redundancies (often intentional)
- Stylistic variations in wording (unless they change meaning)
- Clauses that build upon each other or provide additional detail

INPUT CLAUSES (ALL {len(simplified_clauses)} clauses - read them all to understand the full context):
{clauses_text}

REQUIRED OUTPUT FORMAT - Return a JSON object with exactly this structure:
{{
  "conflicts": [
    {{
      "clause_id_1": "{example_id_1}",
      "clause_id_2": "{example_id_2}",
      "type": "LOGICAL" | "LEGAL" | "TERMINOLOGICAL" | "GEOGRAPHIC" | "TEMPORAL" | "FINANCIAL",
      "description": "Clear, detailed description of the conflict. Be specific: 'Clause X states [specific text/requirement] but Clause Y states [contradictory text/requirement]. This creates a conflict because [explanation].'",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "suggested_resolution": "Specific, actionable recommendation to resolve the conflict. Example: 'Standardize jurisdiction to UAE across all clauses' or 'Clarify that Clause X applies to [context A] and Clause Y applies to [context B]' or 'Remove the conflicting provision in Clause X and keep Clause Y'"
    }}
  ]
}}

RULES:
- clause_id_1 and clause_id_2 must be the EXACT "id" values from the INPUT CLAUSES above
- You MUST copy the id values EXACTLY as they appear - do NOT make up or modify them
- type must be one of: "LOGICAL", "LEGAL", "TERMINOLOGICAL", "GEOGRAPHIC", "TEMPORAL", "FINANCIAL"
- description must clearly explain WHAT the conflict is and WHY it's a conflict
- severity: "HIGH" (prevents contract execution), "MEDIUM" (creates legal risk), "LOW" (minor inconsistency)
- suggested_resolution must be specific and actionable
- Check EVERY clause against EVERY other clause systematically
- If no conflicts exist, return {{"conflicts": []}}
- Be EXTREMELY conservative - only flag conflicts you are 95%+ confident are real contradictions
- CRITICAL: Use only the id values that appear in the INPUT CLAUSES list above

Your JSON response:"""



