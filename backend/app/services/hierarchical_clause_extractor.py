"""
Hierarchical Clause Extractor - Builds parent-child relationships and heading inheritance

Key features:
1. Parent-child relationships (parent_clause_id)
2. Depth tracking (depth_level)
3. Heading inheritance from parent sections
4. Override clause detection
5. Proper appendix/schedule splitting (A, B, 1, 2)
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class HierarchicalClauseExtractor:
    """
    Advanced clause extractor that builds a hierarchy tree with proper parent-child relationships.
    """
    
    # Override keywords for special clause detection
    OVERRIDE_KEYWORDS = [
        'notwithstanding',
        'in the event of conflict',
        'shall prevail',
        'shall override',
        'takes precedence',
        'supersede',
        'overrides'
    ]
    
    def __init__(self):
        self.clauses = []
        self.clause_lookup = {}  # Maps clause_number -> clause dict for quick parent lookup
        self.appendix_boundaries = []
    
    def extract_clauses(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract clauses with full hierarchy and parent-child relationships.
        
        Returns list of clauses with:
        - clause_number: Display number (1, 1.1, A.1, etc.)
        - parent_clause_id: Reference to parent (None for top-level)
        - depth_level: 0=top-level, 1=first child, 2=second child, etc.
        - heading: Inherited or explicit heading
        - category: Semantic category
        - text: Clause text
        - is_override_clause: Boolean flag for override detection
        """
        if not text or not text.strip():
            return []
        
        # Reset state
        self.clauses = []
        self.clause_lookup = {}
        
        # Normalize text
        text = text.replace('\r\n', '\n')
        
        # === PHASE 1: Detect Appendices and Schedules ===
        self._detect_appendices_and_schedules(text)
        
        # === PHASE 2: Find All Clause Boundaries ===
        boundaries = self._find_all_boundaries(text)
        
        if not boundaries:
            return [self._create_unstructured_clause(text)]
        
        # === PHASE 3: Extract Preamble ===
        self._extract_preamble(text, boundaries)
        
        # === PHASE 4: Extract All Clauses ===
        self._extract_all_clauses(text, boundaries)
        
        # === PHASE 5: Build Hierarchy Tree ===
        self._build_hierarchy()
        
        # === PHASE 6: Inherit Headings from Parents ===
        self._inherit_headings()
        
        # === PHASE 7: Detect Override Clauses ===
        self._detect_override_clauses()
        
        logger.info(f"Extracted {len(self.clauses)} clauses with hierarchy")
        
        # === PHASE 8: Validate Extraction Quality ===
        self._validate_extraction(text)
        
        return self.clauses
    
    def _detect_appendices_and_schedules(self, text: str):
        """
        Detect APPENDIX A, APPENDIX B, SCHEDULE 1, SCHEDULE 2 as separate sections.
        Supports both letter-based (A, B, C) and number-based (1, 2, 3) identifiers.
        """
        # Pattern matches: "APPENDIX A –", "SCHEDULE 1:", "ANNEX B: Title", etc.
        # Using broader pattern to catch different separators (–, -, :)
        pattern = re.compile(
            r'^\s*((?:APPENDIX|ANNEX|SCHEDULE|EXHIBIT)\s+([A-Z0-9]+))(?:\s*[–\-:]\s*([A-Z][A-Z\s&,\-]*?))?$',
            re.MULTILINE | re.IGNORECASE
        )
        
        for match in pattern.finditer(text):
            full_label = match.group(1).strip().upper()  # "APPENDIX A"
            identifier = match.group(2).upper()  # "A" or "1"
            title = match.group(3).strip() if match.group(3) else None  # Optional title
            
            self.appendix_boundaries.append({
                'pos': match.start(),
                'end': None,  # Will be set later
                'full_label': full_label,  # "APPENDIX A"
                'identifier': identifier,  # "A"
                'title': title,  # "SERVICE LEVEL AGREEMENT"
                'type': full_label.split()[0]  # "APPENDIX", "SCHEDULE", etc.
            })
            logger.info(f"Found appendix/schedule: {full_label} (ID: {identifier}) at position {match.start()}")
        
        # Set end positions
        for i, app in enumerate(self.appendix_boundaries):
            if i < len(self.appendix_boundaries) - 1:
                app['end'] = self.appendix_boundaries[i + 1]['pos']
            else:
                app['end'] = len(text)
        
        logger.info(f"Found {len(self.appendix_boundaries)} appendices/schedules")
    
    def _get_appendix_context(self, pos: int) -> Optional[Dict[str, Any]]:
        """Get the appendix/schedule context for a given position."""
        for app in self.appendix_boundaries:
            if app['pos'] < pos < app['end']:
                return app
        return None
    
    def _find_all_boundaries(self, text: str) -> List[Dict[str, Any]]:
        """Find all clause boundaries including numbered, lettered, and headings."""
        boundaries = []
        
        # STEP 1: Detect ARTICLE headings (e.g., "1) DEFINITIONS", "6) FEES")
        # Pattern: number followed by ") " and then ALL CAPS heading
        article_pattern = re.compile(
            r'(?:^|\n)\s*(\d+)\)\s+([A-Z][A-Z\s,&\-]+?)(?:\n|$)',
            re.MULTILINE
        )
        
        articles = {}  # Maps position -> article info
        current_article_contexts = []  # List of (start_pos, end_pos, article_number, heading)
        
        for match in article_pattern.finditer(text):
            article_num = match.group(1)
            article_heading = match.group(2).strip()
            pos = match.start()
            
            articles[pos] = {
                'article_number': article_num,
                'heading': article_heading,
                'pos': pos
            }
            logger.info(f"Detected ARTICLE {article_num}: {article_heading} at position {pos}")
        
        # Build article context ranges (from article start to next article)
        article_positions = sorted(articles.keys())
        for i, pos in enumerate(article_positions):
            article = articles[pos]
            start_pos = pos
            end_pos = article_positions[i + 1] if i + 1 < len(article_positions) else len(text)
            current_article_contexts.append({
                'start': start_pos,
                'end': end_pos,
                'number': article['article_number'],
                'heading': article['heading'],
                'subclause_counter': 0  # Track sequential subclauses within this article
            })
        
        def _get_article_context(position: int) -> Optional[Dict]:
            """Get the current article context for a given position."""
            for ctx in current_article_contexts:
                if ctx['start'] < position < ctx['end']:
                    return ctx
            return None
        
        # STEP 2: Patterns for clause detection (most specific to least specific)
        patterns = {
            'sub_sub_sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+\.\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'sub_sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'main_with_dot': re.compile(r'(?:^|\n)\s*(\d+)\.\s+(?=\S)', re.MULTILINE),  # "1. text"
            'main_with_paren': re.compile(r'(?:^|\n)\s*(\d+)\)\s+(?=\S)', re.MULTILINE),  # "1) text"
            'appendix_clause': re.compile(r'(?:^|\n)\s*([A-Z])\.(\d+(?:\.\d+)*)\s+(?=\S)', re.MULTILINE),  # A.1, B.2.3
            'lettered': re.compile(r'(?:^|\n)\s*(\([a-z]\))\s+(?=\S)', re.MULTILINE | re.IGNORECASE),
        }
        
        # STEP 3: Add article boundaries first
        for pos in article_positions:
            article = articles[pos]
            boundaries.append({
                'pos': pos,
                'label': article['article_number'],
                'original': article['article_number'],
                'type': 'article',
                'is_article_heading': True,
                'heading': article['heading'],
                'appendix_context': None
            })
        
        # STEP 4: Find numbered clauses
        for pattern_type, pattern in patterns.items():
            for match in pattern.finditer(text):
                pos = match.start()
                
                # Skip if this position is an article heading
                if pos in articles:
                    continue
                
                # Check if in appendix
                appendix_ctx = self._get_appendix_context(pos)
                
                # Check if inside an article
                article_ctx = _get_article_context(pos)
                
                # Determine display label
                if pattern_type == 'appendix_clause':
                    # This is like "A.1" - combine both groups
                    letter = match.group(1)  # "A"
                    number = match.group(2)  # "1"
                    label = f"{letter}.{number}"
                    display_label = label
                elif pattern_type in ['main_with_paren', 'main_with_dot']:
                    # This is a number like "1)" or "1."
                    label = match.group(1)
                    
                    if article_ctx:
                        # FIXED: Preserve original numbering when inside articles
                        # Check if this looks like a numbered list within the article
                        # by looking for consecutive numbering starting from 1
                        article_ctx['subclause_counter'] += 1
                        
                        # Use original label with article prefix to preserve structure
                        # E.g., "1)" inside "4) FEE" becomes "4.1" not "4.7"
                        display_label = f"{article_ctx['number']}.{label}"
                        
                        # Track that we've seen this numbered item
                        logger.debug(f"Subclause {label} inside Article {article_ctx['number']} -> {display_label}")
                    elif appendix_ctx:
                        # Regular numbered clause inside appendix - namespace it
                        display_label = f"{appendix_ctx['identifier']}.{label}"
                    else:
                        # Top-level clause (shouldn't happen if articles detected, but fallback)
                        display_label = label
                else:
                    label = match.group(1)
                    if appendix_ctx:
                        # Regular numbered clause inside appendix - namespace it
                        display_label = f"{appendix_ctx['identifier']}.{label}"
                    else:
                        display_label = label
                
                boundaries.append({
                    'pos': pos,
                    'label': display_label,
                    'original': label,
                    'type': pattern_type,
                    'is_article_heading': False,
                    'appendix_context': appendix_ctx,
                    'article_context': article_ctx
                })
        
        # Add appendix/schedule headers as top-level clauses
        for app in self.appendix_boundaries:
            boundaries.append({
                'pos': app['pos'],
                'label': app['full_label'],
                'original': app['full_label'],
                'type': 'appendix_header',
                'is_article_heading': False,
                'appendix_context': app
            })
        
        # Sort by position
        boundaries.sort(key=lambda x: x['pos'])
        
        # Deduplicate boundaries at same position (keep highest priority)
        priority = ['article', 'appendix_header', 'sub_sub_sub', 'sub_sub', 'sub', 'main_with_dot', 'main_with_paren', 'appendix_clause', 'lettered']
        unique_boundaries = []
        i = 0
        while i < len(boundaries):
            current_pos = boundaries[i]['pos']
            group = [boundaries[i]]
            j = i + 1
            # Group boundaries within 5 chars
            while j < len(boundaries) and boundaries[j]['pos'] - current_pos < 5:
                group.append(boundaries[j])
                j += 1
            
            # Keep highest priority
            group.sort(key=lambda x: priority.index(x['type']) if x['type'] in priority else 999)
            unique_boundaries.append(group[0])
            i = j
        
        logger.info(f"Found {len(unique_boundaries)} clause boundaries")
        return unique_boundaries
    
    def _extract_preamble(self, text: str, boundaries: List[Dict[str, Any]]):
        """Extract preamble if exists."""
        first_boundary_pos = boundaries[0]['pos']
        if first_boundary_pos > 100:
            preamble_text = text[:first_boundary_pos].strip()
            if len(preamble_text) > 50:
                clause = {
                    'clause_number': 'PREAMBLE',
                    'parent_clause_id': None,
                    'depth_level': 0,
                    'heading': 'Preamble',
                    'category': 'PARTIES',
                    'start_char': 0,
                    'end_char': first_boundary_pos,
                    'text': preamble_text,
                    'is_override_clause': False,
                    'metadata': {'type': 'preamble', 'appendix': None}
                }
                self.clauses.append(clause)
                self.clause_lookup['PREAMBLE'] = clause
    
    def _extract_all_clauses(self, text: str, boundaries: List[Dict[str, Any]]):
        """Extract all clauses from boundaries."""
        skipped_short = 0
        skipped_signature = 0
        stored_count = 0
        
        for i, boundary in enumerate(boundaries):
            logger.debug(f"Processing boundary {i+1}/{len(boundaries)}: label={boundary['label']}, type={boundary['type']}, is_article={boundary.get('is_article_heading', False)}")
            
            # Find end position (before next clause)
            if i < len(boundaries) - 1:
                next_boundary_pos = boundaries[i + 1]['pos']
                # For most clauses, use the position just before the next boundary
                # Don't use rfind as it was cutting off too much text
                end_pos = next_boundary_pos
            else:
                end_pos = len(text)
            
            # Extract text
            clause_text = text[boundary['pos']:end_pos].strip()
            
            # Skip if too short (but articles can be short if they're just headings)
            if len(clause_text) < 15 and not boundary.get('is_article_heading'):
                logger.debug(f"  SKIP (too short): {boundary['label']} - only {len(clause_text)} chars")
                skipped_short += 1
                continue
            
            # Filter signature blocks and execution text (but not articles)
            if not boundary.get('is_article_heading'):
                text_upper = clause_text.upper()
                if any(marker in text_upper[:200] for marker in [
                    'IN WITNESS WHEREOF',
                    'SIGNATURE:',
                    'EXECUTED ON',
                    'SIGNED BY',
                    'DESIGNATION:',
                ]) and 'EXECUTION' not in boundary.get('heading', '').upper():
                    logger.debug(f"  SKIP (signature block): {boundary['label']}")
                    skipped_signature += 1
                    continue
            
            # Extract heading
            if boundary.get('is_article_heading'):
                # For articles, use the detected heading
                heading = boundary.get('heading', boundary['label'])
            else:
                # For subclauses, extract heading from first line
                first_line = re.match(r'^[^\n]{1,150}', clause_text)
                heading = first_line.group(0).strip() if first_line else boundary['label']
            
            # Initial categorization (will be refined by inheritance)
            category = self._categorize_clause(clause_text, boundary['label'])
            
            clause = {
                'clause_number': boundary['label'],
                'parent_clause_id': None,  # Will be set in build_hierarchy
                'depth_level': 0,  # Will be calculated
                'heading': heading,
                'category': category,
                'start_char': boundary['pos'],
                'end_char': end_pos,
                'text': clause_text,
                'is_override_clause': False,  # Will be set in detect_override_clauses
                'metadata': {
                    'type': boundary['type'],
                    'original_number': boundary.get('original'),
                    'is_article_heading': boundary.get('is_article_heading', False),
                    'appendix_context': boundary.get('appendix_context'),
                    'article_context': boundary.get('article_context')
                }
            }
            
            logger.debug(f"  ✅ STORED: {boundary['label']} ({heading[:50]}...)")
            stored_count += 1
            self.clauses.append(clause)
            self.clause_lookup[boundary['label']] = clause
        
        logger.info(f"Extraction summary: {stored_count} stored, {skipped_short} skipped (short), {skipped_signature} skipped (signature)")
    
    def _build_hierarchy(self):
        """
        Build parent-child relationships based on numbering patterns.
        
        Rules:
        - 6.1 is child of 6 (article)
        - 6.1.1 is child of 6.1
        - 1.1 is child of 1
        - 1.1.1 is child of 1.1
        - (a) is child of nearest preceding numeric clause
        - A.1 is child of APPENDIX A
        - A.1.1 is child of A.1
        """
        for clause in self.clauses:
            clause_num = clause['clause_number']
            
            # Skip preamble and appendix headers
            if clause_num in ['PREAMBLE'] or clause['metadata']['type'] == 'appendix_header':
                clause['depth_level'] = 0
                continue
            
            # Articles are top-level (depth 0)
            if clause['metadata'].get('is_article_heading'):
                clause['depth_level'] = 0
                clause['parent_clause_id'] = None
                continue
            
            # Find parent based on numbering
            parent_num = self._find_parent_number(clause_num)
            
            if parent_num and parent_num in self.clause_lookup:
                parent = self.clause_lookup[parent_num]
                clause['parent_clause_id'] = parent_num
                clause['depth_level'] = parent['depth_level'] + 1
            else:
                # Top-level clause
                clause['parent_clause_id'] = None
                clause['depth_level'] = 0
    
    def _find_parent_number(self, clause_num: str) -> Optional[str]:
        """
        Determine the parent clause number based on numbering pattern.
        
        Examples:
        - "1.1" -> "1"
        - "1.1.1" -> "1.1"
        - "(a)" -> find nearest preceding numeric clause
        - "A.1" -> "APPENDIX A"
        - "A.1.1" -> "A.1"
        """
        # Lettered clauses (a), (b), (c)
        if clause_num.startswith('(') and clause_num.endswith(')'):
            # Find nearest preceding numeric clause
            current_index = self.clauses.index(self.clause_lookup[clause_num])
            for i in range(current_index - 1, -1, -1):
                prev_num = self.clauses[i]['clause_number']
                # Match numeric clauses (not letters, not preamble)
                if prev_num[0].isdigit() or (len(prev_num) > 2 and prev_num[0].isalpha() and prev_num[1] == '.'):
                    return prev_num
            return None
        
        # Appendix clauses: A.1, B.2, A.1.1
        if len(clause_num) > 2 and clause_num[0].isalpha() and clause_num[1] == '.':
            letter = clause_num[0]
            rest = clause_num[2:]  # "1" or "1.1"
            
            if '.' in rest:
                # A.1.1 -> parent is A.1
                parts = rest.rsplit('.', 1)
                return f"{letter}.{parts[0]}"
            else:
                # A.1 -> parent is APPENDIX A
                # Find the appendix header
                for clause in self.clauses:
                    if clause['metadata']['type'] == 'appendix_header':
                        app_ctx = clause['metadata'].get('appendix_context')
                        if app_ctx and app_ctx['identifier'] == letter:
                            return clause['clause_number']
                return None
        
        # Regular numbered clauses: 1.1, 1.1.1, 1.1.1.1
        if '.' in clause_num:
            parts = clause_num.rsplit('.', 1)
            return parts[0]
        
        # Top-level clause (1, 2, 3, etc.)
        return None
    
    def _inherit_headings(self):
        """
        Inherit headings from parent sections.
        Only main sections (depth 0) get keyword-based categories.
        Children inherit parent's category and heading.
        """
        for clause in self.clauses:
            if clause['parent_clause_id'] and clause['parent_clause_id'] in self.clause_lookup:
                parent = self.clause_lookup[clause['parent_clause_id']]
                
                # Inherit category from parent
                clause['category'] = parent['category']
                
                # If parent has explicit heading, use it as context
                # The clause's own heading stays (it's the first line of text)
                # But we store parent heading in metadata for context
                clause['metadata']['parent_heading'] = parent['heading']
    
    def _detect_override_clauses(self):
        """
        Detect and tag override clauses.
        These contain keywords like "notwithstanding", "shall prevail", etc.
        """
        for clause in self.clauses:
            text_lower = clause['text'].lower()
            clause['is_override_clause'] = any(
                keyword in text_lower for keyword in self.OVERRIDE_KEYWORDS
            )
            
            if clause['is_override_clause']:
                logger.info(f"Override clause detected: {clause['clause_number']}")
    
    def _validate_extraction(self, text: str):
        """Run validation checks on extracted clauses."""
        from app.services.clause_validation import ClauseExtractionValidator
        ClauseExtractionValidator.validate_extraction(self.clauses, text)
    
    def _categorize_clause(self, text: str, clause_number: str) -> str:
        """Categorize clause by keywords with priority ordering."""
        text_upper = text.upper()
        
        # HIGH PRIORITY: Very specific categories
        specific = {
            'APPENDIX': ['APPENDIX', 'ANNEX', 'SCHEDULE', 'EXHIBIT'],
            'DEFINITIONS': ['DEFINITION', 'DEFINITIONS', 'INTERPRETATION', 'MEANING'],
            'PAYMENT': ['PAYMENT', 'FEE', 'PRICE', 'COMPENSATION', 'INVOICE', 'RATE', 'COST', 'TAX', 'VAT'],
            'CONFIDENTIALITY': ['CONFIDENTIAL', 'NON-DISCLOSURE', 'PRIVACY', 'PROPRIETARY'],
            'TERMINATION': ['TERMINATION', 'EXPIRATION', 'CANCELLATION', 'END OF AGREEMENT'],
            'LIABILITY': ['LIABILITY', 'INDEMNIFICATION', 'DAMAGES', 'WARRANTY', 'LIABLE'],
            'DISPUTE': ['DISPUTE', 'ARBITRATION', 'GOVERNING LAW', 'JURISDICTION', 'LITIGATION'],
        }
        
        # MEDIUM PRIORITY
        moderate = {
            'TERM': ['TERM', 'DURATION', 'EFFECTIVE DATE', 'COMMENCEMENT', 'PERIOD'],
            'SCOPE': ['SCOPE', 'SERVICES', 'WORK', 'DELIVERABLES', 'OBLIGATIONS'],
        }
        
        # LOW PRIORITY: Generic categories
        generic = {
            'PARTIES': ['PARTIES', 'PARTY', 'CLIENT', 'AGENCY', 'CONTRACTOR', 'VENDOR'],
            'GENERAL': ['ENTIRE AGREEMENT', 'AMENDMENT', 'NOTICES', 'ASSIGNMENT', 'FORCE MAJEURE'],
        }
        
        # Check in priority order
        for categories in [specific, moderate, generic]:
            for category, keywords in categories.items():
                if any(keyword in text_upper[:200] for keyword in keywords):
                    return category
        
        return 'Uncategorized'
    
    def _create_unstructured_clause(self, text: str) -> Dict[str, Any]:
        """Create a single unstructured clause for documents with no structure."""
        return {
            'clause_number': 'FULL_DOCUMENT',
            'parent_clause_id': None,
            'depth_level': 0,
            'heading': 'Full Document',
            'category': 'Uncategorized',
            'start_char': 0,
            'end_char': len(text),
            'text': text.strip(),
            'is_override_clause': False,
            'metadata': {'type': 'unstructured'}
        }
