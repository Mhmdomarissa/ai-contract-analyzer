"""Clause extraction service - converts provided script logic into production service."""
import re
import uuid as uuid_lib
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ClauseExtractor:
    """Extract clauses from contract text using regex patterns."""
    
    def __init__(self):
        """Initialize clause extractor."""
        self.main_clause_pattern = re.compile(r'(^|\n)(\d{1,2}[.)])\s')
        self.sub_clause_pattern = re.compile(r'(?<=\n)([a-z]\))\s')
        self.toc_pattern = re.compile(r'\.{5,}')  # 5+ consecutive dots indicate TOC
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text by removing excessive whitespace.
        
        Args:
            text: Raw text to normalize
            
        Returns:
            Normalized text
        """
        # Remove multiple newlines
        text = re.sub(r'\n{2,}', '\n', text)
        # Remove multiple spaces
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()
    
    def capitalize_titles(self, text: str) -> str:
        """
        Capitalize clause titles for consistency.
        
        Args:
            text: Text to capitalize
            
        Returns:
            Text with capitalized titles
        """
        # Capitalize main clause titles (e.g., "1. introduction" -> "1. INTRODUCTION")
        text = re.sub(
            r'(^|\n)(\d{1,2}[.)])\s*([a-z][^\n]*)',
            lambda m: f"{m.group(1)}{m.group(2)} {m.group(3).upper()}",
            text
        )
        
        # Capitalize sub-clause titles (e.g., "a) scope" -> "a) SCOPE")
        text = re.sub(
            r'(?<=\n)([a-z]\))\s*([a-z][^\n]*)',
            lambda m: f"{m.group(1)} {m.group(2).upper()}",
            text
        )
        
        return text
    
    def split_into_clauses(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into structured clauses with UUIDs.
        
        Args:
            text: Normalized and capitalized text
            
        Returns:
            List of clause dictionaries with structure:
            {
                "uuid": str,
                "clause number": str,
                "Clause content": str,
                "sub_clauses": [...]  # Optional
            }
        """
        main_matches = list(self.main_clause_pattern.finditer(text))
        
        if not main_matches:
            logger.warning("No main clauses found in text")
            return []
        
        clauses = []
        
        # Extract each main clause
        for i, match in enumerate(main_matches):
            start = match.start(2)
            end = main_matches[i + 1].start(2) if i + 1 < len(main_matches) else len(text)
            clause_text = text[start:end].strip()
            
            # Remove any = separator lines
            clause_text = re.sub(r'=+\s*', '', clause_text)
            
            # Extract sub-clauses
            sub_matches = list(self.sub_clause_pattern.finditer(clause_text))
            sub_clauses = []
            
            if sub_matches:
                main_text_parts = []
                
                for j, s_match in enumerate(sub_matches):
                    s_start = s_match.start()
                    s_end = sub_matches[j + 1].start() if j + 1 < len(sub_matches) else len(clause_text)
                    sub_text = clause_text[s_start:s_end].strip()
                    
                    # Create sub-clause with UUID
                    sub_clauses.append({
                        "uuid": str(uuid_lib.uuid4()),
                        "clause number": s_match.group(1),
                        "Clause content": sub_text
                    })
                    
                    # Collect main text before first sub-clause
                    if j == 0:
                        main_text_parts.append(clause_text[:s_start].strip())
                
                # Update clause text to only main content
                clause_text = "\n".join(main_text_parts).strip()
            
            # Create main clause with UUID
            clause_dict = {
                "uuid": str(uuid_lib.uuid4()),
                "clause number": match.group(2),
                "Clause content": clause_text
            }
            
            if sub_clauses:
                clause_dict["sub_clauses"] = sub_clauses
            
            clauses.append(clause_dict)
        
        logger.info(f"Extracted {len(clauses)} main clauses with {sum(len(c.get('sub_clauses', [])) for c in clauses)} sub-clauses")
        return clauses
    
    def remove_toc_entries(self, clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove Table of Contents entries.
        
        Identifies TOC entries by looking for lines with multiple dots (.....)
        which usually indicate page number spacers.
        
        Args:
            clauses: List of clause dictionaries
            
        Returns:
            Filtered list without TOC entries
        """
        cleaned_clauses = []
        removed_count = 0
        
        for clause in clauses:
            content = clause.get("Clause content", "")
            
            # If content contains TOC pattern (5+ dots), skip it
            if self.toc_pattern.search(content):
                removed_count += 1
                logger.debug(f"Removed TOC entry: {clause.get('clause number')}")
                continue
            
            cleaned_clauses.append(clause)
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} TOC entries")
        
        return cleaned_clauses
    
    def remove_unnumbered_clauses(self, clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove clauses that have no proper numbering.
        
        Args:
            clauses: List of clause dictionaries
            
        Returns:
            Filtered list without unnumbered clauses
        """
        real_clauses = [
            c for c in clauses 
            if not c["clause number"].startswith("UNNUMBERED")
        ]
        
        removed = len(clauses) - len(real_clauses)
        if removed > 0:
            logger.info(f"Removed {removed} unnumbered clauses")
        
        return real_clauses
    
    def extract_clauses(
        self,
        raw_text: str,
        remove_toc: bool = True,
        remove_unnumbered: bool = True
    ) -> Dict[str, Any]:
        """
        Complete extraction pipeline.
        
        Args:
            raw_text: Raw extracted text from document
            remove_toc: Whether to remove TOC entries
            remove_unnumbered: Whether to remove unnumbered clauses
            
        Returns:
            Dictionary with:
            {
                "raw_text": str,
                "normalized_text": str,
                "capitalized_text": str,
                "clauses": List[Dict],
                "stats": {
                    "total_clauses": int,
                    "main_clauses": int,
                    "sub_clauses": int
                }
            }
        """
        logger.info("Starting clause extraction pipeline")
        
        # Step 1: Normalize text
        logger.info("Step 1: Normalizing text")
        normalized_text = self.normalize_text(raw_text)
        
        # Step 2: Capitalize titles
        logger.info("Step 2: Capitalizing titles")
        capitalized_text = self.capitalize_titles(normalized_text)
        
        # Step 3: Split into clauses
        logger.info("Step 3: Splitting into clauses")
        clauses = self.split_into_clauses(capitalized_text)
        
        # Step 4: Remove unnumbered (if requested)
        if remove_unnumbered:
            logger.info("Step 4: Removing unnumbered clauses")
            clauses = self.remove_unnumbered_clauses(clauses)
        
        # Step 5: Remove TOC entries (if requested)
        if remove_toc:
            logger.info("Step 5: Removing TOC entries")
            clauses = self.remove_toc_entries(clauses)
        
        # Calculate stats
        main_clause_count = len(clauses)
        sub_clause_count = sum(len(c.get("sub_clauses", [])) for c in clauses)
        total_clause_count = main_clause_count + sub_clause_count
        
        logger.info(
            f"Extraction complete: {total_clause_count} total clauses "
            f"({main_clause_count} main, {sub_clause_count} sub)"
        )
        
        return {
            "raw_text": raw_text,
            "normalized_text": normalized_text,
            "capitalized_text": capitalized_text,
            "clauses": clauses,
            "stats": {
                "total_clauses": total_clause_count,
                "main_clauses": main_clause_count,
                "sub_clauses": sub_clause_count
            }
        }
