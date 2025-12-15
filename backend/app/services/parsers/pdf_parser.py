"""
Advanced PDF Parser with OCR, layout detection, and table recognition
Uses PyMuPDF (fitz) as primary parser for speed and accuracy
Falls back to pdfplumber for advanced table extraction if needed
"""
import logging
import re
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not available. Install with: pip install pymupdf")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber not available for table extraction fallback")

from .utils import num_tokens_from_string

# Import table extractor
try:
    from app.services.table_extractor import TableExtractor
    TABLE_EXTRACTOR_AVAILABLE = True
except ImportError:
    TABLE_EXTRACTOR_AVAILABLE = False
    logging.warning("Table extractor not available")

logger = logging.getLogger(__name__)


class AdvancedPdfParser:
    """
    Advanced PDF parser using PyMuPDF (fitz) for fast, accurate text extraction.
    Falls back to pdfplumber for complex table extraction if needed.
    """
    
    def __init__(self, use_ocr: bool = True, layout_recognition: bool = True, 
                 use_pdfplumber_for_tables: bool = False, extract_tables: bool = True):
        """
        Initialize PDF parser.
        
        Args:
            use_ocr: Enable OCR for scanned PDFs
            layout_recognition: Enable layout analysis
            use_pdfplumber_for_tables: Use pdfplumber for table extraction (slower but more accurate)
            extract_tables: Enable advanced table extraction with structured output
        """
        self.use_ocr = use_ocr
        self.layout_recognition = layout_recognition
        self.use_pdfplumber_for_tables = use_pdfplumber_for_tables
        self.extract_tables = extract_tables and TABLE_EXTRACTOR_AVAILABLE
        self.doc = None
        self.pdfplumber_pdf = None
        self.extracted_tables = []  # Store extracted tables
        
        # Initialize table extractor if available
        if self.extract_tables:
            self.table_extractor = TableExtractor(prefer_camelot=True)
        else:
            self.table_extractor = None
    
    def parse(self, file_path: str = None, binary: bytes = None,
              from_page: int = 0, to_page: int = 100000000) -> str:
        """
        Parse PDF and return full text using PyMuPDF (fitz).
        Also extracts tables if extract_tables is enabled.
        
        Args:
            file_path: Path to PDF file
            binary: Binary content of PDF
            from_page: Start page (0-indexed)
            to_page: End page
            
        Returns:
            Full extracted text (includes formatted table text)
        """
        # Extract tables first if enabled
        if self.extract_tables and file_path:
            try:
                self.extracted_tables = self.table_extractor.extract_tables_from_pdf(
                    file_path=file_path,
                    page_num=None  # Extract from all pages
                )
                logger.info(f"Extracted {len(self.extracted_tables)} tables from PDF")
            except Exception as e:
                logger.warning(f"Table extraction failed: {e}, continuing with text extraction")
                self.extracted_tables = []
        
        # COMMENTED OUT: PyMuPDF - using pdfplumber instead
        # if not PYMUPDF_AVAILABLE:
        #     logger.warning("PyMuPDF not available, falling back to pdfplumber")
        #     return self._parse_with_pdfplumber(file_path, binary, from_page, to_page)
        # 
        # try:
        #     # Use PyMuPDF for fast text extraction
        #     if binary:
        #         self.doc = fitz.open(stream=binary, filetype="pdf")
        #     elif file_path:
        #         self.doc = fitz.open(file_path)
        #     else:
        #         raise ValueError("Either file_path or binary must be provided")
        #     
        #     text_parts = []
        #     total_pages = len(self.doc)
        #     
        #     for page_num in range(from_page, min(to_page, total_pages)):
        #         page = self.doc[page_num]
        #         
        #         # Extract text with layout preservation
        #         page_text = page.get_text()
        #         
        #         if page_text and page_text.strip():
        #             text_parts.append(page_text)
        #         elif self.use_ocr:
        #             # Try OCR for scanned pages
        #             logger.info(f"Page {page_num + 1} appears to be scanned, attempting OCR")
        #             ocr_text = self._ocr_fallback_pymupdf(page)
        #             if ocr_text:
        #                 text_parts.append(ocr_text)
        #     
        #     full_text = "\n\n".join(text_parts)
        #     
        #     # Note: We don't append tables to text here because:
        #     # 1. Tables are already in the document text naturally
        #     # 2. We extract them separately for structured linking via metadata
        #     # 3. Appending would cause duplication
        #     
        #     return full_text
        # 
        # except Exception as e:
        #     logger.error(f"PyMuPDF parsing failed: {e}, falling back to pdfplumber")
        #     return self._parse_with_pdfplumber(file_path, binary, from_page, to_page)
        # 
        # finally:
        #     if self.doc:
        #         self.doc.close()
        #         self.doc = None
        
        # Force pdfplumber usage
        logger.info("Using pdfplumber for PDF parsing (PyMuPDF commented out)")
        return self._parse_with_pdfplumber(file_path, binary, from_page, to_page)
    
    def get_extracted_tables(self) -> List[Dict[str, Any]]:
        """
        Get extracted tables (structured format).
        
        Returns:
            List of structured table dictionaries
        """
        return self.extracted_tables
    
    def parse_with_layout(self, file_path: str = None, binary: bytes = None,
                          from_page: int = 0, to_page: int = 100000000) -> List[Dict[str, Any]]:
        """
        Parse PDF with layout information using PyMuPDF.
        
        Returns:
            List of sections with layout metadata
        """
        if not PYMUPDF_AVAILABLE:
            logger.warning("PyMuPDF not available, falling back to pdfplumber")
            return self._parse_with_layout_pdfplumber(file_path, binary, from_page, to_page)
        
        try:
            # Open PDF with PyMuPDF
            if binary:
                    self.doc = fitz.open(stream=binary, filetype="pdf")
            elif file_path:
                    self.doc = fitz.open(file_path)
            else:
                raise ValueError("Either file_path or binary must be provided")
            
            sections = []
            total_pages = len(self.doc)
            
            # Process each page
            for page_num in range(from_page, min(to_page, total_pages)):
                page = self.doc[page_num]
                
                # Extract text with layout
                page_sections = self._extract_page_with_layout_pymupdf(page, page_num)
                sections.extend(page_sections)
            
            return sections
        
        except Exception as e:
            logger.error(f"PyMuPDF layout parsing failed: {e}, falling back to pdfplumber")
            return self._parse_with_layout_pdfplumber(file_path, binary, from_page, to_page)
        
        finally:
            if self.doc:
                self.doc.close()
                self.doc = None
    
    def _extract_page_with_layout_pymupdf(self, page, page_num: int) -> List[Dict[str, Any]]:
        """
        Extract content from a single page using PyMuPDF.
        
        Args:
            page: PyMuPDF Page object
            page_num: Page number (0-indexed)
            
        Returns:
            List of sections from this page
        """
        sections = []
        
        # Extract text with layout preservation
        text_content = page.get_text()
        
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
        
        # Use pdfplumber for table extraction if requested
        if self.use_pdfplumber_for_tables and PDFPLUMBER_AVAILABLE:
            try:
                # Get tables using pdfplumber for this specific page
                # Note: This requires opening the PDF again with pdfplumber
                table_sections = self._extract_tables_pdfplumber_for_page(page_num)
                sections.extend(table_sections)
            except Exception as e:
                logger.warning(f"pdfplumber table extraction failed for page {page_num}: {e}")
        
        # OCR fallback for scanned pages
        if not text_content and self.use_ocr:
            logger.info(f"Page {page_num + 1} appears to be scanned, attempting OCR")
            ocr_text = self._ocr_fallback_pymupdf(page)
            if ocr_text:
                sections.append({
                    'type': 'text_ocr',
                    'text': ocr_text,
                    'page': page_num,
                    'bbox': None
                })
        
        return sections
    
    def _parse_with_pdfplumber(self, file_path: str = None, binary: bytes = None,
                               from_page: int = 0, to_page: int = 100000000) -> str:
        """Fallback to pdfplumber for text extraction."""
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("Neither PyMuPDF nor pdfplumber is available")
        
        try:
            if binary:
                self.pdfplumber_pdf = pdfplumber.open(BytesIO(binary))
            elif file_path:
                self.pdfplumber_pdf = pdfplumber.open(file_path)
            else:
                raise ValueError("Either file_path or binary must be provided")
            
            text_parts = []
            for page_num in range(from_page, min(to_page, len(self.pdfplumber_pdf.pages))):
                page = self.pdfplumber_pdf.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            return "\n\n".join(text_parts)
        
        finally:
            if self.pdfplumber_pdf:
                self.pdfplumber_pdf.close()
                self.pdfplumber_pdf = None
    
    def _parse_with_layout_pdfplumber(self, file_path: str = None, binary: bytes = None,
                                       from_page: int = 0, to_page: int = 100000000) -> List[Dict[str, Any]]:
        """Fallback to pdfplumber for layout extraction."""
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("Neither PyMuPDF nor pdfplumber is available")
        
        try:
            if binary:
                self.pdfplumber_pdf = pdfplumber.open(BytesIO(binary))
            elif file_path:
                self.pdfplumber_pdf = pdfplumber.open(file_path)
            else:
                raise ValueError("Either file_path or binary must be provided")
            
            sections = []
            for page_num in range(from_page, min(to_page, len(self.pdfplumber_pdf.pages))):
                page = self.pdfplumber_pdf.pages[page_num]
                page_sections = self._extract_page_with_layout_pdfplumber(page, page_num)
                sections.extend(page_sections)
            
            return sections
        
        finally:
            if self.pdfplumber_pdf:
                self.pdfplumber_pdf.close()
                self.pdfplumber_pdf = None
    
    def _extract_page_with_layout_pdfplumber(self, page, page_num: int) -> List[Dict[str, Any]]:
        """Extract content using pdfplumber (fallback method)."""
        sections = []
        
        # Extract tables
        tables = page.extract_tables()
        for table in tables:
            if table:
                formatted_table = self._format_table(table)
                if formatted_table:
                    sections.append({
                        'type': 'table',
                        'text': formatted_table,
                        'page': page_num,
                        'bbox': None
                    })
        
        # Extract text
        text_content = page.extract_text()
        if text_content and text_content.strip():
            paragraphs = self._split_into_paragraphs(text_content)
            for para in paragraphs:
                if para.strip():
                    sections.append({
                        'type': 'text',
                        'text': para,
                        'page': page_num,
                        'bbox': None
                    })
        
        return sections
    
    def _extract_tables_pdfplumber_for_page(self, page_num: int) -> List[Dict[str, Any]]:
        """Extract tables from a specific page using pdfplumber."""
        if not PDFPLUMBER_AVAILABLE:
            return []
        
        sections = []
        # Open PDF with pdfplumber just for this page (if we have file_path)
        # Note: This is a simplified approach - in production, you might want to cache the pdfplumber PDF
        try:
            # We need file_path to open with pdfplumber - this is a limitation
            # For now, skip table extraction if we only have binary data
            # In practice, table extraction can be done separately if needed
            logger.debug(f"Table extraction with pdfplumber requires file_path (not available in this context)")
            return []
        except Exception as e:
            logger.warning(f"Failed to extract tables with pdfplumber: {e}")
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
    
    def _ocr_fallback_pymupdf(self, page) -> str:
        """
        OCR fallback for scanned pages using PyMuPDF.
        
        Args:
            page: PyMuPDF Page object
            
        Returns:
            OCR text
        """
        try:
            # Convert page to image
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
            
            # Use pytesseract for OCR
            try:
                import pytesseract
                from PIL import Image
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Perform OCR
                text = pytesseract.image_to_string(img)
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
