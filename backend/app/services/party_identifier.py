"""Party identification service using LLM with regex fallback."""
import re
import json
import logging
from typing import List
import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PartyIdentifier:
    """Identify contract parties using LLM with regex fallback."""
    
    def __init__(self):
        """Initialize party identifier."""
        self.ollama_url = f"{settings.OLLAMA_URL}/api/chat"
        self.model_name = settings.OLLAMA_MODEL
        self.timeout = 60  # 60 second timeout for LLM calls
    
    def identify_parties(self, contract_text: str) -> List[str]:
        """
        Identify all parties in the contract.
        
        Tries LLM first, falls back to regex if LLM fails.
        
        Args:
            contract_text: Full contract text
            
        Returns:
            List of party names
        """
        logger.info("Starting party identification")
        
        # Try LLM first
        try:
            parties = self._identify_with_llm(contract_text)
            if parties and len(parties) > 0:
                logger.info(f"LLM identified {len(parties)} parties: {parties}")
                return parties
        except Exception as e:
            logger.warning(f"LLM party identification failed: {str(e)}")
        
        # Fallback to regex
        logger.info("Falling back to regex party identification")
        parties = self._identify_with_regex(contract_text)
        logger.info(f"Regex identified {len(parties)} parties: {parties}")
        
        return parties
    
    def _identify_with_llm(self, contract_text: str) -> List[str]:
        """
        Identify parties using LLM.
        
        Args:
            contract_text: Full contract text
            
        Returns:
            List of party names
            
        Raises:
            Exception: If LLM call fails
        """
        # Limit text to first 4000 words for context
        snippet = " ".join(contract_text.split()[:4000])
        
        prompt = f"""
Analyze the legal contract text below and identify the official names of ALL parties involved.

1. Contextual Understanding: Look for entities defined as parties (e.g., after 'BETWEEN', 'AND', 'among').
2. Dynamic Count: There may be 2, 3, or more parties. Identify ALL of them.
3. STRICTLY EXCLUDE the following:
   - Addresses (Streets, Cities, P.O. Boxes, Towers, Countries).
   - Trade License numbers.
   - Zip/Postal Codes.
   - Parenthetical definitions (e.g., "hereinafter referred to as...", "The Client", "The Agency").
4. Output: Return ONLY a valid JSON list of the unique party names found. 
   Example format: ["Party Name 1", "Party Name 2", "Party Name 3"]

Text:
{snippet}
"""
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        
        logger.debug(f"Sending party identification request to {self.ollama_url}")
        
        response = requests.post(
            self.ollama_url,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        # Parse response
        response_data = response.json()
        
        # Handle different Ollama response formats
        llm_text = ""
        if "message" in response_data:
            llm_text = response_data["message"].get("content", "")
        elif "choices" in response_data:
            llm_text = response_data["choices"][0].get("message", {}).get("content", "")
        
        if not llm_text:
            raise ValueError("Empty response from LLM")
        
        logger.debug(f"LLM response: {llm_text[:200]}...")
        
        # Try to parse JSON from response
        # LLM might wrap JSON in markdown code blocks
        llm_text = llm_text.strip()
        if llm_text.startswith("```json"):
            llm_text = llm_text[7:]
        if llm_text.startswith("```"):
            llm_text = llm_text[3:]
        if llm_text.endswith("```"):
            llm_text = llm_text[:-3]
        llm_text = llm_text.strip()
        
        # Parse JSON
        parties = json.loads(llm_text)
        
        if not isinstance(parties, list):
            raise ValueError(f"LLM returned non-list: {type(parties)}")
        
        # Filter out empty strings
        parties = [p.strip() for p in parties if p and p.strip()]
        
        if len(parties) == 0:
            raise ValueError("LLM returned empty party list")
        
        return parties
    
    def _identify_with_regex(self, contract_text: str) -> List[str]:
        """
        Identify parties using regex patterns (fallback).
        
        Args:
            contract_text: Full contract text
            
        Returns:
            List of party names (defaults to UNKNOWN if not found)
        """
        # Remove newlines for easier pattern matching
        single_line_text = contract_text.replace("\n", " ")
        
        # Pattern 1: BETWEEN ... AND ...
        pattern1 = r'(?i)(?:between|BETWEEN)\s+(.+?)\s+AND\s+(.+?)(?:hereinafter|,|\()'
        matches1 = re.findall(pattern1, single_line_text)
        
        if matches1:
            p1, p2 = matches1[0]
            parties = [p1.strip(), p2.strip()]
            logger.debug(f"Regex pattern 1 found: {parties}")
            return parties
        
        # Pattern 2: This Agreement is made between ... and ...
        pattern2 = r'(?i)(?:agreement|contract)\s+(?:is\s+)?(?:made\s+)?between\s+(.+?)\s+and\s+(.+?)(?:\.|,|\()'
        matches2 = re.findall(pattern2, single_line_text)
        
        if matches2:
            p1, p2 = matches2[0]
            parties = [p1.strip(), p2.strip()]
            logger.debug(f"Regex pattern 2 found: {parties}")
            return parties
        
        # Pattern 3: Parties: ... and ...
        pattern3 = r'(?i)parties:\s*(.+?)\s+and\s+(.+?)(?:\.|,|\n)'
        matches3 = re.findall(pattern3, single_line_text)
        
        if matches3:
            p1, p2 = matches3[0]
            parties = [p1.strip(), p2.strip()]
            logger.debug(f"Regex pattern 3 found: {parties}")
            return parties
        
        # Default: Return placeholder
        logger.warning("Could not identify parties with regex, returning placeholders")
        return ["UNKNOWN PARTY 1", "UNKNOWN PARTY 2"]
    
    def validate_parties(self, parties: List[str]) -> List[str]:
        """
        Validate and clean party names.
        
        Removes obviously invalid entries like addresses, license numbers, etc.
        
        Args:
            parties: Raw party list
            
        Returns:
            Cleaned party list
        """
        cleaned_parties = []
        
        # Patterns to exclude
        exclude_patterns = [
            r'P\.?O\.?\s+Box',  # P.O. Box
            r'\d{5,}',  # Long numbers (likely license/postal codes)
            r'(?i)tower|building|floor|street|avenue|road',  # Addresses
            r'(?i)hereinafter|referred\s+to\s+as',  # Legal boilerplate
        ]
        
        for party in parties:
            # Skip empty
            if not party or not party.strip():
                continue
            
            # Check against exclude patterns
            exclude = False
            for pattern in exclude_patterns:
                if re.search(pattern, party):
                    logger.debug(f"Excluding party '{party}' (matched pattern: {pattern})")
                    exclude = True
                    break
            
            if not exclude:
                cleaned_parties.append(party.strip())
        
        return cleaned_parties if cleaned_parties else parties
