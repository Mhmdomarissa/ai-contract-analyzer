"""
Advanced PDF Parser with OCR, layout detection, and table recognition
Adapted from RAGFlow PdfParser with vision capabilities
"""
import logging
import re
from io import BytesIO
from typing import List, Dict, Any, Tuple

import pdfplumber

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedPdfParser:
    """
    Advanced PDF parser with OCR fallback, layout detection, and table extraction.
    """
    
    def __init__(self, use_ocr: bool = True, layout_recognition: bool = True):
        """
        Initialize PDF parser.
        
        Args:
            use_ocr: Enable OCR for scanned PDFs
            layout_recognition: Enable layout analysis
        """
        self.use_ocr = use_ocr
        self.layout_recognition = layout_recognition
        self.pdf = None
    
    def parse(self, file_path: str = None, binary: bytes = None,
              from_page: int = 0, to_page: int = 100000000) -> str:
        """
        Parse PDF and return full text.
        
        Args:
            file_path: Path to PDF file
            binary: Binary content of PDF
            from_page: Start page (0-indexed)
            to_page: End page
            
        Returns:
            Full extracted text
        """
        sections = self.parse_with_layout(file_path, binary, from_page, to_page)
        
        # Combine all text blocks
        text_parts = []
        for section in sections:
            if 'text' in section and section['text'].strip():
                text_parts.append(section['text'])
        
        return "\n\n".join(text_parts)
    
    def parse_with_layout(self, file_path: str = None, binary: bytes = None,
                          from_page: int = 0, to_page: int = 100000000) -> List[Dict[str, Any]]:
        """
        Parse PDF with layout information.
        
        Returns:
            List of sections with layout metadata
        """
        # Open PDF
        if binary:
            self.pdf = pdfplumber.open(BytesIO(binary))
        elif file_path:
            self.pdf = pdfplumber.open(file_path)
        else:
            raise ValueError("Either file_path or binary must be provided")
        
        sections = []
        
        try:
            # Process each page
            for page_num in range(from_page, min(to_page, len(self.pdf.pages))):
                page = self.pdf.pages[page_num]
                
                # Extract text with layout
                page_sections = self._extract_page_with_layout(page, page_num)
                sections.extend(page_sections)
        
        finally:
            if self.pdf:
                self.pdf.close()
        
        return sections
    
    def _extract_page_with_layout(self, page, page_num: int) -> List[Dict[str, Any]]:
        """
        Extract content from a single page with layout analysis.
        
        Args:
            page: pdfplumber Page object
            page_num: Page number
            
        Returns:
            List of sections from this page
        """
        sections = []
        
        # Extract tables first
        tables = page.extract_tables()
        table_bboxes = []
        
        for table in tables:
            if table:
                # Format table
                formatted_table = self._format_table(table)
                if formatted_table:
                    sections.append({
                        'type': 'table',
                        'text': formatted_table,
                        'page': page_num,
                        'bbox': None  # Could calculate from table position
                    })
        
        # Extract text outside tables
        text_content = page.extract_text()
        
        if text_content and text_content.strip():
            # Split into paragraphs
            paragraphs = self._split_into_paragraphs(text_content)
            
            for para in paragraphs:
                if para.strip():
                    sections.append({
                        'type': 'text',
                        'text': para,
                        'page': page_num,
                        'bbox': None
                    })
        
        # OCR fallback for scanned pages
        elif self.use_ocr and not text_content:
            logger.info(f"Page {page_num} appears to be scanned, attempting OCR")
            ocr_text = self._ocr_fallback(page)
            if ocr_text:
                sections.append({
                    'type': 'text_ocr',
                    'text': ocr_text,
                    'page': page_num,
                    'bbox': None
                })
        
        return sections
    
    def _format_table(self, table: List[List[str]]) -> str:
        """
        Format extracted table into readable text.
        
        Args:
            table: 2D list of table cells
            
        Returns:
            Formatted table string
        """
        if not table or len(table) < 2:
            return ""
        
        # Clean cells
        cleaned = []
        for row in table:
            cleaned_row = [str(cell).strip() if cell else "" for cell in row]
            if any(cleaned_row):  # Skip empty rows
                cleaned.append(cleaned_row)
        
        if len(cleaned) < 2:
            return ""
        
        # Use first row as header
        headers = cleaned[0]
        rows = cleaned[1:]
        
        # Format rows
        formatted_rows = []
        for row in rows:
            if any(row):  # Skip empty rows
                # Combine header: value pairs
                pairs = []
                for header, value in zip(headers, row):
                    if value:
                        if header:
                            pairs.append(f"{header}: {value}")
                        else:
                            pairs.append(value)
                
                if pairs:
                    formatted_rows.append("; ".join(pairs))
        
        return "\n".join(formatted_rows)
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """
        Split text into logical paragraphs.
        
        Args:
            text: Raw text
            
        Returns:
            List of paragraphs
        """
        # Split on double newlines or large indentation changes
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean and filter
        cleaned = []
        for para in paragraphs:
            # Normalize whitespace
            para = re.sub(r'\s+', ' ', para).strip()
            if para:
                cleaned.append(para)
        
        return cleaned
    
    def _ocr_fallback(self, page) -> str:
        """
        OCR fallback for scanned pages.
        
        Args:
            page: pdfplumber Page object
            
        Returns:
            OCR text
        """
        try:
            # Convert page to image
            im = page.to_image(resolution=150)
            
            # Use pytesseract for OCR
            try:
                import pytesseract
                from PIL import Image
                
                # Get PIL image
                pil_image = im.original
                
                # Perform OCR
                text = pytesseract.image_to_string(pil_image)
                return text
            
            except ImportError:
                logger.warning("pytesseract not available for OCR")
                return ""
        
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None,
                          from_page: int = 0, to_page: int = 100000000,
                          chunk_token_count: int = 128,
                          delimiter: str = "\n!?。;!?") -> List[str]:
        """
        Parse PDF with intelligent chunking.
        
        Args:
            file_path: Path to PDF
            binary: Binary content
            from_page: Start page
            to_page: End page
            chunk_token_count: Target tokens per chunk
            delimiter: Sentence delimiters
            
        Returns:
            List of text chunks
        """
        # Get full text
        full_text = self.parse(file_path, binary, from_page, to_page)
        
        # Use chunking logic from txt_parser
        from .txt_parser import AdvancedTxtParser
        
        txt_parser = AdvancedTxtParser()
        return txt_parser._chunk_text(full_text, chunk_token_count, delimiter)
    
    def __call__(self, file_path: str, binary: bytes = None,
                 from_page: int = 0, to_page: int = 100000000) -> List[Dict[str, Any]]:
        """
        Callable interface returning structured data.
        
        Returns:
            List of sections with layout metadata
        """
        return self.parse_with_layout(file_path, binary, from_page, to_page)
