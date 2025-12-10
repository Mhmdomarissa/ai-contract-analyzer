"""
LLM-based clause validation service.

This module validates regex-extracted clauses using LLM to:
1. Check if extraction boundaries are correct
2. Identify false positives (e.g., table of contents entries)
3. Suggest improvements or corrections
4. Score clause quality
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ClauseValidationResult:
    """Result of validating a single clause."""
    is_valid: bool
    confidence_score: float  # 0.0 to 1.0
    issues: List[str]
    suggestions: List[str]
    is_toc_entry: bool
    boundary_correct: bool
    quality_score: float  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchValidationResult:
    """Result of validating multiple clauses."""
    validated_clauses: List[Dict[str, Any]]
    removed_clauses: List[Dict[str, Any]]
    issues_summary: Dict[str, int]
    overall_quality: float


class ClauseValidator:
    """Validates regex-extracted clauses using LLM."""
    
    def __init__(self, llm_service):
        """
        Initialize validator with LLM service.
        
        Args:
            llm_service: Instance of LLMService for making LLM calls
        """
        self.llm_service = llm_service
        self.validation_cache = {}  # Cache validation results
    
    async def validate_clauses(
        self,
        clauses: List[Dict[str, Any]],
        full_text: str,
        batch_size: int = 10
    ) -> BatchValidationResult:
        """
        Validate all extracted clauses in batches.
        
        Args:
            clauses: List of clause dicts from regex extraction
            full_text: Original contract text
            batch_size: Number of clauses to validate per LLM call
            
        Returns:
            BatchValidationResult with validated and removed clauses
        """
        if not clauses:
            return BatchValidationResult(
                validated_clauses=[],
                removed_clauses=[],
                issues_summary={},
                overall_quality=0.0
            )
        
        validated = []
        removed = []
        issues_count = {}
        
        # Process in batches for efficiency
        for i in range(0, len(clauses), batch_size):
            batch = clauses[i:i + batch_size]
            batch_results = await self._validate_batch(batch, full_text)
            
            for clause, result in zip(batch, batch_results):
                if result.is_valid and not result.is_toc_entry:
                    # Add validation metadata to clause
                    clause['validation'] = result.to_dict()
                    validated.append(clause)
                else:
                    clause['validation'] = result.to_dict()
                    removed.append(clause)
                
                # Track issues
                for issue in result.issues:
                    issues_count[issue] = issues_count.get(issue, 0) + 1
        
        # Calculate overall quality
        if validated:
            overall_quality = sum(
                c.get('validation', {}).get('quality_score', 0.0) 
                for c in validated
            ) / len(validated)
        else:
            overall_quality = 0.0
        
        logger.info(
            f"Validated {len(clauses)} clauses: "
            f"{len(validated)} valid, {len(removed)} removed"
        )
        
        return BatchValidationResult(
            validated_clauses=validated,
            removed_clauses=removed,
            issues_summary=issues_count,
            overall_quality=overall_quality
        )
    
    async def _validate_batch(
        self,
        batch: List[Dict[str, Any]],
        full_text: str
    ) -> List[ClauseValidationResult]:
        """
        Validate a batch of clauses with a single LLM call.
        
        Args:
            batch: List of clause dicts
            full_text: Original contract text
            
        Returns:
            List of ClauseValidationResult for each clause
        """
        prompt = self._build_validation_prompt(batch, full_text)
        
        try:
            response = await self.llm_service._call_llm(prompt)
            parsed = self._parse_validation_response(response, len(batch))
            return parsed
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            # Return default "valid" results on error
            return [
                ClauseValidationResult(
                    is_valid=True,
                    confidence_score=0.5,
                    issues=[],
                    suggestions=[],
                    is_toc_entry=False,
                    boundary_correct=True,
                    quality_score=0.5
                )
                for _ in batch
            ]
    
    def _build_validation_prompt(
        self,
        batch: List[Dict[str, Any]],
        full_text: str
    ) -> str:
        """Build LLM prompt for clause validation."""
        
        # Prepare clause info for LLM
        clauses_info = []
        for idx, clause in enumerate(batch):
            clause_num = clause.get('clause_number', f'CLAUSE_{idx}')
            text = clause.get('text', '')[:500]  # Limit text length
            start = clause.get('start_char', 0)
            end = clause.get('end_char', 0)
            
            # Get surrounding context (50 chars before/after)
            context_before = full_text[max(0, start-50):start] if start > 0 else ""
            context_after = full_text[end:min(len(full_text), end+50)] if end < len(full_text) else ""
            
            clauses_info.append({
                'index': idx,
                'clause_number': clause_num,
                'text_preview': text,
                'context_before': context_before,
                'context_after': context_after,
                'category': clause.get('category', 'Unknown')
            })
        
        return f"""You are a legal document analysis expert. Validate the following extracted contract clauses.

