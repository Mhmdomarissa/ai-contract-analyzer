import json
import logging
import os
import re
from typing import Any, List

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
        Advanced clause extraction supporting:
        - Multiple numbering schemes (1., I., Article, etc.)
        - Hierarchical structures (Article > Section > Subsection)
        - Tables, schedules, and exhibits
        - Cross-references and nested lists
        - Multi-level indexing
        
        Args:
            text: The full contract text
            
        Returns:
            List of clause dicts with clause_number, category, start_char, end_char, text
        """
        clauses = []
        
        # Detect schedules/exhibits first (they're typically at the end)
        schedule_match = re.search(
            r'\n\s*(SCHEDULE[S]?|EXHIBIT[S]?|APPENDIX|ANNEX|ATTACHMENT)[:\s]',
            text,
            re.IGNORECASE | re.MULTILINE
        )
        
        main_text = text
        schedule_text = None
        schedule_start = None
        
        if schedule_match:
            schedule_start = schedule_match.start()
            main_text = text[:schedule_start]
            schedule_text = text[schedule_start:]
        
        # Pattern definitions for different contract structures
        patterns = {
            'article_section': re.compile(
                r'\b(Article|ARTICLE)\s+([IVX\d]+(?:\.\d+)?)[:\.\s]+([A-Z][^\n]{0,100}?)(?=\n|$)',
                re.MULTILINE
            ),
            'section_subsection': re.compile(
                r'\b(Section|SECTION)\s+(\d+(?:\.\d+)?)[:\.\s]+([A-Z][^\n]{0,100}?)(?=\n|$)',
                re.MULTILINE
            ),
            'numbered': re.compile(
                r'(?:^|\n|[\."\s])\s*(\d{1,2})\.\s+([A-Z][A-Za-z\s&,\-\']{2,50}?)(?:\s+(?:[A-Z][a-z]+|The |This |Either |Any ))',
                re.MULTILINE
            ),
            'roman': re.compile(
                r'(?:^|\n)\s*([IVX]{1,6})\.\s+([A-Z][A-Za-z\s&\-]{2,50}?)(?=\s)',
                re.MULTILINE
            ),
            'heading': re.compile(
                r'^([A-Z][A-Z\s&\-]{4,50}?)$',
                re.MULTILINE
            ),
            'lettered': re.compile(
                r'(?:^|\n)\s*\(([a-z])\)\s+([A-Z][^\n]{0,100}?)(?=\n|$)',
                re.MULTILINE
            ),
        }
        
        # Try patterns in priority order
        best_matches = []
        best_pattern = None
        
        for pattern_name in ['article_section', 'section_subsection', 'numbered', 'roman', 'heading']:
            matches = list(patterns[pattern_name].finditer(main_text))
            if len(matches) >= 3:  # Need at least 3 matches to consider valid structure
                best_matches = matches
                best_pattern = pattern_name
                break
        
        if not best_matches:
            # Fallback: return entire document
            return [{
                'clause_number': '0',
                'category': 'Full Document',
                'start_char': 0,
                'end_char': len(text),
                'text': text.strip(),
                'metadata': {'type': 'unstructured'}
            }]
        
        # Deduplicate and filter matches
        filtered_matches = []
        seen_identifiers = set()
        
        for match in best_matches:
            if best_pattern == 'heading':
                identifier = match.group(1).strip()
                title = identifier
                # Skip common non-clause headings
                skip_words = {'WITNESSETH', 'RECITALS', 'WHEREAS', 'NOW THEREFORE', 'BACKGROUND'}
                if identifier in skip_words or len(identifier.split()) > 6:
                    continue
            else:
                identifier = match.group(1) + (match.group(2) if len(match.groups()) > 2 else '')
                title = match.group(3).strip() if len(match.groups()) > 2 else match.group(2).strip()
            
            if identifier not in seen_identifiers:
                filtered_matches.append((match, identifier, title))
                seen_identifiers.add(identifier)
        
        # Sort by position
        filtered_matches.sort(key=lambda x: x[0].start())
        
        # Handle preamble
        if filtered_matches and filtered_matches[0][0].start() > 50:
            preamble_text = main_text[:filtered_matches[0][0].start()].strip()
            if preamble_text:
                clauses.append({
                    'clause_number': 'Preamble',
                    'category': 'Preamble and Parties',
                    'start_char': 0,
                    'end_char': filtered_matches[0][0].start(),
                    'text': preamble_text,
                    'metadata': {'type': 'preamble'}
                })
        
        # Extract main clauses with hierarchical sub-clauses
        for i, (match, identifier, title) in enumerate(filtered_matches):
            start_pos = match.start()
            
            # Determine end position
            if i < len(filtered_matches) - 1:
                end_pos = filtered_matches[i + 1][0].start()
            else:
                end_pos = len(main_text)
            
            clause_text = main_text[start_pos:end_pos].strip()
            
            # Detect if clause contains tables
            has_table = LLMService._detect_table_in_text(clause_text)
            
            # Extract hierarchical sub-clauses (e.g., 4.1, 4.2, 5.1, etc.)
            # First try pattern-based extraction for explicitly numbered subsections
            hierarchical_subclauses = LLMService._extract_hierarchical_subclauses(
                clause_text, identifier, start_pos
            )
            
            # Debug logging
            if hierarchical_subclauses:
                logger.info(f"Found {len(hierarchical_subclauses)} hierarchical subclauses for clause '{identifier}'")
            
            # If hierarchical sub-clauses found (minimum 2), add them instead of the parent
            if len(hierarchical_subclauses) >= 2:
                clauses.extend(hierarchical_subclauses)
            else:
                # No explicit sub-clauses, add the main clause
                # Note: In future, we could use LLM to intelligently split long clauses
                # into semantic sub-clauses with descriptive titles
                subsections = LLMService._extract_subsections(clause_text, best_pattern)
                cross_refs = LLMService._extract_cross_references(clause_text)
                
                clauses.append({
                    'clause_number': identifier,
                    'category': title,
                    'start_char': start_pos,
                    'end_char': end_pos,
                    'text': clause_text,
                    'metadata': {
                        'type': best_pattern,
                        'has_table': has_table,
                        'subsection_count': len(subsections),
                        'cross_references': cross_refs,
                        'parent_clause': None
                    }
                })
        
        # Process schedules/exhibits if found
        if schedule_text:
            schedule_clauses = LLMService._extract_schedules_and_exhibits(
                schedule_text, 
                schedule_start
            )
            clauses.extend(schedule_clauses)
        
        return clauses
    
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

    async def extract_clauses(self, text: str) -> List[dict]:
        """
        Step 1: Extract clauses from the text using structure-based parsing.
        
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
            clauses = await self._run_clause_extraction(text, start_index=1)
            logger.info(f"Total clauses extracted: {len(clauses)}")
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
            for conflict in conflicts:
                id1 = conflict.get("clause_id_1")
                id2 = conflict.get("clause_id_2")
                
                # Map back to UUIDs
                if id1 in self._clause_id_mapping:
                    conflict["clause_id_1"] = self._clause_id_mapping[id1]
                if id2 in self._clause_id_mapping:
                    conflict["clause_id_2"] = self._clause_id_mapping[id2]
        
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
        """
        # Use structure-based extraction (regex parsing of numbered sections)
        clauses = self.extract_clauses_by_structure(text)
        
        logger.info(f"Extracted {len(clauses)} clauses using structure-based parsing")
        return clauses

    def _build_conflict_detection_prompt(self, clauses: List[dict]) -> str:
        # We send a simplified version of clauses to save tokens
        # Include clause_number as "id" for easier LLM reference (instead of UUID)
        simplified_clauses: List[dict[str, Any]] = []
        id_mapping = {}  # Map clause_number to UUID for later lookup
        
        for clause in clauses:
            # Use clause_number as the ID (simpler for LLM to reference)
            clause_ref = clause.get("clause_number") or clause.get("id")
            id_mapping[clause_ref] = clause.get("id")
            
            payload: dict[str, Any] = {
                "id": clause_ref,
                "text": clause.get("text", ""),
            }
            if clause.get("clause_number"):
                payload["clause_number"] = clause["clause_number"]
            simplified_clauses.append(payload)

        # Store mapping for later use
        self._clause_id_mapping = id_mapping
        
        clauses_text = json.dumps(simplified_clauses, indent=2, ensure_ascii=False)
        
        # Build example with actual IDs from the input
        example_id_1 = simplified_clauses[0]["id"] if len(simplified_clauses) > 0 else "Preamble"
        example_id_2 = simplified_clauses[1]["id"] if len(simplified_clauses) > 1 else "AGREEMENT"
        
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
- clause_id_1 and clause_id_2 must be the EXACT "id" values from the INPUT CLAUSES above
- You MUST copy the id values EXACTLY as they appear - do NOT make up or modify them
- type must be either "LOGICAL" or "LEGAL"
- Check EVERY clause against EVERY other clause
- If no conflicts exist, return {{"conflicts": []}}
- Do NOT return the input clauses
- Do NOT add extra fields
- CRITICAL: Use only the id values that appear in the INPUT CLAUSES list above

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



