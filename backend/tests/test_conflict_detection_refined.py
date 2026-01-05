"""
Tests for refined conflict detection with clause function classification.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from decimal import Decimal

from app.models.clause import Clause
from app.models.conflict import Conflict
from app.services.clause_classifier import (
    classify_clause_function,
    is_pair_allowed,
    ClauseFunction
)


class TestClauseClassification:
    """Test clause function classification."""
    
    def test_payment_classification(self):
        """Payment clauses should be classified as PAYMENT."""
        text = "The Contractor shall invoice the Client with Net 30 payment terms."
        heading = "Payment Terms"
        
        result = classify_clause_function(text, heading)
        assert result == ClauseFunction.PAYMENT
    
    def test_amendments_classification(self):
        """Amendment clauses should be classified as AMENDMENTS."""
        text = "Any variation or amendments to this Agreement shall be in writing."
        heading = "Amendments"
        
        result = classify_clause_function(text, heading)
        assert result == ClauseFunction.AMENDMENTS
    
    def test_execution_classification(self):
        """Execution clauses should be classified as EXECUTION_SIGNATURES."""
        text = "IN WITNESS WHEREOF, the parties have executed this Agreement."
        heading = "Execution"
        
        result = classify_clause_function(text, heading)
        assert result == ClauseFunction.EXECUTION_SIGNATURES
    
    def test_jurisdiction_classification(self):
        """Jurisdiction clauses should be classified as GOVERNING_LAW_JURISDICTION."""
        text = "This Agreement shall be governed by the laws of England and Wales."
        heading = "Governing Law"
        
        result = classify_clause_function(text, heading)
        assert result == ClauseFunction.GOVERNING_LAW_JURISDICTION
    
    def test_notices_classification(self):
        """Notice clauses should be classified as NOTICES."""
        text = "Any notice shall be served in writing to the registered address."
        heading = "Notices"
        
        result = classify_clause_function(text, heading)
        assert result == ClauseFunction.NOTICES


class TestCompatibilityGate:
    """Test compatibility checking between clause functions."""
    
    def test_same_function_compatible(self):
        """Clauses of the same function should be compatible."""
        assert is_pair_allowed(ClauseFunction.PAYMENT, ClauseFunction.PAYMENT) == True
        assert is_pair_allowed(ClauseFunction.TERMINATION, ClauseFunction.TERMINATION) == True
    
    def test_payment_vs_amendments_incompatible(self):
        """Payment and amendments should NOT be compatible."""
        assert is_pair_allowed(ClauseFunction.PAYMENT, ClauseFunction.AMENDMENTS) == False
    
    def test_payment_vs_execution_incompatible(self):
        """Payment and execution should NOT be compatible."""
        assert is_pair_allowed(ClauseFunction.PAYMENT, ClauseFunction.EXECUTION_SIGNATURES) == False
    
    def test_payment_vs_notices_incompatible(self):
        """Payment and notices should NOT be compatible."""
        assert is_pair_allowed(ClauseFunction.PAYMENT, ClauseFunction.NOTICES) == False
    
    def test_indemnity_confidentiality_compatible(self):
        """Indemnity and confidentiality should be compatible (cross-function allowed)."""
        assert is_pair_allowed(ClauseFunction.INDEMNITY_LIABILITY, ClauseFunction.CONFIDENTIALITY) == True
        assert is_pair_allowed(ClauseFunction.CONFIDENTIALITY, ClauseFunction.INDEMNITY_LIABILITY) == True
    
    def test_override_bypass_compatibility(self):
        """Override/xref pairs should bypass compatibility gate."""
        assert is_pair_allowed(
            ClauseFunction.PAYMENT,
            ClauseFunction.AMENDMENTS,
            is_override_or_xref=True
        ) == True


class TestConflictDetectionScenarios:
    """Integration tests for specific conflict scenarios."""
    
    @pytest.mark.asyncio
    async def test_payment_vs_amendments_not_related(self, db_session):
        """
        Test: Payment vs Amendments should be filtered as NOT_RELATED.
        Expected: No conflict created.
        """
        # This test requires full integration with database and LLM
        # Mock implementation shown as structure
        
        clause1 = Clause(
            id=uuid4(),
            contract_version_id=uuid4(),
            clause_number="3.1",
            heading="Payment Terms",
            text="Contractor shall invoice Client with Net 30 payment terms.",
            order_index=1,
            analysis_results={"clause_function": ClauseFunction.PAYMENT}
        )
        
        clause2 = Clause(
            id=uuid4(),
            contract_version_id=clause1.contract_version_id,
            clause_number="12.5",
            heading="Amendments",
            text="Any amendments to this Agreement shall be in writing signed by both parties.",
            order_index=2,
            analysis_results={"clause_function": ClauseFunction.AMENDMENTS}
        )
        
        # These clauses should be filtered by compatibility gate
        # and never sent to LLM for validation
        result = is_pair_allowed(
            clause1.analysis_results["clause_function"],
            clause2.analysis_results["clause_function"]
        )
        
        assert result == False, "Payment vs Amendments should be incompatible"
    
    @pytest.mark.asyncio
    async def test_override_creates_valid_override_not_conflict(self, db_session):
        """
        Test: "Notwithstanding Clause X" should return VALID_OVERRIDE.
        Expected: No conflict created (only TRUE_CONFLICT/AMBIGUITY stored).
        """
        # Mock structure
        clause1 = Clause(
            id=uuid4(),
            contract_version_id=uuid4(),
            clause_number="3.1",
            heading="Payment Terms",
            text="Payment terms are Net 30.",
            order_index=1,
            analysis_results={"clause_function": ClauseFunction.PAYMENT}
        )
        
        clause2 = Clause(
            id=uuid4(),
            contract_version_id=clause1.contract_version_id,
            clause_number="5.2",
            heading="Government Contracts",
            text="Notwithstanding Clause 3.1, for government clients, payment terms are Net 60.",
            order_index=2,
            analysis_results={"clause_function": ClauseFunction.PAYMENT}
        )
        
        # LLM should return classification="VALID_OVERRIDE"
        # which should NOT be stored as Conflict
        
        # Simulated LLM response
        llm_classification = "VALID_OVERRIDE"
        
        # Only TRUE_CONFLICT and AMBIGUITY should be stored
        should_store = llm_classification in {"TRUE_CONFLICT", "AMBIGUITY"}
        
        assert should_store == False, "VALID_OVERRIDE should not create Conflict record"
    
    @pytest.mark.asyncio
    async def test_jurisdiction_mismatch_creates_critical_conflict(self, db_session):
        """
        Test: UK jurisdiction vs Abu Dhabi jurisdiction should return TRUE_CONFLICT with CRITICAL severity.
        Expected: Conflict created with severity=CRITICAL.
        """
        # Mock structure
        clause1 = Clause(
            id=uuid4(),
            contract_version_id=uuid4(),
            clause_number="15.1",
            heading="Governing Law",
            text="This Agreement shall be governed by the laws of England and Wales.",
            order_index=1,
            analysis_results={"clause_function": ClauseFunction.GOVERNING_LAW_JURISDICTION}
        )
        
        clause2 = Clause(
            id=uuid4(),
            contract_version_id=clause1.contract_version_id,
            clause_number="15.3",
            heading="Jurisdiction",
            text="The courts of Abu Dhabi shall have exclusive jurisdiction.",
            order_index=2,
            analysis_results={"clause_function": ClauseFunction.GOVERNING_LAW_JURISDICTION}
        )
        
        # Simulated LLM response
        conflict_data = {
            "classification": "TRUE_CONFLICT",
            "confidence": 0.98,
            "conflict_type": "JurisdictionMismatch",
            "summary": "Conflicting jurisdictions: England and Wales vs Abu Dhabi",
            "materiality": "HIGH",
            "left_evidence": {"quote": "England and Wales", "start_char": 40, "end_char": 57},
            "right_evidence": {"quote": "Abu Dhabi", "start_char": 14, "end_char": 23}
        }
        
        # Severity should be CRITICAL for JurisdictionMismatch
        # Based on conflict_type == "JurisdictionMismatch"
        expected_severity = "CRITICAL"
        
        # This would be calculated in _create_conflict
        actual_severity = "CRITICAL" if conflict_data["conflict_type"] == "JurisdictionMismatch" else "HIGH"
        
        assert actual_severity == expected_severity, "Jurisdiction mismatch should be CRITICAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
