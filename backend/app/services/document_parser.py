import logging
import mimetypes
import os
from pathlib import Path

import docx
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader

# Import advanced parsers
from .parsers.pdf_parser import AdvancedPdfParser
from .parsers.docx_parser import AdvancedDocxParser
from .parsers.excel_parser import AdvancedExcelParser
from .parsers.ppt_parser import AdvancedPptParser
from .parsers.html_parser import AdvancedHtmlParser
from .parsers.markdown_parser import AdvancedMarkdownParser
from .parsers.json_parser import AdvancedJsonParser
from .parsers.txt_parser import AdvancedTxtParser

logger = logging.getLogger(__name__)

# Flag to use advanced parsers (set to True after dependencies are installed)
USE_ADVANCED_PARSERS = True

# Configuration constants
MAX_FILE_SIZE_MB = 100  # Maximum file size in MB
MIN_TEXT_LENGTH = 10    # Minimum extracted text length
SUPPORTED_EXTENSIONS = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv',
    '.pptx', '.ppt', '.html', '.htm', '.md', '.txt',
    '.json', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'
}


class DocumentParsingError(Exception):
    """Base exception for document parsing errors."""
    pass


class FileSizeError(DocumentParsingError):
    """File size exceeds maximum allowed."""
    pass


class FileTypeError(DocumentParsingError):
    """Unsupported file type."""
    pass


class EncryptedFileError(DocumentParsingError):
    """File is encrypted and cannot be parsed."""
    pass


class EmptyContentError(DocumentParsingError):
    """File parsed but no text content extracted."""
    pass


