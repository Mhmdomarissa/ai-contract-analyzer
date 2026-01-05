"""
Improved clause extraction with state-aware parsing.

Key improvements over previous version:
1. State tracking (PREAMBLE → MAIN → APPENDIX modes)
2. Appendix namespacing (prevents numbering collisions like "2.1" in main vs appendix)
3. Better boundary detection (no missing clauses)
4. Complete lettered item detection (a-z all captured)
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ImprovedClauseExtractor:
    """
    State-aware clause extractor that properly handles:
    - Preambles (WHEREAS, WITNESSETH, NOW THEREFORE)
    - Main numbered clauses (1., 1.1, 1.1.1, etc.)
    - Appendices with internal numbering (namespaced to avoid conflicts)
    - Lettered items ((a), (b), (c), etc.)
    - All-caps headings
    """
    
    @staticmethod
    def extract_clauses(text: str) -> List[Dict[str, Any]]:
        """
        Extract clauses with proper state tracking and namespacing.
        
        Args:
            text: Full contract text
            
        Returns:
            List of clause dicts with clause_number, category, text, etc.
        """
        if not text or not text.strip():
            return []
        
        # Normalize text
        text = text.replace('\r\n', '\n')
        
        clauses = []
        
        # PHASE 1: Detect appendix boundaries (these switch parsing mode)
        # STRICT: Match APPENDIX headers that start at beginning of line (with optional whitespace)
        # Pattern matches: "APPENDIX 1:" or "APPENDIX 1: RATE CARD" on its own line
        # Will NOT match: "...attached as Appendix 1 (Rate Card) of..." (has text before on same line)
        appendix_pattern = re.compile(
            r'^\s*((?:APPENDIX|ANNEX|SCHEDULE|EXHIBIT)\s+([A-Z0-9]+))(?:\s*:\s*[A-Z][A-Z\s&,\-]*)?$',
            re.MULTILINE | re.IGNORECASE
        )
        
        appendix_boundaries = []
        for match in appendix_pattern.finditer(text):
            appendix_boundaries.append({
                'pos': match.start(),
                'label': match.group(1).strip().upper(),
                'id': match.group(2),  # Just the number/letter
                'end': None  # Will be set to next appendix start or doc end
            })
            logger.info(f"Found appendix: {match.group(1)} at position {match.start()}")
        
        # Set end positions for each appendix
        for i, app in enumerate(appendix_boundaries):
            if i < len(appendix_boundaries) - 1:
                app['end'] = appendix_boundaries[i + 1]['pos']
            else:
                app['end'] = len(text)
        
        logger.info(f"Found {len(appendix_boundaries)} appendices")
        
        # PHASE 2: Define patterns for clause detection
        patterns = {
            # Most specific to least specific
            # Match: "1.2.3.4." or "1.2.3.4 " (with optional trailing dot)
            'sub_sub_sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+\.\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'sub_sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'sub': re.compile(r'(?:^|\n)\s*(\d+\.\d+)[\.\)]*\s+(?=\S)', re.MULTILINE),
            'main': re.compile(r'(?:^|\n)\s*(\d+)[\.\)]\s+(?=\S)', re.MULTILINE),
            'lettered': re.compile(r'(?:^|\n)\s*(\([a-z]\))\s+(?=\S)', re.MULTILINE | re.IGNORECASE),
            'heading': re.compile(r'(?:^|\n)([A-Z][A-Z\s&,\-]{10,100}?)(?=\n)', re.MULTILINE),
        }
        
        # PHASE 3: Find all clause boundaries
        boundaries = []
        
        # Helper function to determine which appendix (if any) a position belongs to
        def get_appendix_context(pos: int) -> Optional[str]:
            for app in appendix_boundaries:
                if app['pos'] < pos < app['end']:
                    return app['id']
            return None
        
        # Detect numbered clauses
        for pattern_name in ['sub_sub_sub', 'sub_sub', 'sub', 'main']:
            for match in patterns[pattern_name].finditer(text):
                label = match.group(1)
                pos = match.start()
                
                # Check if this is inside an appendix
                appendix_ctx = get_appendix_context(pos)
                
                # Namespace if in appendix
                if appendix_ctx:
                    display_label = f"A{appendix_ctx}.{label}"
                else:
                    display_label = label
                
                boundaries.append({
                    'pos': pos,
                    'label': display_label,
                    'original': label,
                    'type': pattern_name,
                    'appendix': appendix_ctx
                })
        
        # Detect lettered items
        for match in patterns['lettered'].finditer(text):
            label = match.group(1)
            pos = match.start()
            
            appendix_ctx = get_appendix_context(pos)
            
            if appendix_ctx:
                display_label = f"A{appendix_ctx}.{label}"
            else:
                display_label = label
            
            boundaries.append({
                'pos': pos,
                'label': display_label,
                'original': label,
                'type': 'lettered',
                'appendix': appendix_ctx
            })
        
        # Detect all-caps headings
        for match in patterns['heading'].finditer(text):
            heading = match.group(1).strip()
            pos = match.start()
            
            # Skip if it's an appendix marker
            if any(kw in heading.upper() for kw in ['APPENDIX', 'ANNEX', 'SCHEDULE', 'EXHIBIT', 'WITNESSETH']):
                continue
            
            # Verify it's mostly uppercase
            if not ImprovedClauseExtractor._is_all_caps(heading):
                continue
            
            appendix_ctx = get_appendix_context(pos)
            
            if appendix_ctx:
                display_label = f"A{appendix_ctx}.{heading}"
            else:
                display_label = heading
            
            boundaries.append({
                'pos': pos,
                'label': display_label,
                'original': heading,
                'type': 'heading',
                'appendix': appendix_ctx
            })
        
        # Add appendix headers themselves as boundaries
        for app in appendix_boundaries:
            boundaries.append({
                'pos': app['pos'],
                'label': app['label'],
                'original': app['label'],
                'type': 'appendix',
                'appendix': app['id']
            })
        
        # PHASE 4: Sort and deduplicate boundaries
        boundaries.sort(key=lambda x: x['pos'])
        
        # Remove duplicates at same position (keep highest priority)
        # Higher priority = earlier in list (will be kept)
        priority = ['appendix', 'sub_sub_sub', 'sub_sub', 'sub', 'main', 'lettered', 'heading']
        unique_boundaries = []
        i = 0
        while i < len(boundaries):
            current_pos = boundaries[i]['pos']
            group = [boundaries[i]]
            j = i + 1
            # Group boundaries within 5 chars (tighter grouping)
            while j < len(boundaries) and boundaries[j]['pos'] - current_pos < 5:
                group.append(boundaries[j])
                j += 1
            
            # Keep highest priority
            group.sort(key=lambda x: priority.index(x['type']) if x['type'] in priority else 999)
            unique_boundaries.append(group[0])
            i = j
        
        boundaries = unique_boundaries
        
        logger.info(f"Found {len(boundaries)} total clause boundaries")
        
        if not boundaries:
            return [{
                'clause_number': 'FULL_DOCUMENT',
                'category': 'Uncategorized',
                'start_char': 0,
                'end_char': len(text),
                'text': text.strip(),
                'metadata': {'type': 'unstructured'}
            }]
        
        # PHASE 5: Extract preamble
        first_boundary_pos = boundaries[0]['pos']
        if first_boundary_pos > 100:
            preamble_text = text[:first_boundary_pos].strip()
            if len(preamble_text) > 50:
                clauses.append({
                    'clause_number': 'AGREEMENT',
                    'category': 'PARTIES',
                    'start_char': 0,
                    'end_char': first_boundary_pos,
                    'text': preamble_text,
                    'metadata': {'type': 'preamble', 'appendix': None}
                })
        
        # PHASE 6: Extract each clause
        for i, boundary in enumerate(boundaries):
            # End position: stop BEFORE the next clause boundary marker
            if i < len(boundaries) - 1:
                # The next boundary position is where the next clause NUMBER starts
                # We want to end BEFORE that (at the preceding newline)
                next_boundary_pos = boundaries[i + 1]['pos']
                
                # Find the last newline before the next boundary
                # This ensures we don't include "2.2 The Agency..." in clause (g)
                end_pos = text.rfind('\n', boundary['pos'], next_boundary_pos)
                if end_pos == -1 or end_pos <= boundary['pos']:
                    # If no newline found, use the boundary position itself
                    # (but this shouldn't happen with proper document formatting)
                    end_pos = next_boundary_pos
            else:
                end_pos = len(text)
            
            # Extract text
            clause_text = text[boundary['pos']:end_pos].strip()
            
            # Skip if too short
            if len(clause_text) < 15:
                continue
            
            # Extract heading from first line
            first_line = re.match(r'^[^\n]{1,150}', clause_text)
            heading = first_line.group(0).strip() if first_line else boundary['label']
            
            # Categorize
            category = ImprovedClauseExtractor._categorize_clause(clause_text, boundary['label'])
            
            # Detect tables
            has_table = ImprovedClauseExtractor._detect_table(clause_text)
            
            clauses.append({
                'clause_number': boundary['label'],
                'category': category,
                'start_char': boundary['pos'],
                'end_char': end_pos,
                'text': clause_text,
                'metadata': {
                    'type': boundary['type'],
                    'has_table': has_table,
                    'appendix': boundary.get('appendix'),
                    'original_number': boundary.get('original')
                }
            })
        
        logger.info(f"Extracted {len(clauses)} clauses total")
        return clauses
    
    @staticmethod
    def _is_all_caps(text: str) -> bool:
        """Check if text is mostly uppercase."""
        if not text:
            return False
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return False
        uppercase = sum(1 for c in letters if c.isupper())
        return uppercase / len(letters) > 0.8
    
    @staticmethod
    def _detect_table(text: str) -> bool:
        """Detect if text contains table structures."""
        indicators = [
            r'[│┤├┼┴┬┌┐└┘─]',  # Box drawing
            r'\|\s+\w+\s+\|',  # Pipe-separated
            r'[-─]{3,}',  # Horizontal lines
            r'(?:\t|  {2,})\w+(?:\t|  {2,})\w+',  # Tab/space separated columns
        ]
        return any(re.search(pattern, text) for pattern in indicators)
    
    @staticmethod
    def _categorize_clause(text: str, clause_number: str) -> str:
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
