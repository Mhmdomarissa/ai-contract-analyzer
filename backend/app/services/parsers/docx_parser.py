"""
Advanced DOCX Parser with table extraction and intelligent formatting
Adapted from RAGFlow DocxParser
"""
import logging
import re
from io import BytesIO
from typing import List, Tuple
from collections import Counter

import pandas as pd
from docx import Document

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedDocxParser:
    """
    Advanced DOCX parser that extracts text, tables, and maintains structure.
    """
    
    def __init__(self):
        self.doc = None
    
    def parse(self, file_path: str = None, binary: bytes = None, 
              from_page: int = 0, to_page: int = 100000000) -> str:
        """
        Parse DOCX and return full text.
        
        Args:
            file_path: Path to DOCX file
            binary: Binary content of DOCX
            from_page: Start page (for pagination support)
            to_page: End page
            
        Returns:
            Full extracted text
        """
        sections, tables = self._parse_with_structure(file_path, binary, from_page, to_page)
        
        # Combine sections and tables
        text_parts = []
        for text, style in sections:
            if text.strip():
                text_parts.append(text)
        
        for table in tables:
            text_parts.extend(table)
        
        return "\n\n".join(text_parts)
    
    def _parse_with_structure(self, file_path: str = None, binary: bytes = None,
                              from_page: int = 0, to_page: int = 100000000) -> Tuple[List[Tuple[str, str]], List[List[str]]]:
        """
        Parse DOCX with structure preservation.
        
        Returns:
            Tuple of (sections, tables)
            - sections: List of (text, style_name) tuples
            - tables: List of table contents
        """
        # Load document
        if binary:
            self.doc = Document(BytesIO(binary))
        elif file_path:
            self.doc = Document(file_path)
        else:
            raise ValueError("Either file_path or binary must be provided")
        
        pn = 0  # page number
        sections = []
        
        # Extract paragraphs with page awareness
        for p in self.doc.paragraphs:
            if pn > to_page:
                break
            
            runs_within_page = []
            for run in p.runs:
                if pn > to_page:
                    break
                
                if from_page <= pn < to_page and p.text.strip():
                    runs_within_page.append(run.text)
                
                # Check for page break
                if 'lastRenderedPageBreak' in run._element.xml:
                    pn += 1
            
            paragraph_text = "".join(runs_within_page)
            style_name = p.style.name if hasattr(p.style, 'name') else ''
            
            if paragraph_text:
                sections.append((paragraph_text, style_name))
        
        # Extract tables
        tables = [self._extract_table_content(tb) for tb in self.doc.tables]
        
        return sections, tables
    
    def _extract_table_content(self, table) -> List[str]:
        """
        Extract and format table content intelligently.
        
        Args:
            table: python-docx Table object
            
        Returns:
            List of formatted table rows
        """
        # Convert table to DataFrame
        df_data = []
        for row in table.rows:
            df_data.append([cell.text for cell in row.cells])
        
        df = pd.DataFrame(df_data)
        
        return self._compose_table_content(df)
    
    def _compose_table_content(self, df: pd.DataFrame) -> List[str]:
        """
        Intelligently compose table content with header detection.
        
        Args:
            df: DataFrame representation of table
            
        Returns:
            List of formatted table content
        """
        def block_type(block_text: str) -> str:
            """Classify block type based on content patterns."""
            patterns = [
                (r"^(20|19)[0-9]{2}[年/-][0-9]{1,2}[月/-][0-9]{1,2}日*$", "Dt"),  # Date
                (r"^(20|19)[0-9]{2}年$", "Dt"),
                (r"^(20|19)[0-9]{2}[年/-][0-9]{1,2}月*$", "Dt"),
                (r"^[0-9]{1,2}[月/-][0-9]{1,2}日*$", "Dt"),
                (r"^第*[一二三四1-4]季度$", "Dt"),
                (r"^(20|19)[0-9]{2}年*[一二三四1-4]季度$", "Dt"),
                (r"^(20|19)[0-9]{2}[ABCDE]$", "DT"),
                (r"^[0-9.,+%/ -]+$", "Nu"),  # Number
                (r"^[0-9A-Z/\._~-]+$", "Ca"),  # Code/Category
                (r"^[A-Z]*[a-z' -]+$", "En"),  # English
                (r"^[0-9.,+-]+[0-9A-Za-z/$￥%<>（）()' -]+$", "NE"),  # Mixed
                (r"^.{1}$", "Sg")  # Single char
            ]
            
            for pattern, type_code in patterns:
                if re.search(pattern, block_text):
                    return type_code
            
            # Use simple token counting for text classification
            tokens = block_text.split()
            token_count = len([t for t in tokens if len(t) > 1])
            
            if token_count > 3:
                return "Tx" if token_count < 12 else "Lx"
            
            return "Ot"  # Other
        
        if len(df) < 2:
            return []
        
        # Determine dominant block type
        max_type = Counter([
            block_type(str(df.iloc[i, j])) 
            for i in range(1, len(df)) 
            for j in range(len(df.iloc[i, :]))
        ])
        max_type = max(max_type.items(), key=lambda x: x[1])[0]
        
        # Identify header rows
        hdrows = [0]  # First row is usually header
        
        if max_type == "Nu":  # For numeric tables, find non-numeric rows as headers
            for r in range(1, len(df)):
                tys = Counter([
                    block_type(str(df.iloc[r, j])) 
                    for j in range(len(df.iloc[r, :]))
                ])
                tys = max(tys.items(), key=lambda x: x[1])[0]
                if tys != max_type:
                    hdrows.append(r)
        
        # Compose formatted lines
        lines = []
        for i in range(1, len(df)):
            if i in hdrows:
                continue
            
            # Get relevant header rows for this data row
            hr = [r - i for r in hdrows if r - i < 0]
            t = len(hr) - 1
            while t > 0:
                if hr[t] - hr[t - 1] > 1:
                    hr = hr[t:]
                    break
                t -= 1
            
            # Build headers for each column
            headers = []
            for j in range(len(df.iloc[i, :])):
                header_parts = []
                for h in hr:
                    x = str(df.iloc[i + h, j]).strip()
                    if x and x not in header_parts:
                        header_parts.append(x)
                
                header_str = ",".join(header_parts)
                if header_str:
                    header_str += ": "
                headers.append(header_str)
            
            # Build cells with headers
            cells = []
            for j in range(len(df.iloc[i, :])):
                cell_value = str(df.iloc[i, j])
                if cell_value and cell_value.strip():
                    cells.append(headers[j] + cell_value)
            
            if cells:
                lines.append("; ".join(cells))
        
        # Return as list or joined based on column count
        col_count = len(df.iloc[0, :])
        if col_count > 3:
            return lines
        return ["\n".join(lines)]
    
    def __call__(self, file_path: str, binary: bytes = None, 
                 from_page: int = 0, to_page: int = 100000000) -> Tuple[List[Tuple[str, str]], List[List[str]]]:
        """
        Callable interface returning structured data.
        
        Returns:
            Tuple of (sections, tables)
        """
        return self._parse_with_structure(file_path, binary, from_page, to_page)