def parse_document(file_path: str) -> str:
    """
    Extract text from a file (supports all major formats).
    
    Supports: PDF, DOCX, XLSX, PPTX, HTML, Markdown, JSON, TXT, Images
    
    Args:
        file_path: Path to the file to parse.
        
    Returns:
        Extracted text as a string.
        
    Raises:
        FileNotFoundError: File does not exist
        FileSizeError: File exceeds maximum size
        FileTypeError: Unsupported file type
        EncryptedFileError: File is encrypted
        EmptyContentError: No text content extracted
        DocumentParsingError: General parsing error
    """
    path = Path(file_path)
    
    # Validation 1: File exists
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Validation 2: File size
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise FileSizeError(
            f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed ({MAX_FILE_SIZE_MB}MB). "
            f"Please upload a smaller file."
        )
    
    # Validation 3: File type
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise FileTypeError(
            f"Unsupported file type: {suffix}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    
    # Validation 4: Check for encrypted PDF
    if suffix == ".pdf":
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                raise EncryptedFileError(
                    "PDF is encrypted. Please provide an unencrypted version of the document."
                )
        except EncryptedFileError:
            raise
        except Exception as e:
            logger.warning(f"Could not check PDF encryption status: {e}")

    mime_type, _ = mimetypes.guess_type(path)
    logger.info(f"Parsing file: {file_path} ({file_size_mb:.1f}MB), Type: {suffix}, Mime: {mime_type}")

    text = ""
    method = "unknown"

    try:
        suffix = path.suffix.lower()
        
        # Try advanced parsers first if enabled
        if USE_ADVANCED_PARSERS:
            try:
                if suffix == ".pdf":
                    # Use pdfplumber for PDF parsing
                    parser = AdvancedPdfParser(
                        use_ocr=True, 
                        layout_recognition=True,
                        extract_tables=True,
                        use_pdfplumber_for_tables=True
                    )
                    text = parser.parse(file_path=str(path))
                    method = "pdfplumber"
                    logger.info(f"✅ Extraction complete using pdfplumber (length: {len(text)} chars)")
                    
                elif suffix in [".docx", ".doc"]:
                    parser = AdvancedDocxParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_docx"
                    
                elif suffix in [".xlsx", ".xls", ".csv"]:
                    parser = AdvancedExcelParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_excel"
                    
                elif suffix in [".pptx", ".ppt"]:
                    parser = AdvancedPptParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_ppt"
                    
                elif suffix in [".html", ".htm"]:
                    parser = AdvancedHtmlParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_html"
                    
                elif suffix in [".md", ".markdown"]:
                    parser = AdvancedMarkdownParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_markdown"
                    
                elif suffix in [".json", ".jsonl"]:
                    parser = AdvancedJsonParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_json"
                    
                elif suffix == ".txt":
                    parser = AdvancedTxtParser()
                    text = parser.parse(file_path=str(path))
                    method = "advanced_txt"
                    
                elif suffix in [".jpg", ".jpeg", ".png", ".tiff", ".bmp"]:
                    # Use legacy OCR for images
                    text, method = _parse_image(path)
                    
                else:
                    raise FileTypeError(f"Unsupported file type: {suffix}")
                
            except FileTypeError:
                raise
            except EncryptedFileError:
                raise
            except Exception as e:
                logger.warning(f"Advanced parser failed ({suffix}): {e}, falling back to legacy parsers")
                # Fall through to legacy parsers
                text = ""
        
        # Legacy parsers fallback
        if not text:
            if suffix == ".pdf":
                text, method = _parse_pdf(path)
            elif suffix in [".docx", ".doc"]:
                text, method = _parse_docx(path)
            elif suffix in [".jpg", ".jpeg", ".png", ".tiff", ".bmp"]:
                text, method = _parse_image(path)
            elif suffix in [".txt"]:
                text, method = _parse_txt(path)
            else:
                raise FileTypeError(f"Unsupported file type: {suffix}")
        
        # Validation 5: Check extracted content
        if not text or len(text.strip()) < MIN_TEXT_LENGTH:
            raise EmptyContentError(
                f"Could not extract meaningful text from document. "
                f"Extracted only {len(text.strip())} characters (minimum: {MIN_TEXT_LENGTH}). "
                f"The file may be empty, corrupted, or consist only of images/scans."
            )
            
        logger.info(f"✅ Successfully extracted {len(text)} chars using {method} from {file_path}")
        return text

    except (FileNotFoundError, FileSizeError, FileTypeError, EncryptedFileError, EmptyContentError):
        # Re-raise our custom exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error parsing document {file_path}: {e}", exc_info=True)
        raise DocumentParsingError(f"Failed to parse document: {str(e)}") from e


def _parse_txt(path: Path) -> tuple[str, str]:
    """Parse a plain text file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        return text, "plain_text"
    except UnicodeDecodeError:
        # Try with a different encoding if UTF-8 fails
        try:
            with open(path, 'r', encoding='latin-1') as f:
                text = f.read()
            return text, "plain_text_latin1"
        except Exception as e:
            logger.error(f"TXT parsing failed with latin-1: {e}")
            raise
    except Exception as e:
        logger.error(f"TXT parsing failed: {e}")
        raise


def _parse_pdf(path: Path) -> tuple[str, str]:
    text = ""
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        
        # If text is very short, try OCR (scanned PDF)
        # Threshold is arbitrary, but < 100 chars for a contract page is suspicious
        if len(text.strip()) < 100:
            logger.info(f"PDF text content low ({len(text.strip())} chars), attempting OCR...")
            return _parse_pdf_ocr(path)
            
        return text, "pypdf"
    except Exception as e:
        logger.warning(f"pypdf failed: {e}, falling back to OCR")
        return _parse_pdf_ocr(path)


def _parse_pdf_ocr(path: Path) -> tuple[str, str]:
    try:
        # convert_from_path requires poppler-utils installed
        images = convert_from_path(str(path))
        text = ""
        for i, img in enumerate(images):
            logger.info(f"OCR processing page {i+1}/{len(images)}")
            text += pytesseract.image_to_string(img) + "\n"
        return text, "ocr_tesseract"
    except Exception as e:
        logger.error(f"OCR failed for PDF {path}: {e}")
        # If OCR fails, return whatever we had or empty, but raising might be better to signal failure
        raise


def _parse_docx(path: Path) -> tuple[str, str]:
    try:
        doc = docx.Document(path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text, "python-docx"
    except Exception as e:
        logger.error(f"DOCX parsing failed: {e}")
        raise


def _parse_image(path: Path) -> tuple[str, str]:
    try:
        image = Image.open(path)
        text = pytesseract.image_to_string(image)
        return text, "ocr_tesseract"
    except Exception as e:
        logger.error(f"Image OCR failed: {e}")
        raise



