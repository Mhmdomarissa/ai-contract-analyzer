"""
Advanced Excel Parser with multi-sheet support and CSV handling
Adapted from RAGFlow ExcelParser
"""
import logging
import re
from io import BytesIO
from typing import List, Union

import pandas as pd

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedExcelParser:
    """
    Advanced Excel parser supporting XLSX, XLS, and CSV formats.
    """
    
    def __init__(self):
        self.workbook = None
    
    def parse(self, file_path: str = None, binary: bytes = None) -> str:
        """
        Parse Excel/CSV and return full text.
        
        Args:
            file_path: Path to Excel/CSV file
            binary: Binary content
            
        Returns:
            Full extracted text
        """
        sheets = self._parse_sheets(file_path, binary)
        
        # Combine all sheets
        text_parts = []
        for sheet_name, content in sheets:
            if content.strip():
                text_parts.append(f"=== {sheet_name} ===\n{content}")
        
        return "\n\n".join(text_parts)
    
    def _parse_sheets(self, file_path: str = None, binary: bytes = None) -> List[tuple]:
        """
        Parse all sheets from Excel workbook.
        
        Returns:
            List of (sheet_name, content) tuples
        """
        sheets = []
        
        # Determine if CSV
        is_csv = False
        if file_path:
            is_csv = file_path.lower().endswith('.csv')
        
        if is_csv:
            # Parse CSV
            try:
                if binary:
                    df = pd.read_csv(BytesIO(binary))
                else:
                    df = pd.read_csv(file_path)
                
                content = self._format_dataframe(df)
                sheets.append(("Sheet1", content))
            
            except Exception as e:
                logger.error(f"CSV parsing failed: {e}")
        
        else:
            # Parse Excel workbook
            try:
                if binary:
                    excel_file = pd.ExcelFile(BytesIO(binary))
                else:
                    excel_file = pd.ExcelFile(file_path)
                
                # Process each sheet
                for sheet_name in excel_file.sheet_names:
                    try:
                        df = pd.read_excel(excel_file, sheet_name=sheet_name)
                        content = self._format_dataframe(df)
                        
                        if content.strip():
                            sheets.append((sheet_name, content))
                    
                    except Exception as e:
                        logger.error(f"Failed to parse sheet {sheet_name}: {e}")
                
            except Exception as e:
                logger.error(f"Excel parsing failed: {e}")
        
        return sheets
    
    def _format_dataframe(self, df: pd.DataFrame) -> str:
        """
        Format DataFrame into readable text.
        
        Args:
            df: pandas DataFrame
            
        Returns:
            Formatted text
        """
        if df.empty:
            return ""
        
        # Clean column names
        df.columns = [self._clean_text(str(col)) for col in df.columns]
        
        # Remove rows where all values are NaN
        df = df.dropna(how='all')
        
        # Remove columns where all values are NaN
        df = df.dropna(axis=1, how='all')
        
        if df.empty:
            return ""
        
        # Format rows
        lines = []
        headers = list(df.columns)
        
        for idx, row in df.iterrows():
            # Build row text
            pairs = []
            for header, value in zip(headers, row):
                # Skip NaN values
                if pd.isna(value):
                    continue
                
                # Clean value
                value_str = self._clean_text(str(value))
                
                if value_str:
                    if header and not header.startswith('Unnamed'):
                        pairs.append(f"{header}: {value_str}")
                    else:
                        pairs.append(value_str)
            
            if pairs:
                lines.append("; ".join(pairs))
        
        return "\n".join(lines)
    
    def _clean_text(self, text: str) -> str:
        """
        Clean text by removing illegal characters and normalizing whitespace.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Remove illegal XML characters (common in Excel)
        illegal_chars = [
            (0x00, 0x08), (0x0B, 0x0C), (0x0E, 0x1F),
            (0x7F, 0x84), (0x86, 0x9F),
            (0xFDD0, 0xFDDF), (0xFFFE, 0xFFFF)
        ]
        
        illegal_ranges = [f"{chr(low)}-{chr(high)}" for low, high in illegal_chars if low <= 0xFFFF]
        illegal_pattern = f"[{''.join(illegal_ranges)}]"
        
        try:
            text = re.sub(illegal_pattern, '', text)
        except:
            pass
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None,
                          chunk_token_count: int = 128,
                          delimiter: str = "\n") -> List[str]:
        """
        Parse Excel with intelligent chunking.
        
        Args:
            file_path: Path to Excel/CSV
            binary: Binary content
            chunk_token_count: Target tokens per chunk
            delimiter: Row delimiter
            
        Returns:
            List of text chunks
        """
        # Get full text
        full_text = self.parse(file_path, binary)
        
        # Use chunking logic from txt_parser
        from .txt_parser import AdvancedTxtParser
        
        txt_parser = AdvancedTxtParser()
        return txt_parser._chunk_text(full_text, chunk_token_count, delimiter)
    
    def __call__(self, file_path: str, binary: bytes = None) -> List[tuple]:
        """
        Callable interface returning sheet data.
        
        Returns:
            List of (sheet_name, content) tuples
        """
        return self._parse_sheets(file_path, binary)
