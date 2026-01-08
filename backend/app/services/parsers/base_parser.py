"""Base parser interface."""
from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ParseResult:
    """Result from parsing a document."""
    
    def __init__(
        self,
        text: str,
        page_count: int = 0,
        word_count: int = 0,
        metadata: Dict[str, Any] = None
    ):
        self.text = text
        self.page_count = page_count
        self.word_count = word_count or len(text.split())
        self.metadata = metadata or {}


class BaseParser(ABC):
    """Base class for document parsers."""
    
    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Check if this parser can handle the file."""
        pass
    
    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        """Parse the file and extract text."""
        pass
    
    def _log_parse_start(self, file_path: str):
        """Log parsing start."""
        logger.info(f"Starting parse with {self.__class__.__name__}: {file_path}")
    
    def _log_parse_complete(self, file_path: str, result: ParseResult):
        """Log parsing completion."""
        logger.info(
            f"Completed parse of {file_path}: "
            f"{result.word_count} words, {result.page_count} pages"
        )
