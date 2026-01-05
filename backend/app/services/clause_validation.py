"""
Clause Extraction Validation Module

Validates extraction quality to detect missing clauses, gaps in numbering,
and other extraction issues.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ClauseExtractionValidator:
    """Validates clause extraction quality and warns about potential issues."""
    
    # Critical keywords that should be found if they exist in document
    CRITICAL_KEYWORDS = [
        ('termination', 'terminate'),
        ('liability', 'liable', 'indemnif'),
        ('payment', 'fee', 'charge'),
        ('confidential', 'proprietary'),
        ('dispute', 'arbitration', 'jurisdiction'),
    ]
    
    @staticmethod
    def validate_extraction(clauses: List[Dict[str, Any]], original_text: str) -> Dict[str, Any]:
        """
        Validate extraction quality and return validation report.
        
        Args:
            clauses: List of extracted clause dicts
            original_text: Original document text
            
        Returns:
            Dict with validation results and warnings
        """
        doc_length = len(original_text)
        clause_count = len(clauses)
        warnings = []
        
        # Check 1: Minimum clause density
        expected_min_clauses = max(10, doc_length // 2000)
        if clause_count < expected_min_clauses:
            warnings.append({
                'type': 'low_clause_density',
                'severity': 'WARNING',
                'message': (
                    f"Only {clause_count} clauses extracted from {doc_length:,} chars. "
                    f"Expected at least {expected_min_clauses}. Document may have complex structure."
                )
            })
            logger.warning(f"⚠️  {warnings[-1]['message']}")
        
        # Check 2: Gaps in numbered sequences
        numbered_analysis = ClauseExtractionValidator._analyze_numbering(clauses)
        for section, analysis in numbered_analysis.items():
            if analysis['missing_percentage'] > 30:
                warnings.append({
                    'type': 'numbering_gaps',
                    'severity': 'WARNING',
                    'section': section,
                    'message': (
                        f"Section {section} has gaps in numbering. "
                        f"Has {analysis['actual_count']} clauses but max is {section}.{analysis['max_subsection']}. "
                        f"Potentially missing: {', '.join(analysis['missing_sample'])}"
                    )
                })
                logger.warning(f"⚠️  {warnings[-1]['message']}")
        
        # Check 3: Missing critical keywords
        keyword_analysis = ClauseExtractionValidator._analyze_keywords(clauses, original_text)
        for keyword_group, result in keyword_analysis.items():
            if result['in_document'] and not result['in_extraction']:
                warnings.append({
                    'type': 'missing_keywords',
                    'severity': 'WARNING',
                    'keyword': keyword_group,
                    'message': (
                        f"Document contains '{keyword_group}' clauses "
                        f"but they were not extracted. Check for formatting issues."
                    )
                })
                logger.warning(f"⚠️  {warnings[-1]['message']}")
        
        # Success message
        if not warnings:
            logger.info(
                f"✅ Extraction validation PASSED: {clause_count} clauses, "
                f"{len(numbered_analysis)} numbered sections, "
                f"{doc_length:,} chars processed"
            )
        else:
            logger.warning(
                f"⚠️  Extraction validation found {len(warnings)} warnings for "
                f"{clause_count} clauses from {doc_length:,} chars"
            )
        
        return {
            'passed': len(warnings) == 0,
            'clause_count': clause_count,
            'document_length': doc_length,
            'numbered_sections': len(numbered_analysis),
            'warnings': warnings
        }
    
    @staticmethod
    def _analyze_numbering(clauses: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Analyze numbered clause sequences for gaps."""
        numbered_clauses = {}
        
        for clause in clauses:
            num = clause.get('clause_number', '')
            # Parse X.Y format
            if '.' in num and num[0].isdigit():
                parts = num.split('.')
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    section = int(parts[0])
                    subsection = int(parts[1])
                    if section not in numbered_clauses:
                        numbered_clauses[section] = []
                    numbered_clauses[section].append(subsection)
        
        # Analyze each section
        analysis = {}
        for section, subsections in numbered_clauses.items():
            if len(subsections) > 1:
                subsections_sorted = sorted(set(subsections))  # Remove duplicates
                max_sub = subsections_sorted[-1]
                expected_count = max_sub
                actual_count = len(subsections_sorted)
                missing = set(range(1, max_sub + 1)) - set(subsections_sorted)
                missing_percentage = (len(missing) / expected_count * 100) if expected_count > 0 else 0
                
                analysis[section] = {
                    'max_subsection': max_sub,
                    'expected_count': expected_count,
                    'actual_count': actual_count,
                    'missing_count': len(missing),
                    'missing_percentage': missing_percentage,
                    'missing_sample': [f'{section}.{m}' for m in sorted(missing)[:5]]
                }
        
        return analysis
    
    @staticmethod
    def _analyze_keywords(clauses: List[Dict[str, Any]], original_text: str) -> Dict[str, Dict[str, bool]]:
        """Analyze presence of critical keywords in document vs extracted clauses."""
        all_clause_text = ' '.join(c.get('text', '') for c in clauses).lower()
        doc_text_lower = original_text.lower()
        
        results = {}
        for keyword_group in ClauseExtractionValidator.CRITICAL_KEYWORDS:
            primary_keyword = keyword_group[0]
            doc_has = any(kw in doc_text_lower for kw in keyword_group)
            extracted_has = any(kw in all_clause_text for kw in keyword_group)
            
            results[primary_keyword] = {
                'in_document': doc_has,
                'in_extraction': extracted_has
            }
        
        return results
