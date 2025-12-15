"""
Advanced Table Extraction Service
Uses multiple methods (pdfplumber, camelot) for robust table extraction
Structures tables as JSON for better analysis and clause linking
"""
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from io import BytesIO

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber not available for table extraction")

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    logging.warning("camelot-py not available for advanced table extraction")

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    Advanced table extraction service with multiple extraction methods.
    Structures tables as JSON for better analysis and clause linking.
    """
    
    def __init__(self, prefer_camelot: bool = True):
        """
        Initialize table extractor.
        
        Args:
            prefer_camelot: Use camelot for complex tables (better accuracy)
        """
        self.prefer_camelot = prefer_camelot and CAMELOT_AVAILABLE
        self.extracted_tables = []  # Store extracted tables
    
    def extract_tables_from_pdf(
        self, 
        file_path: str = None, 
        binary: bytes = None,
        page_num: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract all tables from PDF using best available method.
        
        Args:
            file_path: Path to PDF file
            binary: Binary content of PDF
            page_num: Specific page to extract (None for all pages)
            
        Returns:
            List of structured table dictionaries
        """
        tables = []
        
        # Try camelot first (best for complex tables)
        if self.prefer_camelot and file_path:
            try:
                camelot_tables = self._extract_with_camelot(file_path, page_num)
                if camelot_tables:
                    logger.info(f"Extracted {len(camelot_tables)} tables using camelot")
                    tables.extend(camelot_tables)
                    return tables
            except Exception as e:
                logger.warning(f"Camelot extraction failed: {e}, falling back to pdfplumber")
        
        # Fallback to pdfplumber (more reliable, works with binary)
        if PDFPLUMBER_AVAILABLE:
            try:
                pdfplumber_tables = self._extract_with_pdfplumber(file_path, binary, page_num)
                if pdfplumber_tables:
                    logger.info(f"Extracted {len(pdfplumber_tables)} tables using pdfplumber")
                    tables.extend(pdfplumber_tables)
            except Exception as e:
                logger.error(f"pdfplumber extraction failed: {e}")
        
        return tables
    
    def _extract_with_camelot(
        self, 
        file_path: str, 
        page_num: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tables using camelot (best for complex tables with borders).
        
        Args:
            file_path: Path to PDF file
            page_num: Specific page (None for all)
            
        Returns:
            List of structured table dictionaries
        """
        if not CAMELOT_AVAILABLE:
            return []
        
        tables = []
        
        try:
            # Try lattice method first (for tables with borders)
            try:
                camelot_tables = camelot.read_pdf(
                    file_path, 
                    pages=str(page_num + 1) if page_num is not None else 'all',
                    flavor='lattice'
                )
            except:
                # Fallback to stream method (for tables without borders)
                camelot_tables = camelot.read_pdf(
                    file_path,
                    pages=str(page_num + 1) if page_num is not None else 'all',
                    flavor='stream'
                )
            
            for idx, table in enumerate(camelot_tables):
                structured_table = self._structure_table_camelot(table, idx)
                if structured_table:
                    tables.append(structured_table)
        
        except Exception as e:
            logger.error(f"Camelot extraction error: {e}")
            return []
        
        return tables
    
    def _extract_with_pdfplumber(
        self,
        file_path: str = None,
        binary: bytes = None,
        page_num: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract tables using pdfplumber (more reliable, works with binary).
        
        Args:
            file_path: Path to PDF file
            binary: Binary content of PDF
            page_num: Specific page (None for all)
            
        Returns:
            List of structured table dictionaries
        """
        if not PDFPLUMBER_AVAILABLE:
            return []
        
        tables = []
        
        try:
            # Open PDF
            if binary:
                pdf = pdfplumber.open(BytesIO(binary))
            elif file_path:
                pdf = pdfplumber.open(file_path)
            else:
                return []
            
            try:
                # Extract from specific page or all pages
                pages = [pdf.pages[page_num]] if page_num is not None else pdf.pages
                
                for page_idx, page in enumerate(pages):
                    page_tables = page.extract_tables()
                    
                    for table_idx, table in enumerate(page_tables):
                        if table and len(table) > 0:
                            structured_table = self._structure_table_pdfplumber(
                                table, 
                                page_idx if page_num is None else page_num,
                                table_idx
                            )
                            if structured_table:
                                tables.append(structured_table)
            
            finally:
                pdf.close()
        
        except Exception as e:
            logger.error(f"pdfplumber extraction error: {e}")
            return []
        
        return tables
    
    def _structure_table_camelot(
        self, 
        table, 
        table_idx: int
    ) -> Optional[Dict[str, Any]]:
        """
        Structure camelot table into JSON format.
        
        Args:
            table: Camelot table object
            table_idx: Table index
            
        Returns:
            Structured table dictionary
        """
        try:
            df = table.df
            
            # Convert to list of lists
            rows = df.values.tolist()
            
            if not rows or len(rows) < 1:
                return None
            
            # First row as headers
            headers = [str(cell).strip() if cell else f"Column_{i+1}" 
                      for i, cell in enumerate(rows[0])]
            data_rows = rows[1:] if len(rows) > 1 else []
            
            # Structure as JSON
            structured = {
                'table_id': f"table_{table_idx}",
                'method': 'camelot',
                'accuracy': float(table.accuracy) if hasattr(table, 'accuracy') else None,
                'headers': headers,
                'rows': [],
                'row_count': len(data_rows),
                'column_count': len(headers),
                'formatted_text': self._format_table_text(headers, data_rows),
                'json_data': self._table_to_json(headers, data_rows)
            }
            
            # Add rows as dictionaries
            for row in data_rows:
                row_dict = {}
                for i, cell in enumerate(row):
                    cell_value = str(cell).strip() if cell else ""
                    if i < len(headers):
                        row_dict[headers[i]] = cell_value
                    else:
                        row_dict[f"Column_{i+1}"] = cell_value
                
                if any(row_dict.values()):  # Skip empty rows
                    structured['rows'].append(row_dict)
            
            return structured
        
        except Exception as e:
            logger.error(f"Error structuring camelot table: {e}")
            return None
    
    def _structure_table_pdfplumber(
        self,
        table: List[List[str]],
        page_num: int,
        table_idx: int
    ) -> Optional[Dict[str, Any]]:
        """
        Structure pdfplumber table into JSON format.
        
        Args:
            table: 2D list of table cells
            page_num: Page number
            table_idx: Table index on page
            
        Returns:
            Structured table dictionary
        """
        try:
            if not table or len(table) < 1:
                return None
            
            # Clean cells
            cleaned = []
            for row in table:
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                if any(cleaned_row):  # Skip completely empty rows
                    cleaned.append(cleaned_row)
            
            if len(cleaned) < 1:
                return None
            
            # First row as headers (or generate if empty)
            first_row = cleaned[0]
            headers = []
            for i, cell in enumerate(first_row):
                if cell:
                    headers.append(cell)
                else:
                    headers.append(f"Column_{i+1}")
            
            # If no headers found, generate them
            if not any(headers):
                max_cols = max(len(row) for row in cleaned) if cleaned else 0
                headers = [f"Column_{i+1}" for i in range(max_cols)]
            
            data_rows = cleaned[1:] if len(cleaned) > 1 else []
            
            # Structure as JSON
            structured = {
                'table_id': f"table_p{page_num}_t{table_idx}",
                'method': 'pdfplumber',
                'page': page_num,
                'headers': headers,
                'rows': [],
                'row_count': len(data_rows),
                'column_count': len(headers),
                'formatted_text': self._format_table_text(headers, data_rows),
                'json_data': self._table_to_json(headers, data_rows)
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
            
            return structured
        
        except Exception as e:
            logger.error(f"Error structuring pdfplumber table: {e}")
            return None
    
    def _format_table_text(
        self, 
        headers: List[str], 
        rows: List[List[str]]
    ) -> str:
        """
        Format table as readable text for clause inclusion.
        
        Args:
            headers: Table headers
            rows: Table data rows
            
        Returns:
            Formatted text string
        """
        if not headers:
            return ""
        
        formatted_lines = []
        
        # Format each row as "header: value" pairs
        for row in rows:
            pairs = []
            for i, value in enumerate(row):
                if value and value.strip():
                    if i < len(headers) and headers[i]:
                        pairs.append(f"{headers[i]}: {value}")
                    else:
                        pairs.append(value)
            
            if pairs:
                formatted_lines.append("; ".join(pairs))
        
        return "\n".join(formatted_lines)
    
    def _table_to_json(
        self, 
        headers: List[str], 
        rows: List[List[str]]
    ) -> List[Dict[str, str]]:
        """
        Convert table to JSON array of objects.
        
        Args:
            headers: Table headers
            rows: Table data rows
            
        Returns:
            List of row dictionaries
        """
        json_data = []
        
        for row in rows:
            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    row_dict[headers[i]] = cell
                else:
                    row_dict[f"Column_{i+1}"] = cell
            
            if any(row_dict.values()):
                json_data.append(row_dict)
        
        return json_data
    
    def find_tables_in_text(
        self, 
        text: str, 
        extracted_tables: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find which tables are referenced in a given text block.
        
        Args:
            text: Text to search
            extracted_tables: List of extracted tables
            
        Returns:
            List of tables found in the text
        """
        found_tables = []
        text_lower = text.lower()
        
        for table in extracted_tables:
            # Check if table headers or content appear in text
            headers = table.get('headers', [])
            headers_text = " ".join(headers)
            formatted_text = table.get('formatted_text', '')
            
            # Multiple matching strategies:
            # 1. Check if any header appears in text
            header_match = any(header.lower() in text_lower for header in headers if header and len(header) > 2)
            
            # 2. Check if formatted text (first 200 chars) appears in text
            formatted_match = False
            if formatted_text:
                # Check first few lines of formatted text
                first_lines = "\n".join(formatted_text.split("\n")[:3])
                if first_lines.lower() in text_lower or len(set(first_lines.split()[:5]) & set(text_lower.split())) >= 2:
                    formatted_match = True
            
            # 3. Check if table content patterns match (for structured data like "Stack: X; Role: Y")
            pattern_match = False
            if headers and len(headers) >= 2:
                # Look for patterns like "Header1: Value1; Header2: Value2"
                pattern_parts = [f"{h.lower()}: " for h in headers[:3] if h]
                if any(part in text_lower for part in pattern_parts):
                    pattern_match = True
            
            # 4. Check if table data rows appear in text
            row_match = False
            rows = table.get('rows', [])
            if rows:
                # Check first few rows
                for row in rows[:2]:
                    row_values = [str(v).lower() for v in row.values() if v]
                    if row_values:
                        # Check if at least 2 values from row appear in text
                        matches = sum(1 for val in row_values if len(val) > 3 and val in text_lower)
                        if matches >= 2:
                            row_match = True
                            break
            
            # If any match found, link the table
            if header_match or formatted_match or pattern_match or row_match:
                found_tables.append(table)
        
        return found_tables

