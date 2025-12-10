"""
Advanced TXT Parser with smart chunking
Adapted from RAGFlow TxtParser
"""
import logging
import re
from pathlib import Path
from typing import List, Tuple

from .utils import get_text, num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedTxtParser:
    """
    Advanced text parser with intelligent chunking based on delimiters and token count.
    """
    
    def __init__(self, chunk_token_num: int = 128, delimiter: str = "\n!?;。；！？"):
        """
        Initialize parser with chunking parameters.
        
        Args:
            chunk_token_num: Target number of tokens per chunk
            delimiter: String containing delimiter characters for chunking
        """
        self.chunk_token_num = chunk_token_num
        self.delimiter = delimiter
    
    def parse(self, file_path: str = None, binary: bytes = None) -> str:
        """
        Parse text file and return full text.
        
        Args:
            file_path: Path to text file
            binary: Binary content of file
            
        Returns:
            Extracted text as string
        """
        return get_text(file_path, binary)
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None) -> List[Tuple[str, str]]:
        """
        Parse text file and return smart chunks.
        
        Args:
            file_path: Path to text file
            binary: Binary content of file
            
        Returns:
            List of tuples (chunk_text, metadata)
        """
        txt = get_text(file_path, binary)
        return self._chunk_text(txt)
    
    def _chunk_text(self, txt: str) -> List[Tuple[str, str]]:
        """
        Split text into intelligent chunks based on delimiters and token count.
        
        Args:
            txt: Input text to chunk
            
        Returns:
            List of tuples (chunk_text, metadata)
        """
        if not isinstance(txt, str):
            raise TypeError("txt type should be str!")
        
        chunks = [""]
        token_nums = [0]
        
        # Decode delimiter string (handle unicode escapes)
        try:
            delimiter = self.delimiter.encode('utf-8').decode('unicode_escape').encode('latin1').decode('utf-8')
        except Exception as e:
            logger.warning(f"Delimiter decode failed: {e}, using raw delimiter")
            delimiter = self.delimiter
        
        def add_chunk(text_segment):
            """Add text to current chunk or create new chunk if needed."""
            nonlocal chunks, token_nums
            tnum = num_tokens_from_string(text_segment)
            
            if token_nums[-1] > self.chunk_token_num:
                # Start new chunk
                chunks.append(text_segment)
                token_nums.append(tnum)
            else:
                # Add to current chunk
                chunks[-1] += text_segment
                token_nums[-1] += tnum
        
        # Extract delimiters (handle backtick-escaped delimiters)
        dels = []
        s = 0
        for m in re.finditer(r"`([^`]+)`", delimiter, re.I):
            f, t = m.span()
            dels.append(m.group(1))
            dels.extend(list(delimiter[s:f]))
            s = t
        
        if s < len(delimiter):
            dels.extend(list(delimiter[s:]))
        
        # Escape delimiters for regex and filter empty
        dels = [re.escape(d) for d in dels if d]
        dels = [d for d in dels if d]
        
        if not dels:
            # No delimiters, return whole text as one chunk
            return [(txt, "")]
        
        dels_pattern = "|".join(dels)
        
        # Split text by delimiters
        sections = re.split(r"(%s)" % dels_pattern, txt)
        
        for sec in sections:
            # Skip if section is just a delimiter
            if re.match(f"^{dels_pattern}$", sec):
                continue
            add_chunk(sec)
        
        # Return chunks with empty metadata
        return [(c, "") for c in chunks if c]
    
    def __call__(self, file_path: str, binary: bytes = None) -> List[Tuple[str, str]]:
        """
        Callable interface for parsing.
        
        Args:
            file_path: Path to file or filename
            binary: Binary content
            
        Returns:
            List of chunks with metadata
        """
        return self.parse_with_chunks(file_path, binary)
