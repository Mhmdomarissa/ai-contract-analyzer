"""
Clause filtering and quality control utilities.

Provides robust filtering for:
- Table of Contents (TOC) entries
- Heading-only stubs
- Legal content validation
"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ClauseFilter:
    """Filter and validate extracted clauses for quality."""
    
    # Legal operators that indicate substantive content
    LEGAL_OPERATORS = [
        'shall', 'must', 'may', 'will', 'should', 'would',
        'subject to', 'provided that', 'notwithstanding',
        'hereby', 'herein', 'hereto', 'thereof', 'therein',
        'agree', 'agrees', 'agreed', 'undertake', 'undertakes',
        'warrant', 'warrants', 'represent', 'represents',
        'covenant', 'covenants', 'acknowledge', 'acknowledges'
    ]
    
    # TOC indicators
    TOC_KEYWORDS = [
        'table of contents', 'contents', 'index',
        'list of clauses', 'list of sections'
    ]
    
    def __init__(self, 
                 min_clause_words: int = 15,
                 min_clause_chars: int = 50,
                 max_stub_chars: int = 180):
        """
        Initialize clause filter.
        
        Args:
            min_clause_words: Minimum word count for substantive clauses
            min_clause_chars: Minimum character count
            max_stub_chars: Maximum chars for stub detection
        """
        self.min_clause_words = min_clause_words
        self.min_clause_chars = min_clause_chars
        self.max_stub_chars = max_stub_chars
    
    def is_toc_line(self, text: str, clause_number: str = None) -> bool:
        """
        Detect if a clause is a Table of Contents entry.
        
        TOC patterns:
        - "14. TERMINATION AND SUSPENSION 14" (number + heading + page)
        - "5.	FEES AND PAYMENT	5" (number + tab + heading + tab + page)
        - Lines containing TOC keywords
        
        Args:
            text: Clause text
            clause_number: Optional clause number for context
            
        Returns:
            True if this is a TOC entry
        """
        text_stripped = text.strip()
        
        # Pattern 1: Number + Heading + Page number
        # Examples: "14. TERMINATION 14", "5.	FEES	5"
        toc_pattern1 = re.compile(
            r'^\d+[\.\)]\s+[A-Z\s,&\-]+\s+\d+$',
            re.IGNORECASE
        )
        if toc_pattern1.match(text_stripped):
            logger.debug(f"TOC detected (pattern 1): {text_stripped[:100]}")
            return True
        
        # Pattern 2: Number + TAB + Heading + TAB + Page
        if '\t' in text_stripped:
            parts = text_stripped.split('\t')
            if len(parts) >= 3:
                # First part is number, last part is page number
                if re.match(r'^\d+[\.\)]?$', parts[0].strip()) and parts[-1].strip().isdigit():
                    logger.debug(f"TOC detected (pattern 2): {text_stripped[:100]}")
                    return True
        
        # Pattern 3: Contains TOC keywords
        text_lower = text_stripped.lower()
        if any(keyword in text_lower for keyword in self.TOC_KEYWORDS):
            logger.debug(f"TOC detected (keyword): {text_stripped[:100]}")
            return True
        
        # Pattern 4: Very short line with only heading and page number
        # "DEFINITIONS 3"
        if len(text_stripped) < 50:
            words = text_stripped.split()
            if len(words) >= 2 and words[-1].isdigit():
                # Last word is a page number, everything before is heading
                heading_part = ' '.join(words[:-1])
                if heading_part.isupper() or heading_part.istitle():
                    logger.debug(f"TOC detected (short heading + page): {text_stripped}")
                    return True
        
        return False
    
    def is_stub_clause(self, text: str, clause_number: str = None) -> bool:
        """
        Detect if a clause is just a heading stub without substantive content.
        
        Stub patterns:
        - Very short text ending with ":"
        - Contains "It is agreed that:" without following content
        - Only heading text, no legal operators
        
        Args:
            text: Clause text
            clause_number: Optional clause number for context
            
        Returns:
            True if this is a stub clause
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        
        # Quick length check
        if len(text_stripped) > self.max_stub_chars:
            return False
        
        # Pattern 1: Ends with ":" (likely a heading)
        if text_stripped.endswith(':'):
            logger.debug(f"Stub detected (ends with colon): {text_stripped}")
            return True
        
        # Pattern 2: Common stub patterns
        stub_patterns = [
            'it is agreed that:',
            'it is hereby agreed that:',
            'it is further agreed that:',
            'the parties agree as follows:',
            'as follows:',
            'the following terms apply:',
        ]
        
        if any(pattern in text_lower for pattern in stub_patterns):
            # Check if there's actual content after the pattern
            for pattern in stub_patterns:
                if pattern in text_lower:
                    idx = text_lower.index(pattern)
                    after_pattern = text_stripped[idx + len(pattern):].strip()
                    if len(after_pattern) < 20:  # Not much content after
                        logger.debug(f"Stub detected (agreement pattern without content): {text_stripped[:100]}")
                        return True
        
        # Pattern 3: Short text without legal operators
        word_count = len(text_stripped.split())
        if word_count < self.min_clause_words:
            # Check if it has ANY legal operator
            has_legal_operator = any(
                op in text_lower 
                for op in self.LEGAL_OPERATORS
            )
            if not has_legal_operator:
                # Also check it's not just a definition
                # Definitions can be short but are still substantive
                if not re.search(r'"[^"]+".*means', text_lower):
                    logger.debug(f"Stub detected (short without legal operators): {text_stripped[:100]}")
                    return True
        
        return False
    
    def has_substantive_content(self, text: str) -> bool:
        """
        Check if clause has substantive legal content.
        
        Content is substantive if it:
        - Contains legal operators (shall, must, may, etc.)
        - OR is long enough (>= min_clause_words)
        - OR contains definitions patterns
        
        Args:
            text: Clause text
            
        Returns:
            True if clause has substantive content
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        
        # Check 1: Length
        word_count = len(text_stripped.split())
        if word_count >= self.min_clause_words and len(text_stripped) >= self.min_clause_chars:
            return True
        
        # Check 2: Legal operators
        has_legal_operator = any(
            op in text_lower 
            for op in self.LEGAL_OPERATORS
        )
        if has_legal_operator:
            return True
        
        # Check 3: Definition patterns
        # "X" means..., "X" shall mean..., etc.
        definition_pattern = re.compile(
            r'"[^"]+".*\b(means?|refers?\s+to|includes?|denotes?)\b',
            re.IGNORECASE
        )
        if definition_pattern.search(text_stripped):
            return True
        
        # Check 4: Common clause patterns
        clause_patterns = [
            r'\b(the|this)\s+(party|parties|agreement|contract)',
            r'\b(either|both|each)\s+party\b',
            r'\b(rights?|obligations?|duties|responsibilities)\b',
        ]
        for pattern in clause_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def filter_clauses(self, clauses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Filter clauses and return quality metrics.
        
        Args:
            clauses: List of clause dictionaries
            
        Returns:
            Dictionary with:
                - valid_clauses: List of clauses that passed filters
                - removed_toc: List of TOC entries removed
                - removed_stubs: List of stub clauses removed
                - removed_no_content: List of clauses without substantive content
                - metrics: Summary statistics
        """
        valid_clauses = []
        removed_toc = []
        removed_stubs = []
        removed_no_content = []
        
        for clause in clauses:
            text = clause.get('text', '')
            clause_number = clause.get('clause_number', '')
            
            # Filter 1: TOC entries
            if self.is_toc_line(text, clause_number):
                removed_toc.append(clause)
                continue
            
            # Filter 2: Stub clauses
            if self.is_stub_clause(text, clause_number):
                removed_stubs.append(clause)
                continue
            
            # Filter 3: No substantive content
            if not self.has_substantive_content(text):
                removed_no_content.append(clause)
                continue
            
            valid_clauses.append(clause)
        
        metrics = {
            'total_extracted': len(clauses),
            'valid_clauses': len(valid_clauses),
            'removed_toc': len(removed_toc),
            'removed_stubs': len(removed_stubs),
            'removed_no_content': len(removed_no_content),
            'filter_rate': (len(clauses) - len(valid_clauses)) / len(clauses) if clauses else 0
        }
        
        logger.info(
            f"Clause filtering complete: {metrics['valid_clauses']}/{metrics['total_extracted']} valid "
            f"(TOC: {metrics['removed_toc']}, Stubs: {metrics['removed_stubs']}, "
            f"No content: {metrics['removed_no_content']})"
        )
        
        return {
            'valid_clauses': valid_clauses,
            'removed_toc': removed_toc,
            'removed_stubs': removed_stubs,
            'removed_no_content': removed_no_content,
            'metrics': metrics
        }


