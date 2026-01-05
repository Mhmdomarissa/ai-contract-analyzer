"""
Advanced DOCX Parser with table extraction and intelligent formatting
Adapted from RAGFlow DocxParser
Enhanced with docx2python for numbered list preservation
"""
import logging
import re
from io import BytesIO
from typing import List, Tuple
from collections import Counter

import pandas as pd
from docx import Document

try:
    from docx2python import docx2python
    HAS_DOCX2PYTHON = True
except ImportError:
    HAS_DOCX2PYTHON = False
    logger.warning("docx2python not installed - numbered lists may not be preserved correctly")

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedDocxParser:
    """
    Advanced DOCX parser that extracts text, tables, and maintains structure.
    """
    
    def __init__(self, extract_tables: bool = True, preserve_numbering: bool = True):
        """
        Initialize DOCX parser.
        
        Args:
            extract_tables: Enable structured table extraction
            preserve_numbering: Use docx2python to preserve numbered lists (requires docx2python)
        """
        self.doc = None
        self.extract_tables = extract_tables
        self.preserve_numbering = preserve_numbering and HAS_DOCX2PYTHON
        self.extracted_tables = []  # Store structured tables
    
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
        logger.info(f"🔍 Starting DOCX parsing: {file_path}")
        
        # Use docx2python if available and numbering preservation is enabled
        if self.preserve_numbering and file_path:
            try:
                text = self._parse_with_docx2python(file_path)
                if text:
                    logger.info(
                        f"✅ docx2python extraction complete: "
                        f"{len(text)} chars, last 100 chars: ...{text[-100:]}"
                    )
                    return text
            except Exception as e:
                logger.warning(f"docx2python parsing failed, falling back to python-docx: {e}")
        
        # Fall back to standard parsing
        sections, tables = self._parse_with_structure(file_path, binary, from_page, to_page)
        
        logger.info(
            f"📄 Extracted {len(sections)} sections, {len(tables)} tables from DOCX"
        )
        
        # Combine sections and tables
        text_parts = []
        for text, style in sections:
            if text.strip():
                text_parts.append(text)
        
        for table in tables:
            text_parts.extend(table)
        
        full_text = "\n\n".join(text_parts)
        
        logger.info(
            f"✅ DOCX extraction complete: "
            f"{len(full_text)} chars total, "
            f"last 200 chars: ...{full_text[-200:] if len(full_text) > 200 else full_text}"
        )
        
        return full_text
    
    def _parse_with_docx2python(self, file_path: str) -> str:
        """
        Parse DOCX using docx2python to preserve numbered lists.
        
        Args:
            file_path: Path to DOCX file
            
        Returns:
            Extracted text with numbering preserved
        """
        if not HAS_DOCX2PYTHON:
            return None
        
        try:
            # Extract content with docx2python
            doc_result = docx2python(file_path)
            
            # Get text content
            text = doc_result.text
            
            # Also extract tables if enabled
            if self.extract_tables:
                # Load with python-docx for structured table extraction
                self.doc = Document(file_path)
                self.extracted_tables = []
                for idx, table in enumerate(self.doc.tables):
                    structured = self._extract_structured_table(table, idx)
                    if structured:
                        self.extracted_tables.append(structured)
            
            # Clean up the docx2python output
            # It uses special markers that we should clean
            text = text.replace('----', '\n')  # docx2python uses ---- for separators
            text = re.sub(r'\n{3,}', '\n\n', text)  # Remove excessive newlines
            
            return text
            
        except Exception as e:
            logger.error(f"Error in docx2python parsing: {e}")
            return None
    
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
        
        # Extract structured tables if enabled
        if self.extract_tables:
            self.extracted_tables = []
            for idx, table in enumerate(self.doc.tables):
                structured = self._extract_structured_table(table, idx)
                if structured:
                    self.extracted_tables.append(structured)
        
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
    
    def _extract_structured_table(self, table, table_idx: int) -> dict:
        """
        Extract table as structured JSON format (similar to PDF table extractor).
        
        Args:
            table: python-docx Table object
            table_idx: Table index
            
        Returns:
            Structured table dictionary
        """
        try:
            # Convert table to list of lists
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip() if cell.text else "" for cell in row.cells])
            
            if not rows or len(rows) < 1:
                return None
            
            # First row as headers
            headers = rows[0] if rows else []
            # If no headers, generate them
            if not any(headers):
                max_cols = max(len(row) for row in rows) if rows else 0
                headers = [f"Column_{i+1}" for i in range(max_cols)]
            
            data_rows = rows[1:] if len(rows) > 1 else []
            
            # Format as text for clause inclusion
            formatted_lines = []
            for row in data_rows:
                pairs = []
                for i, cell in enumerate(row):
                    if cell and cell.strip():
                        if i < len(headers) and headers[i]:
                            pairs.append(f"{headers[i]}: {cell}")
                        else:
                            pairs.append(cell)
                if pairs:
                    formatted_lines.append("; ".join(pairs))
            
            # Structure as JSON
            structured = {
                'table_id': f"table_docx_{table_idx}",
                'method': 'docx',
                'headers': headers,
                'rows': [],
                'row_count': len(data_rows),
                'column_count': len(headers),
                'formatted_text': "\n".join(formatted_lines),
                'json_data': []
            }
            
            # Add rows as dictionaries
            for row in data_rows:
                row_dict = {}
                for i, cell in enumerate(row):
                    if i < len(headers):
                        row_dict[headers[i]] = cell
                    else:
                        row_dict[f"Column_{i+1}"] = cell
                
                if any(row_dict.values()):  # Skip empty rows
                    structured['rows'].append(row_dict)
                    structured['json_data'].append(row_dict)
            
            return structured
        
        except Exception as e:
            logger.error(f"Error structuring DOCX table: {e}")
            return None
    
    def get_extracted_tables(self) -> List[dict]:
        """
        Get extracted structured tables.
        
        Returns:
            List of structured table dictionaries
        """
        return self.extracted_tables
    
    def __call__(self, file_path: str, binary: bytes = None, 
                 from_page: int = 0, to_page: int = 100000000) -> Tuple[List[Tuple[str, str]], List[List[str]]]:
        """
        Callable interface returning structured data.
        
        Returns:
            Tuple of (sections, tables)
        """
        return self._parse_with_structure(file_path, binary, from_page, to_page)
