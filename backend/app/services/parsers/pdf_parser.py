"""PDF parser using pdfplumber with fallback to PyMuPDF."""
import re
import logging
from pathlib import Path
from typing import Optional

import pdfplumber

from app.services.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """Parser for PDF files."""
    
    SUPPORTED_EXTENSIONS = {'.pdf'}
    
    def can_parse(self, file_path: str) -> bool:
        """Check if file is a PDF."""
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def parse(self, file_path: str) -> ParseResult:
        """Parse PDF and extract text."""
        self._log_parse_start(file_path)
        
        try:
            # Try pdfplumber first (primary method)
            text, page_count = self._parse_with_pdfplumber(file_path)
            
            # If no text extracted, try PyMuPDF fallback
            if not text.strip():
                logger.warning(f"pdfplumber extracted no text from {file_path}, trying PyMuPDF")
                text, page_count = self._parse_with_pymupdf(file_path)
            
            # If still no text, might be scanned PDF
            if not text.strip():
                logger.warning(f"No text extracted from {file_path}. Might be scanned PDF requiring OCR.")
                raise ValueError(
                    "No text could be extracted from this PDF. "
                    "It may be a scanned document requiring OCR processing."
                )
            
            # Remove page numbers from text
            text = self._remove_page_numbers(text)
            
            result = ParseResult(
                text=text,
                page_count=page_count,
                metadata={"parser": "pdfplumber", "file_path": file_path}
            )
            
            self._log_parse_complete(file_path, result)
            return result
            
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {str(e)}")
            raise
    
    def _parse_with_pdfplumber(self, file_path: str) -> tuple[str, int]:
        """Parse PDF using pdfplumber."""
        full_text = ""
        page_count = 0
        
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        
        return full_text, page_count
    
    def _parse_with_pymupdf(self, file_path: str) -> tuple[str, int]:
        """Parse PDF using PyMuPDF (fallback)."""
        try:
            import fitz  # PyMuPDF
            
            full_text = ""
            doc = fitz.open(file_path)
            page_count = len(doc)
            
            for page in doc:
                full_text += page.get_text() + "\n"
            
            doc.close()
            return full_text, page_count
            
        except ImportError:
            logger.warning("PyMuPDF (fitz) not installed, cannot use as fallback")
            return "", 0
    
    def _remove_page_numbers(self, text: str) -> str:
        """Remove page number markers from text."""
        # Remove patterns like [Page 1], Page 1, etc.
        text = re.sub(r'\[?Page\s*\d+\]?', '', text, flags=re.IGNORECASE)
        return text
