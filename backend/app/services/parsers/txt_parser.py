"""TXT parser for plain text files."""
import logging
from pathlib import Path

from app.services.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class TXTParser(BaseParser):
    """Parser for plain text files."""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.text', '.md', '.markdown'}
    
    def can_parse(self, file_path: str) -> bool:
        """Check if file is a text file."""
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def parse(self, file_path: str) -> ParseResult:
        """Parse text file."""
        self._log_parse_start(file_path)
        
        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
            text = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                    logger.info(f"Successfully read {file_path} with {encoding} encoding")
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                raise ValueError(f"Could not decode {file_path} with any supported encoding")
            
            if not text.strip():
                raise ValueError("File is empty or contains no readable text.")
            
            # Estimate page count (rough: ~500 words per page)
            word_count = len(text.split())
            page_count = max(1, word_count // 500)
            
            result = ParseResult(
                text=text,
                page_count=page_count,
                word_count=word_count,
                metadata={"parser": "txt", "file_path": file_path}
            )
            
            self._log_parse_complete(file_path, result)
            return result
            
        except Exception as e:
            logger.error(f"Error parsing text file {file_path}: {str(e)}")
            raise
