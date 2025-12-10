"""
Advanced Markdown Parser with table extraction
Adapted from RAGFlow MarkdownParser
"""
import logging
import re
from typing import List

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedMarkdownParser:
    """
    Advanced Markdown parser with table extraction and structure preservation.
    """
    
    def __init__(self):
        pass
    
    def parse(self, file_path: str = None, binary: bytes = None, text: str = None) -> str:
        """
        Parse Markdown and return full text.
        
        Args:
            file_path: Path to Markdown file
            binary: Binary content
            text: Markdown string
            
        Returns:
            Full extracted text
        """
        # Load markdown
        if text:
            md_text = text
        elif binary:
            md_text = binary.decode('utf-8', errors='ignore')
        elif file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                md_text = f.read()
        else:
            raise ValueError("Either file_path, binary, or text must be provided")
        
        # Extract tables
        tables = self._extract_tables(md_text)
        
        # Remove tables from text
        text_without_tables = md_text
        for table_md in tables:
            text_without_tables = text_without_tables.replace(table_md, '')
        
        # Clean remaining text
        clean_text = self._clean_markdown(text_without_tables)
        
        # Format tables
        formatted_tables = []
        for table_md in tables:
            formatted = self._format_table(table_md)
            if formatted:
                formatted_tables.append(formatted)
        
        # Combine
        parts = []
        if clean_text.strip():
            parts.append(clean_text)
        parts.extend(formatted_tables)
        
        return "\n\n".join(parts)
    
    def _extract_tables(self, text: str) -> List[str]:
        """
        Extract markdown tables from text.
        
        Args:
            text: Markdown text
            
        Returns:
            List of table markdown strings
        """
        tables = []
        
        # Pattern for standard markdown tables (with |)
        # Find table blocks (consecutive lines with |)
        lines = text.split('\n')
        current_table = []
        
        for line in lines:
            if '|' in line:
                current_table.append(line)
            else:
                if len(current_table) >= 2:  # Minimum: header + separator
                    table_md = '\n'.join(current_table)
                    tables.append(table_md)
                current_table = []
        
        # Don't forget last table
        if len(current_table) >= 2:
            table_md = '\n'.join(current_table)
            tables.append(table_md)
        
        return tables
    
    def _format_table(self, table_md: str) -> str:
        """
        Format markdown table into readable text.
        
        Args:
            table_md: Markdown table string
            
        Returns:
            Formatted table text
        """
        lines = [line.strip() for line in table_md.split('\n') if line.strip()]
        
        if len(lines) < 2:
            return ""
        
        # Parse header
        header_line = lines[0]
        headers = [cell.strip() for cell in header_line.split('|')]
        headers = [h for h in headers if h]  # Remove empty
        
        # Skip separator line (usually line 1)
        data_lines = lines[2:] if len(lines) > 2 else []
        
        # Parse data rows
        formatted_rows = []
        for line in data_lines:
            cells = [cell.strip() for cell in line.split('|')]
            cells = [c for c in cells if c]  # Remove empty
            
            # Build pairs
            pairs = []
            for i, cell in enumerate(cells):
                if cell:
                    if i < len(headers) and headers[i]:
                        pairs.append(f"{headers[i]}: {cell}")
                    else:
                        pairs.append(cell)
            
            if pairs:
                formatted_rows.append("; ".join(pairs))
        
        return "\n".join(formatted_rows)
    
    def _clean_markdown(self, text: str) -> str:
        """
        Clean markdown formatting from text.
        
        Args:
            text: Markdown text
            
        Returns:
            Cleaned text
        """
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        
        # Remove headers markers
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        
        # Remove emphasis
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'__([^_]+)__', r'\1', text)      # Bold alt
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Italic alt
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove images
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
        
        # Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
        
        # Remove list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple blank lines
        text = re.sub(r' +', ' ', text)           # Multiple spaces
        
        return text.strip()
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None,
                          text: str = None,
                          chunk_token_count: int = 128,
                          delimiter: str = "\n!?。;!?") -> List[str]:
        """
        Parse Markdown with intelligent chunking.
        
        Args:
            file_path: Path to Markdown
            binary: Binary content
            text: Markdown string
            chunk_token_count: Target tokens per chunk
            delimiter: Sentence delimiters
            
        Returns:
            List of text chunks
        """
        # Get full text
        full_text = self.parse(file_path, binary, text)
        
        # Use chunking logic from txt_parser
        from .txt_parser import AdvancedTxtParser
        
        txt_parser = AdvancedTxtParser()
        return txt_parser._chunk_text(full_text, chunk_token_count, delimiter)
    
    def __call__(self, file_path: str = None, binary: bytes = None,
                 text: str = None) -> str:
        """
        Callable interface returning text.
        
        Returns:
            Extracted text
        """
        return self.parse(file_path, binary, text)
