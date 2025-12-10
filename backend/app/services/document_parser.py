import logging
import mimetypes
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


def parse_document(file_path: str) -> str:
    """
    Extract text from a file (supports all major formats).
    
    Supports: PDF, DOCX, XLSX, PPTX, HTML, Markdown, JSON, TXT, Images
    
    Args:
        file_path: Path to the file to parse.
        
    Returns:
        Extracted text as a string.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    mime_type, _ = mimetypes.guess_type(path)
    logger.info(f"Parsing file: {file_path}, Mime: {mime_type}")

    text = ""
    method = "unknown"

    try:
        suffix = path.suffix.lower()
        
        # Try advanced parsers first if enabled
        if USE_ADVANCED_PARSERS:
            try:
                if suffix == ".pdf":
                    parser = AdvancedPdfParser(use_ocr=True, layout_recognition=True)
                    text = parser.parse(file_path=str(path))
                    method = "advanced_pdf"
                    
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
                    logger.warning(f"Unsupported file type: {suffix}. Returning empty string.")
                    return ""
                
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
                logger.warning(f"Unsupported file type: {suffix}. Returning empty string.")
                return ""
            
        logger.info(f"Extracted {len(text)} chars using {method} from {file_path}")
        return text

    except Exception as e:
        logger.error(f"Error parsing document {file_path}: {e}")
        raise


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



