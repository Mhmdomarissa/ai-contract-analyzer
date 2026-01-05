"""
Enhanced Conflict Detection Helper Functions.

This module provides clause function classification and compatibility checking
for improved conflict detection accuracy.
"""

import re
from enum import Enum
from typing import Optional


class ClauseFunction(str, Enum):
    """Contract-agnostic clause function classification."""
    PAYMENT = "PAYMENT"
    TERMINATION = "TERMINATION"
    GOVERNING_LAW_JURISDICTION = "GOVERNING_LAW_JURISDICTION"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    INDEMNITY_LIABILITY = "INDEMNITY_LIABILITY"
    FORCE_MAJEURE = "FORCE_MAJEURE"
    NOTICES = "NOTICES"
    AMENDMENTS = "AMENDMENTS"
    DEFINITIONS = "DEFINITIONS"
    SCOPE_SERVICES = "SCOPE_SERVICES"
    EXECUTION_SIGNATURES = "EXECUTION_SIGNATURES"
    MISC_ADMIN = "MISC_ADMIN"


# Compatibility matrix: which function pairs can be compared
COMPATIBLE_PAIRS = {
    # Same function always compatible
    (ClauseFunction.PAYMENT, ClauseFunction.PAYMENT),
    (ClauseFunction.TERMINATION, ClauseFunction.TERMINATION),
    (ClauseFunction.GOVERNING_LAW_JURISDICTION, ClauseFunction.GOVERNING_LAW_JURISDICTION),
    (ClauseFunction.CONFIDENTIALITY, ClauseFunction.CONFIDENTIALITY),
    (ClauseFunction.INDEMNITY_LIABILITY, ClauseFunction.INDEMNITY_LIABILITY),
    (ClauseFunction.FORCE_MAJEURE, ClauseFunction.FORCE_MAJEURE),
    (ClauseFunction.NOTICES, ClauseFunction.NOTICES),
    (ClauseFunction.AMENDMENTS, ClauseFunction.AMENDMENTS),
    (ClauseFunction.DEFINITIONS, ClauseFunction.DEFINITIONS),
    (ClauseFunction.SCOPE_SERVICES, ClauseFunction.SCOPE_SERVICES),
    (ClauseFunction.EXECUTION_SIGNATURES, ClauseFunction.EXECUTION_SIGNATURES),
    (ClauseFunction.MISC_ADMIN, ClauseFunction.MISC_ADMIN),
    # Cross-function allowed pairs
    (ClauseFunction.INDEMNITY_LIABILITY, ClauseFunction.CONFIDENTIALITY),
    (ClauseFunction.CONFIDENTIALITY, ClauseFunction.INDEMNITY_LIABILITY),
}


def classify_clause_function(clause_text: str, heading: Optional[str]) -> str:
    """
    Classify clause function using deterministic regex/keyword rules.
    
    Args:
        clause_text: Full text of the clause
        heading: Optional heading/title of the clause
    
    Returns:
        ClauseFunction enum value as string
    """
    text_lower = clause_text.lower()
    heading_lower = heading.lower() if heading else ""
    
    # EXECUTION_SIGNATURES - high priority
    if ("in witness whereof" in text_lower or 
        "signature:" in text_lower or
        "signed on" in text_lower or
        ("executed" in heading_lower and "signature" in heading_lower)):
        return ClauseFunction.EXECUTION_SIGNATURES
    
    # AMENDMENTS
    if ("amendment" in heading_lower or 
        "variation" in heading_lower or
        ("amendment" in text_lower and "variation" in text_lower) or
        "any variation or amendment" in text_lower or
        "modify this agreement" in text_lower):
        return ClauseFunction.AMENDMENTS
    
    # NOTICES
    if ("notice" in heading_lower or
        "any notice" in text_lower or
        ("serve" in text_lower and "notice" in text_lower) or
        "notification" in heading_lower):
        return ClauseFunction.NOTICES
    
    # DEFINITIONS
    if ("definition" in heading_lower or
        "interpretation" in heading_lower or
        ("means" in text_lower and "shall mean" in text_lower)):
        return ClauseFunction.DEFINITIONS
    
    # GOVERNING_LAW_JURISDICTION
    if ("governing law" in text_lower or
        "governing law" in heading_lower or
        "jurisdiction" in text_lower or
        "jurisdiction" in heading_lower or
        ("courts" in text_lower and ("subject to" in text_lower or "exclusive" in text_lower)) or
        "venue" in text_lower or
        "arbitration" in text_lower or
        "dispute resolution" in heading_lower):
        return ClauseFunction.GOVERNING_LAW_JURISDICTION
    
    # PAYMENT
    if ("payment" in heading_lower or
        "fee" in heading_lower or
        "invoice" in text_lower or
        "payable" in text_lower or
        "compensation" in heading_lower or
        re.search(r'\d+%', text_lower) or  # percentages often payment-related
        re.search(r'net \d+', text_lower)):  # "Net 30", "Net 60"
        return ClauseFunction.PAYMENT
    
    # TERMINATION
    if ("termination" in heading_lower or
        "terminate" in text_lower or
        "cancellation" in text_lower or
        "expiry" in heading_lower):
        return ClauseFunction.TERMINATION
    
    # CONFIDENTIALITY
    if ("confidential" in text_lower or
        "nda" in text_lower or
        "non-disclosure" in text_lower or
        "proprietary information" in text_lower):
        return ClauseFunction.CONFIDENTIALITY
    
    # INDEMNITY_LIABILITY
    if ("indemnif" in text_lower or
        "liability" in text_lower or
        "liable" in text_lower or
        "damages" in heading_lower or
        "limitation of liability" in text_lower):
        return ClauseFunction.INDEMNITY_LIABILITY
    
    # FORCE_MAJEURE
    if ("force majeure" in text_lower or
        "act of god" in text_lower):
        return ClauseFunction.FORCE_MAJEURE
    
    # SCOPE_SERVICES
    if ("scope" in heading_lower or
        "services" in heading_lower or
        "deliverable" in text_lower or
        ("work" in heading_lower and "scope" in heading_lower)):
        return ClauseFunction.SCOPE_SERVICES
    
    # Default
    return ClauseFunction.MISC_ADMIN


def is_pair_allowed(func1: str, func2: str, is_override_or_xref: bool = False) -> bool:
    """
    Check if two clause functions can be compared based on compatibility matrix.
    
    Args:
        func1, func2: Clause function classifications
        is_override_or_xref: If True, bypass compatibility gate (explicit override/cross-reference)
    
    Returns:
        True if comparison allowed, False otherwise
    """
    # Override/cross-reference pairs always allowed
    if is_override_or_xref:
        return True
    
    # Check compatibility matrix
    pair = (func1, func2)
    reverse_pair = (func2, func1)
    
    return pair in COMPATIBLE_PAIRS or reverse_pair in COMPATIBLE_PAIRS
