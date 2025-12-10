"""
Advanced JSON Parser with smart nested chunking
Adapted from RAGFlow JsonParser
"""
import logging
import json
from io import BytesIO
from typing import List, Dict, Any, Union

from .utils import num_tokens_from_string

logger = logging.getLogger(__name__)


class AdvancedJsonParser:
    """
    Advanced JSON parser with smart chunking for nested structures.
    """
    
    def __init__(self):
        pass
    
    def parse(self, file_path: str = None, binary: bytes = None, 
              json_str: str = None, json_obj: Any = None) -> str:
        """
        Parse JSON and return formatted text.
        
        Args:
            file_path: Path to JSON file
            binary: Binary content
            json_str: JSON string
            json_obj: Already parsed JSON object
            
        Returns:
            Formatted JSON text
        """
        # Load JSON
        if json_obj is not None:
            data = json_obj
        elif json_str:
            data = json.loads(json_str)
        elif binary:
            data = json.loads(binary.decode('utf-8'))
        elif file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Check if JSONL (JSON Lines)
                first_line = f.readline()
                f.seek(0)
                
                if first_line.strip().startswith('{'):
                    # Might be JSONL
                    try:
                        json.loads(first_line)
                        # It's JSONL
                        return self._parse_jsonl(f)
                    except:
                        pass
                
                # Regular JSON
                data = json.load(f)
        else:
            raise ValueError("Must provide file_path, binary, json_str, or json_obj")
        
        # Format JSON
        return self._format_json(data)
    
    def _parse_jsonl(self, file_obj) -> str:
        """
        Parse JSON Lines format.
        
        Args:
            file_obj: File object
            
        Returns:
            Formatted text
        """
        lines = []
        for line in file_obj:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    formatted = self._format_json(obj)
                    lines.append(formatted)
                except Exception as e:
                    logger.error(f"Failed to parse JSONL line: {e}")
        
        return "\n\n".join(lines)
    
    def _format_json(self, data: Any, indent: int = 0) -> str:
        """
        Format JSON into readable text.
        
        Args:
            data: JSON data (dict, list, or primitive)
            indent: Current indentation level
            
        Returns:
            Formatted text
        """
        indent_str = "  " * indent
        
        if isinstance(data, dict):
            # Format dictionary
            lines = []
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    nested = self._format_json(value, indent + 1)
                    lines.append(f"{indent_str}{key}:")
                    lines.append(nested)
                else:
                    lines.append(f"{indent_str}{key}: {value}")
            
            return "\n".join(lines)
        
        elif isinstance(data, list):
            # Format list
            if not data:
                return f"{indent_str}[]"
            
            # Check if list of primitives
            if all(not isinstance(item, (dict, list)) for item in data):
                # Simple list
                return f"{indent_str}" + ", ".join(str(item) for item in data)
            
            # List of complex objects
            lines = []
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    lines.append(f"{indent_str}[{i}]:")
                    lines.append(self._format_json(item, indent + 1))
                else:
                    lines.append(f"{indent_str}[{i}]: {item}")
            
            return "\n".join(lines)
        
        else:
            # Primitive value
            return f"{indent_str}{data}"
    
    def parse_with_chunks(self, file_path: str = None, binary: bytes = None,
                          json_str: str = None, json_obj: Any = None,
                          chunk_token_count: int = 128) -> List[str]:
        """
        Parse JSON with intelligent chunking.
        
        For large JSON objects, intelligently splits at logical boundaries.
        
        Args:
            file_path: Path to JSON
            binary: Binary content
            json_str: JSON string
            json_obj: JSON object
            chunk_token_count: Target tokens per chunk
            
        Returns:
            List of text chunks
        """
        # Load JSON
        if json_obj is not None:
            data = json_obj
        elif json_str:
            data = json.loads(json_str)
        elif binary:
            data = json.loads(binary.decode('utf-8'))
        elif file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            raise ValueError("Must provide file_path, binary, json_str, or json_obj")
        
        # Chunk based on structure
        return self._chunk_json(data, chunk_token_count)
    
    def _chunk_json(self, data: Any, chunk_token_count: int) -> List[str]:
        """
        Intelligently chunk JSON data.
        
        Args:
            data: JSON data
            chunk_token_count: Target tokens per chunk
            
        Returns:
            List of chunks
        """
        chunks = []
        
        if isinstance(data, dict):
            # Chunk dictionary by keys
            current_chunk = {}
            current_tokens = 0
            
            for key, value in data.items():
                # Format this key-value pair
                pair_text = self._format_json({key: value})
                pair_tokens = num_tokens_from_string(pair_text)
                
                # Check if adding this would exceed limit
                if current_tokens + pair_tokens > chunk_token_count and current_chunk:
                    # Save current chunk
                    chunks.append(self._format_json(current_chunk))
                    current_chunk = {}
                    current_tokens = 0
                
                # Add to current chunk
                current_chunk[key] = value
                current_tokens += pair_tokens
            
            # Don't forget last chunk
            if current_chunk:
                chunks.append(self._format_json(current_chunk))
        
        elif isinstance(data, list):
            # Chunk list by items
            current_chunk = []
            current_tokens = 0
            
            for item in data:
                # Format this item
                item_text = self._format_json(item)
                item_tokens = num_tokens_from_string(item_text)
                
                # Check if adding this would exceed limit
                if current_tokens + item_tokens > chunk_token_count and current_chunk:
                    # Save current chunk
                    chunks.append(self._format_json(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Add to current chunk
                current_chunk.append(item)
                current_tokens += item_tokens
            
            # Don't forget last chunk
            if current_chunk:
                chunks.append(self._format_json(current_chunk))
        
        else:
            # Primitive - single chunk
            chunks.append(self._format_json(data))
        
        return chunks
    
    def __call__(self, file_path: str = None, binary: bytes = None,
                 json_str: str = None, json_obj: Any = None) -> str:
        """
        Callable interface returning formatted text.
        
        Returns:
            Formatted JSON text
        """
        return self.parse(file_path, binary, json_str, json_obj)