For each clause, check:
1. **Boundary Correctness**: Does the text start and end at natural clause boundaries? (not mid-sentence)
2. **TOC Detection**: Is this a Table of Contents entry rather than actual clause text?
3. **Quality**: Is this a complete, meaningful clause or fragment?

CLAUSES TO VALIDATE:
{json.dumps(clauses_info, indent=2, ensure_ascii=False)}

REQUIRED OUTPUT FORMAT - Return JSON array with EXACTLY {len(batch)} objects:
[
  {{
    "index": 0,
    "is_valid": true,
    "confidence_score": 0.95,
    "issues": ["Minor boundary issue at start"],
    "suggestions": ["Consider including previous sentence"],
    "is_toc_entry": false,
    "boundary_correct": true,
    "quality_score": 0.9
  }},
  ...
]

RULES:
- Return EXACTLY {len(batch)} validation objects, one per input clause
- index must match the clause index (0 to {len(batch)-1})
- is_valid: false if major issues, true if acceptable
- confidence_score: 0.0 to 1.0 (how sure you are of validity assessment)
- issues: array of detected problems (empty if none)
- suggestions: array of improvement recommendations (empty if none)
- is_toc_entry: true if this looks like table of contents/index
- boundary_correct: true if start/end positions are at natural boundaries
- quality_score: 0.0 to 1.0 overall quality rating

Common TOC indicators:
- Contains "Page X" or "....... X"
- Lists multiple clause numbers without content
- Very short text (< 20 chars) with only numbering

Your JSON response:"""
    
    def _parse_validation_response(
        self,
        response: str,
        expected_count: int
    ) -> List[ClauseValidationResult]:
        """Parse LLM validation response."""
        
        try:
            # Clean response
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            parsed = json.loads(cleaned.strip())
            
            # Handle both array and object with array
            if isinstance(parsed, dict) and 'validations' in parsed:
                parsed = parsed['validations']
            
            if not isinstance(parsed, list):
                raise ValueError("Response is not an array")
            
            results = []
            for item in parsed[:expected_count]:
                results.append(ClauseValidationResult(
                    is_valid=item.get('is_valid', True),
                    confidence_score=float(item.get('confidence_score', 0.5)),
                    issues=item.get('issues', []),
                    suggestions=item.get('suggestions', []),
                    is_toc_entry=item.get('is_toc_entry', False),
                    boundary_correct=item.get('boundary_correct', True),
                    quality_score=float(item.get('quality_score', 0.5))
                ))
            
            # Fill missing results with defaults
            while len(results) < expected_count:
                results.append(ClauseValidationResult(
                    is_valid=True,
                    confidence_score=0.5,
                    issues=[],
                    suggestions=[],
                    is_toc_entry=False,
                    boundary_correct=True,
                    quality_score=0.5
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse validation response: {e}")
            # Return default valid results
            return [
                ClauseValidationResult(
                    is_valid=True,
                    confidence_score=0.5,
                    issues=[],
                    suggestions=[],
                    is_toc_entry=False,
                    boundary_correct=True,
                    quality_score=0.5
                )
                for _ in range(expected_count)
            ]
