"""
Advanced HTML Parser with table extraction and smart chunking
Adapted from RAGFlow HtmlParser
"""
import logging
import re
from io import BytesIO
from typing import List

from bs4 import BeautifulSoup, NavigableString

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedHtmlParser:
    """
    Advanced HTML parser with table extraction and text cleaning.
    """
    
    def __init__(self):
        self.soup = None
    
    def parse(self, file_path: str = None, binary: bytes = None, html: str = None) -> str:
        """
        Parse HTML and return full text.
        
        Args:
            file_path: Path to HTML file
            binary: Binary content
            html: HTML string
            
        Returns:
            Full extracted text
        """
        # Load HTML
        if html:
            self.soup = BeautifulSoup(html, 'html5lib')
        elif binary:
            self.soup = BeautifulSoup(binary, 'html5lib')
        elif file_path:
            with open(file_path, 'rb') as f:
                self.soup = BeautifulSoup(f, 'html5lib')
        else:
            raise ValueError("Either file_path, binary, or html must be provided")
        
        # Remove script and style elements
        for element in self.soup(['script', 'style', 'meta', 'link']):
            element.decompose()
        
        # Extract text
        text_parts = []
        
        # Extract tables first
        for table in self.soup.find_all('table'):
            table_text = self._extract_table(table)
            if table_text:
                text_parts.append(table_text)
            # Remove table from soup to avoid duplicating text
            table.decompose()
        
        # Extract remaining text
        body_text = self._extract_text_blocks(self.soup)
        if body_text:
            text_parts.append(body_text)
        
        return "\n\n".join(text_parts)
    
    def _extract_table(self, table) -> str:
        """
        Extract and format table content.
        
        Args:
            table: BeautifulSoup table element
            
        Returns:
            Formatted table text
        """
        rows = []
        
        # Extract all rows
        for tr in table.find_all('tr'):
            cells = []
            for cell in tr.find_all(['td', 'th']):
                cell_text = self._get_text_from_element(cell).strip()
                if cell_text:
                    cells.append(cell_text)
            
            if cells:
                rows.append(cells)
        
        if len(rows) < 2:
            return ""
        
        # Format with first row as header
        headers = rows[0]
        data_rows = rows[1:]
        
        formatted_rows = []
        for row in data_rows:
            pairs = []
            for i, value in enumerate(row):
                if value:
                    if i < len(headers) and headers[i]:
                        pairs.append(f"{headers[i]}: {value}")
                    else:
                        pairs.append(value)
            
            if pairs:
                formatted_rows.append("; ".join(pairs))
        
        return "\n".join(formatted_rows)
    
    def _extract_text_blocks(self, element) -> str:
        """
        Extract text from HTML blocks (p, div, h1-h6, li, etc).
        
        Args:
            element: BeautifulSoup element
            
        Returns:
            Extracted text
        """
        # Block-level elements
        block_elements = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                          'li', 'blockquote', 'pre', 'article', 'section']
        
        blocks = []
        
        for tag_name in block_elements:
            for elem in element.find_all(tag_name):
                text = self._get_text_from_element(elem).strip()
                if text:
                    blocks.append(text)
        
        # If no blocks found, get all text
        if not blocks:
            text = self._get_text_from_element(element)
            return self._clean_text(text)
        
        return "\n\n".join(blocks)
    
    def _get_text_from_element(self, element) -> str:
        """
        Get text from element, handling nested structures.
        
        Args:
            element: BeautifulSoup element
            
        Returns:
            Text content
        """
        # Get text and clean
        text = element.get_text(separator=' ', strip=True)
        return self._clean_text(text)
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common HTML entities that slipped through
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        
        return text.strip()
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None,
                          html: str = None,
                          chunk_token_count: int = 128,
                          delimiter: str = "\n!?。;!?") -> List[str]:
        """
        Parse HTML with intelligent chunking.
        
        Args:
            file_path: Path to HTML
            binary: Binary content
            html: HTML string
            chunk_token_count: Target tokens per chunk
            delimiter: Sentence delimiters
            
        Returns:
            List of text chunks
        """
        # Get full text
        full_text = self.parse(file_path, binary, html)
        
        # Use chunking logic from txt_parser
        from .txt_parser import AdvancedTxtParser
        
        txt_parser = AdvancedTxtParser()
        return txt_parser._chunk_text(full_text, chunk_token_count, delimiter)
    
    def __call__(self, file_path: str = None, binary: bytes = None, 
                 html: str = None) -> str:
        """
        Callable interface returning text.
        
        Returns:
            Extracted text
        """
        return self.parse(file_path, binary, html)