class ClauseSplitter:
    """Split long clauses into atomic semantic units."""
    
    def __init__(self, 
                 max_clause_chars: int = 2500,
                 min_split_chars: int = 100):
        """
        Initialize clause splitter.
        
        Args:
            max_clause_chars: Maximum chars before splitting
            min_split_chars: Minimum chars for a split section
        """
        self.max_clause_chars = max_clause_chars
        self.min_split_chars = min_split_chars
    
    def should_split(self, text: str) -> bool:
        """Check if clause should be split."""
        return len(text) > self.max_clause_chars
    
    def split_clause(self, clause: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split a long clause into smaller atomic clauses.
        
        Splitting strategies (in order):
        1. Numbered subclauses: (1), (2), (a), (b), (i), (ii)
        2. Heading + colon patterns: "DEFINITIONS:", "APPENDIX A:"
        3. Legal operator sentence boundaries: "shall", "must", "may"
        
        Args:
            clause: Clause dictionary with text, clause_number, etc.
            
        Returns:
            List of split clauses (or original if no split needed)
        """
        text = clause.get('text', '')
        
        if not self.should_split(text):
            return [clause]
        
        clause_number = clause.get('clause_number', '')
        logger.info(f"Splitting long clause {clause_number} ({len(text)} chars)")
        
        # Strategy 1: Split by numbered subclauses
        split_clauses = self._split_by_numbered_subclauses(clause)
        if len(split_clauses) > 1:
            logger.info(f"Split {clause_number} into {len(split_clauses)} subclauses")
            return split_clauses
        
        # Strategy 2: Split by headings + colon
        split_clauses = self._split_by_headings(clause)
        if len(split_clauses) > 1:
            logger.info(f"Split {clause_number} into {len(split_clauses)} sections by headings")
            return split_clauses
        
        # Strategy 3: Split by legal operator sentences
        split_clauses = self._split_by_legal_sentences(clause)
        if len(split_clauses) > 1:
            logger.info(f"Split {clause_number} into {len(split_clauses)} sentences")
            return split_clauses
        
        # No split possible, return original
        logger.warning(f"Could not split clause {clause_number} ({len(text)} chars)")
        return [clause]
    
    def _split_by_numbered_subclauses(self, clause: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split by numbered patterns like (1), (2), (a), (b), etc."""
        text = clause.get('text', '')
        clause_number = clause.get('clause_number', '')
        
        # Patterns for subclauses
        patterns = [
            re.compile(r'\n\s*\(([0-9]+)\)\s+', re.MULTILINE),  # (1), (2)
            re.compile(r'\n\s*\(([a-z])\)\s+', re.MULTILINE),   # (a), (b)
            re.compile(r'\n\s*\(([ivxlcdm]+)\)\s+', re.MULTILINE),  # (i), (ii)
            re.compile(r'\n\s*([0-9]+)\.\s+', re.MULTILINE),    # 1., 2.
            re.compile(r'\n\s*([a-z])\.\s+', re.MULTILINE),     # a., b.
        ]
        
        for pattern in patterns:
            matches = list(pattern.finditer(text))
            if len(matches) >= 2:  # Need at least 2 subclauses
                split_clauses = []
                
                for i, match in enumerate(matches):
                    subclause_num = match.group(1)
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                    
                    subclause_text = text[start:end].strip()
                    
                    if len(subclause_text) >= self.min_split_chars:
                        new_clause = clause.copy()
                        new_clause['text'] = subclause_text
                        new_clause['clause_number'] = f"{clause_number}.{subclause_num}"
                        new_clause['metadata'] = clause.get('metadata', {}).copy()
                        new_clause['metadata']['split_from'] = clause_number
                        new_clause['metadata']['split_method'] = 'numbered_subclause'
                        split_clauses.append(new_clause)
                
                if split_clauses:
                    # Add preamble if there's text before first subclause
                    if matches[0].start() > self.min_split_chars:
                        preamble_text = text[:matches[0].start()].strip()
                        preamble_clause = clause.copy()
                        preamble_clause['text'] = preamble_text
                        preamble_clause['clause_number'] = f"{clause_number}.0"
                        preamble_clause['metadata'] = clause.get('metadata', {}).copy()
                        preamble_clause['metadata']['split_from'] = clause_number
                        preamble_clause['metadata']['split_method'] = 'preamble'
                        split_clauses.insert(0, preamble_clause)
                    
                    return split_clauses
        
        return [clause]
    
    def _split_by_headings(self, clause: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split by heading + colon patterns."""
        text = clause.get('text', '')
        clause_number = clause.get('clause_number', '')
        
        # Pattern: ALL CAPS HEADING followed by colon
        heading_pattern = re.compile(
            r'\n\s*([A-Z][A-Z\s&,\-]{5,50}?):\s*\n',
            re.MULTILINE
        )
        
        matches = list(heading_pattern.finditer(text))
        if len(matches) >= 2:
            split_clauses = []
            
            for i, match in enumerate(matches):
                heading = match.group(1).strip()
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                
                section_text = text[start:end].strip()
                
                if len(section_text) >= self.min_split_chars:
                    new_clause = clause.copy()
                    new_clause['text'] = section_text
                    new_clause['clause_number'] = f"{clause_number}.{i+1}"
                    new_clause['heading'] = heading
                    new_clause['metadata'] = clause.get('metadata', {}).copy()
                    new_clause['metadata']['split_from'] = clause_number
                    new_clause['metadata']['split_method'] = 'heading'
                    split_clauses.append(new_clause)
            
            return split_clauses if split_clauses else [clause]
        
        return [clause]
    
    def _split_by_legal_sentences(self, clause: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split by sentences containing legal operators (fallback strategy)."""
        text = clause.get('text', '')
        clause_number = clause.get('clause_number', '')
        
        # Split by sentence boundaries
        sentences = re.split(r'\.( |\n)+', text)
        
        split_clauses = []
        current_text = ""
        split_count = 0
        
        for sentence in sentences:
            sentence_stripped = sentence.strip()
            if not sentence_stripped:
                continue
            
            current_text += sentence_stripped + ". "
            
            # Check if we should create a new clause
            if len(current_text) >= self.min_split_chars:
                # Check if sentence has legal operator
                has_legal = any(
                    op in current_text.lower() 
                    for op in ClauseFilter.LEGAL_OPERATORS
                )
                
                if has_legal:
                    split_count += 1
                    new_clause = clause.copy()
                    new_clause['text'] = current_text.strip()
                    new_clause['clause_number'] = f"{clause_number}.{split_count}"
                    new_clause['metadata'] = clause.get('metadata', {}).copy()
                    new_clause['metadata']['split_from'] = clause_number
                    new_clause['metadata']['split_method'] = 'legal_sentence'
                    split_clauses.append(new_clause)
                    current_text = ""
        
        # Add remaining text
        if current_text.strip() and len(current_text.strip()) >= self.min_split_chars:
            split_count += 1
            new_clause = clause.copy()
            new_clause['text'] = current_text.strip()
            new_clause['clause_number'] = f"{clause_number}.{split_count}"
            new_clause['metadata'] = clause.get('metadata', {}).copy()
            new_clause['metadata']['split_from'] = clause_number
            new_clause['metadata']['split_method'] = 'legal_sentence'
            split_clauses.append(new_clause)
        
        return split_clauses if len(split_clauses) > 1 else [clause]
