"""
Python-based clause extraction using regex patterns.
Generic, flexible, and adaptable to various contract structures.
"""
import re
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class ClauseExtractor:
    """Extract clauses from contract text using flexible pattern matching."""
    
    # Main clauses: "1.", "2.", "3.", etc. (must be followed by space, not digit)
    MAIN_CLAUSE_PATTERN = re.compile(
        r'(?:^|\n)\s*(\d+)\.\s+(?=\S)',
        re.MULTILINE
    )
    
    # Sub-clauses: "1.1", "1.2", "2.1", etc. (not "1.1.1")
    SUB_CLAUSE_PATTERN = re.compile(
        r'(?:^|\n)\s*(\d+\.\d+)\s+(?=\S)',
        re.MULTILINE
    )
    
    # Sub-sub-clauses: "1.1.1", "1.1.2", etc.
    SUB_SUB_CLAUSE_PATTERN = re.compile(
        r'(?:^|\n)\s*(\d+\.\d+\.\d+)\s+(?=\S)',
        re.MULTILINE
    )
    
    # Lettered clauses: "(a)", "(b)", "(i)", "(ii)", etc.
    LETTERED_CLAUSE_PATTERN = re.compile(
        r'(?:^|\n)\s*(\([a-z]+\)|\([ivx]+\))\s+(?=\S)',
        re.MULTILINE | re.IGNORECASE
    )
    
    # Section headings: All caps lines (flexible detection)
    # Matches lines that are mostly/all uppercase with reasonable length
    SECTION_HEADING_PATTERN = re.compile(
        r'(?:^|\n)\s*([A-Z][A-Z\s]{6,})\s*\n',
        re.MULTILINE
    )
    
    # Appendices: "APPENDIX", "ANNEX", "SCHEDULE", etc.
    APPENDIX_PATTERN = re.compile(
        r'(?:^|\n)\s*((?:APPENDIX|ANNEX|SCHEDULE|EXHIBIT)\s+[A-Z0-9]+[:\s])',
        re.MULTILINE | re.IGNORECASE
    )
    
    # Definitions section - generic pattern (not hardcoded to specific text)
    # Looks for "DEFINITIONS" or "INTERPRETATION" headings
    DEFINITIONS_PATTERN = re.compile(
        r'(?:^|\n)\s*(DEFINITIONS?\s*(?:AND\s*)?(?:INTERPRETATION)?)\s*\n',
        re.MULTILINE | re.IGNORECASE
    )
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for consistent processing."""
        # Replace Windows line endings
        text = text.replace('\r\n', '\n')
        # Keep original spacing and newlines for accurate character mapping
        return text
    
    @staticmethod
    def _is_all_caps(text: str) -> bool:
        """Check if text is all uppercase (ignoring spaces and punctuation)."""
        if not text:
            return False
        # Remove spaces and common punctuation
        cleaned = re.sub(r'[\s\-\.,;:!?]', '', text)
        return cleaned.isupper() and len(cleaned) > 3
    
    @staticmethod
    def _categorize_clause(text: str, clause_number: str) -> str:
        """Categorize clause based on content and number."""
        text_upper = text.upper()
        
        # Common clause categories (flexible keyword matching)
        categories = {
            'DEFINITIONS': ['DEFINITION', 'DEFINITIONS', 'INTERPRETATION'],
            'PARTIES': ['PARTIES', 'PARTY', 'CLIENT', 'AGENCY', 'CONTRACTOR', 'VENDOR', 'SUPPLIER'],
            'TERM': ['TERM', 'DURATION', 'EFFECTIVE DATE', 'COMMENCEMENT', 'SOLE AGREEMENT', 'PERIOD'],
            'SCOPE': ['SCOPE', 'SERVICES', 'WORK', 'DELIVERABLES', 'PROVISION', 'OBLIGATIONS'],
            'PAYMENT': ['PAYMENT', 'FEE', 'PRICE', 'COMPENSATION', 'INVOICE', 'RATE', 'CHARGEABLE', 'COST'],
            'TERMINATION': ['TERMINATION', 'EXPIRATION', 'CANCELLATION', 'END OF AGREEMENT'],
            'CONFIDENTIALITY': ['CONFIDENTIAL', 'NON-DISCLOSURE', 'PRIVACY', 'PROPRIETARY'],
            'LIABILITY': ['LIABILITY', 'INDEMNIFICATION', 'DAMAGES', 'WARRANTY', 'WARRANTIES'],
            'DISPUTE': ['DISPUTE', 'ARBITRATION', 'GOVERNING LAW', 'JURISDICTION', 'LITIGATION'],
            'GENERAL': ['ENTIRE AGREEMENT', 'AMENDMENT', 'NOTICES', 'ASSIGNMENT', 'FORCE MAJEURE', 'SEVERABILITY'],
            'APPENDIX': ['APPENDIX', 'ANNEX', 'SCHEDULE', 'EXHIBIT'],
        }
        
        for category, keywords in categories.items():
            if any(keyword in text_upper for keyword in keywords):
                return category
        
        return 'Uncategorized'
    
    def _find_definitions_section(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Find definitions section boundaries generically.
        Returns (start_pos, end_pos) or None.
        """
        def_match = self.DEFINITIONS_PATTERN.search(text)
        if not def_match:
            return None
        
        def_start = def_match.start(1)
        
        # Find end by looking for next major section boundary
        # Look for: numbered clauses, section headings, or appendices
        end_patterns = [
            self.MAIN_CLAUSE_PATTERN,
            self.SUB_CLAUSE_PATTERN,
            self.SECTION_HEADING_PATTERN,
            self.APPENDIX_PATTERN,
        ]
        
        # Search for next boundary after definitions start
        min_end = len(text)
        for pattern in end_patterns:
            for match in pattern.finditer(text, def_start + 100):
                if match.start() < min_end:
                    min_end = match.start()
                break
        
        if min_end < len(text):
            return (def_start, min_end)
        
        return None
    
    def _find_all_boundaries(self, text: str) -> List[Tuple[int, str, str]]:
        """
        Find all clause boundaries in the text generically.
        Returns sorted list of (position, label, type) tuples.
        """
        boundaries = []
        
        # Find definitions section (if present) - treat as single boundary
        def_section = self._find_definitions_section(text)
        if def_section:
            def_start, def_end = def_section
            # Extract the definitions heading
            def_heading_match = self.DEFINITIONS_PATTERN.search(text, def_start, def_start + 100)
            if def_heading_match:
                boundaries.append((def_start, def_heading_match.group(1).strip(), 'definitions'))
        
        # Find main clauses (1., 2., 3., etc.)
        for match in self.MAIN_CLAUSE_PATTERN.finditer(text):
            boundaries.append((match.start(1), match.group(1), 'main'))
        
        # Find sub-clauses (1.1, 1.2, etc.)
        for match in self.SUB_CLAUSE_PATTERN.finditer(text):
            boundaries.append((match.start(1), match.group(1), 'sub'))
        
        # Find sub-sub-clauses (1.1.1, 1.1.2, etc.)
        for match in self.SUB_SUB_CLAUSE_PATTERN.finditer(text):
            boundaries.append((match.start(1), match.group(1), 'sub_sub'))
        
        # Find lettered clauses ((a), (b), (i), (ii), etc.)
        for match in self.LETTERED_CLAUSE_PATTERN.finditer(text):
            boundaries.append((match.start(1), match.group(1), 'lettered'))
        
        # Find section headings (all caps lines) - flexible detection
        for match in self.SECTION_HEADING_PATTERN.finditer(text):
            heading = match.group(1).strip()
            heading_start = match.start(1)
            
            # Skip if it's definitions (handled separately) or appendix (handled separately)
            heading_upper = heading.upper()
            if (heading_upper.startswith('DEFINITION') or 
                heading_upper.startswith('APPENDIX') or
                heading_upper.startswith('ANNEX') or
                heading_upper.startswith('SCHEDULE') or
                heading_upper.startswith('EXHIBIT')):
                continue
            
            # Verify it's actually all caps (not just starts with caps)
            if self._is_all_caps(heading):
                boundaries.append((heading_start, heading, 'heading'))
        
        # Find appendices (APPENDIX, ANNEX, SCHEDULE, EXHIBIT)
        for match in self.APPENDIX_PATTERN.finditer(text):
            boundaries.append((match.start(1), match.group(1).strip(), 'appendix'))
        
        # Sort by position
        boundaries.sort(key=lambda x: x[0])
        
        # Remove duplicates (same position)
        unique_boundaries = []
        seen_positions = set()
        for boundary in boundaries:
            pos = boundary[0]
            # Allow small overlap (within 5 chars) to handle formatting
            if not any(abs(pos - seen_pos) < 5 for seen_pos in seen_positions):
                unique_boundaries.append(boundary)
                seen_positions.add(pos)
        
        return unique_boundaries
    
    def extract_clauses(self, text: str, start_index: int = 1) -> List[Dict]:
        """
        Extract all clauses from contract text.
        Generic extraction that works with various contract structures.
        Each numbered section, section heading, and appendix is extracted as a separate clause.
        """
        if not text or not text.strip():
            return []
        
        normalized_text = self._normalize_text(text)
        clauses = []
        clause_id = start_index
        
        # Find all boundaries
        boundaries = self._find_all_boundaries(normalized_text)
        
        if not boundaries:
            # No boundaries found - treat entire text as one clause
            clause_text = normalized_text.strip()
            if clause_text:
                clauses.append({
                    "id": str(clause_id),
                    "category": self._categorize_clause(clause_text, ""),
                    "start_char": 0,
                    "end_char": len(clause_text),
                    "text": clause_text,
                })
            return clauses
        
        # Extract preamble (text before first boundary)
        first_boundary = boundaries[0]
        preamble_start = 0
        preamble_end = first_boundary[0]
        preamble_text = normalized_text[preamble_start:preamble_end].strip()
        
        if preamble_text and len(preamble_text) > 20:
            clauses.append({
                "id": str(clause_id),
                "category": "PREAMBLE",
                "start_char": preamble_start,
                "end_char": preamble_end,
                "text": preamble_text,
            })
            clause_id += 1
        
        # Extract each boundary as a separate clause
        for i, (boundary_start, boundary_label, boundary_type) in enumerate(boundaries):
            # Find end position (start of next boundary or end of text)
            if i + 1 < len(boundaries):
                next_start = boundaries[i + 1][0]
            else:
                next_start = len(normalized_text)
            
            # Generic handling for different boundary types
            if boundary_type == 'definitions':
                # Definitions section - extract from start to next boundary
                clause_text = normalized_text[boundary_start:next_start].strip()
                end_pos = next_start
            elif boundary_type == 'heading':
                # Section heading - check if it has content or is just a heading
                heading_line_end = normalized_text.find('\n', boundary_start)
                if heading_line_end == -1:
                    heading_line_end = boundary_start + len(boundary_label)
                
                # Check if there's substantial content after the heading
                content_start = heading_line_end + 1
                content_before_next = normalized_text[content_start:next_start].strip()
                
                # If next boundary is very close (within 50 chars), likely just a heading
                if next_start - heading_line_end < 50:
                    clause_text = normalized_text[boundary_start:heading_line_end].strip()
                    end_pos = heading_line_end
                else:
                    # Heading with content - include content up to next boundary
                    clause_text = normalized_text[boundary_start:next_start].strip()
                    end_pos = next_start
            else:
                # Numbered clauses, appendices, etc. - extract from boundary to next boundary
                clause_text = normalized_text[boundary_start:next_start].strip()
                end_pos = next_start
            
            # Remove trailing whitespace
            while end_pos > boundary_start and normalized_text[end_pos - 1].isspace():
                end_pos -= 1
            
            # Re-extract with proper end
            clause_text = normalized_text[boundary_start:end_pos].strip()
            
            if not clause_text or len(clause_text) < 3:
                continue
            
            # Categorize clause
            category = self._categorize_clause(clause_text, boundary_label)
            
            clauses.append({
                "id": str(clause_id),
                "category": category,
                "start_char": boundary_start,
                "end_char": end_pos,
                "text": clause_text,
            })
            
            clause_id += 1
        
        logger.info(f"Extracted {len(clauses)} clauses using Python-based extraction")
        return clauses


# Global instance for module-level function
_extractor = ClauseExtractor()


def extract_clauses(content: str, start_index: int = 1) -> List[Dict]:
    """
    Extract clauses from contract content.
    Generic extraction that works with various contract structures.
    
    Args:
        content: Contract text
        start_index: Starting clause ID
        
    Returns:
        List of clause dictionaries
    """
    return _extractor.extract_clauses(content, start_index)
