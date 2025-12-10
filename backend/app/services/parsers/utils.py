"""
Utility functions for advanced parsers
Adapted from DeepDoc utils
"""
import logging
import chardet

logger = logging.getLogger(__name__)


def find_codec(binary_data: bytes) -> str:
    """
    Detect the encoding of binary data.
    
    Args:
        binary_data: Binary content to detect encoding from
        
    Returns:
        Detected encoding name (e.g., 'utf-8', 'latin-1')
    """
    try:
        result = chardet.detect(binary_data)
        encoding = result.get('encoding', 'utf-8')
        confidence = result.get('confidence', 0)
        
        if confidence < 0.7:
            logger.warning(f"Low confidence ({confidence}) in detected encoding: {encoding}")
            
        # Fallback to utf-8 if detection failed
        return encoding if encoding else 'utf-8'
    except Exception as e:
        logger.error(f"Encoding detection failed: {e}, defaulting to utf-8")
        return 'utf-8'


def get_text(file_path: str = None, binary: bytes = None) -> str:
    """
    Extract text from file path or binary data.
    
    Args:
        file_path: Path to text file
        binary: Binary content of file
        
    Returns:
        Extracted text as string
    """
    txt = ""
    if binary:
        encoding = find_codec(binary)
        txt = binary.decode(encoding, errors="ignore")
    elif file_path:
        # Try to detect encoding from file
        with open(file_path, "rb") as f:
            sample = f.read()
            encoding = find_codec(sample)
        
        with open(file_path, "r", encoding=encoding, errors="ignore") as f:
            txt = f.read()
    
    return txt


def num_tokens_from_string(text: str) -> int:
    """
    Estimate number of tokens in a string.
    Simple approximation: split by whitespace and punctuation.
    
    Args:
        text: Input text
        
    Returns:
        Approximate token count
    """
    if not text:
        return 0
    
    # Simple tokenization - split by whitespace
    # This is a rough approximation
    import re
    tokens = re.findall(r'\b\w+\b|[.,!?;:]', text)
    return len(tokens)
