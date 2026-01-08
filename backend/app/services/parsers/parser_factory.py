"""Parser factory to select appropriate parser for file type."""
import logging
from pathlib import Path
from typing import List, Optional

from app.services.parsers.base_parser import BaseParser, ParseResult
from app.services.parsers.pdf_parser import PDFParser
from app.services.parsers.docx_parser import DOCXParser
from app.services.parsers.txt_parser import TXTParser

logger = logging.getLogger(__name__)


class ParserFactory:
    """Factory for creating appropriate parser based on file type."""
    
    def __init__(self):
        """Initialize with all available parsers."""
        self.parsers: List[BaseParser] = [
            PDFParser(),
            DOCXParser(),
            TXTParser(),
        ]
    
    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        """Get appropriate parser for file."""
        for parser in self.parsers:
            if parser.can_parse(file_path):
                return parser
        return None
    
    def parse_file(self, file_path: str) -> ParseResult:
        """Parse file with appropriate parser."""
        parser = self.get_parser(file_path)
        
        if not parser:
            ext = Path(file_path).suffix
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported types: PDF, DOCX, TXT, MD"
            )
        
        return parser.parse(file_path)
    
    def is_supported(self, file_path: str) -> bool:
        """Check if file type is supported."""
        return self.get_parser(file_path) is not None
    
    @property
    def supported_extensions(self) -> set:
        """Get all supported file extensions."""
        extensions = set()
        for parser in self.parsers:
            extensions.update(parser.SUPPORTED_EXTENSIONS)
        return extensions
