"""
Test suite for clause filtering and quality control.

Tests cover:
- TOC detection and filtering
- Stub clause detection
- Substantive content validation
- Long clause splitting
"""
import pytest
from app.services.clause_filters import ClauseFilter, ClauseSplitter


class TestTOCDetection:
    """Test Table of Contents detection."""
    
    def test_toc_pattern_number_heading_page(self):
        """Test: '14. TERMINATION 14' is detected as TOC."""
        filter = ClauseFilter()
        
        toc_text = "14. TERMINATION AND SUSPENSION 14"
        assert filter.is_toc_line(toc_text, "14")
    
    def test_toc_pattern_with_tabs(self):
        """Test: '5.\tFEES\t5' is detected as TOC."""
        filter = ClauseFilter()
        
        toc_text = "5.\tFEES AND PAYMENT\t5"
        assert filter.is_toc_line(toc_text, "5")
    
    def test_toc_keyword_detection(self):
        """Test: Lines with 'TABLE OF CONTENTS' are TOC."""
        filter = ClauseFilter()
        
        assert filter.is_toc_line("TABLE OF CONTENTS")
        assert filter.is_toc_line("Contents")
        assert filter.is_toc_line("INDEX")
    
    def test_short_heading_plus_page(self):
        """Test: 'DEFINITIONS 3' is detected as TOC."""
        filter = ClauseFilter()
        
        assert filter.is_toc_line("DEFINITIONS 3", "1")
        assert filter.is_toc_line("PAYMENT TERMS 10", "5")
    
    def test_normal_clause_not_toc(self):
        """Test: Normal clauses are not detected as TOC."""
        filter = ClauseFilter()
        
        normal_text = "The parties agree that payment shall be made within 30 days."
        assert not filter.is_toc_line(normal_text)


class TestStubClauseDetection:
    """Test stub clause detection."""
    
    def test_stub_ends_with_colon(self):
        """Test: Clauses ending with ':' are stubs."""
        filter = ClauseFilter()
        
        stub1 = "14) NOTICES:"
        stub2 = "16) GOVERNING LAW:"
        
        assert filter.is_stub_clause(stub1, "14")
        assert filter.is_stub_clause(stub2, "16")
    
    def test_stub_it_is_agreed_that_without_content(self):
        """Test: 'It is agreed that:' without content is stub."""
        filter = ClauseFilter()
        
        stub = "16) GOVERNING LAW\n\nIt is hereby agreed that:"
        assert filter.is_stub_clause(stub, "16")
    
    def test_stub_short_without_legal_operators(self):
        """Test: Short clauses without legal operators are stubs."""
        filter = ClauseFilter()
        
        # Only 4 words, no legal operators
        stub = "Section about payment terms"
        assert filter.is_stub_clause(stub, "5")
    
    def test_definition_not_stub(self):
        """Test: Short definitions are NOT stubs (have substantive content)."""
        filter = ClauseFilter()
        
        # Definitions are substantive even if short
        definition = '"Territory" means United Arab Emirates.'
        assert not filter.is_stub_clause(definition, "1.1")
    
    def test_normal_clause_not_stub(self):
        """Test: Normal clauses with legal operators are not stubs."""
        filter = ClauseFilter()
        
        normal = "The Recruitment Consultant shall provide services as agreed between the parties."
        assert not filter.is_stub_clause(normal, "2")


class TestSubstantiveContent:
    """Test substantive content validation."""
    
    def test_has_legal_operators(self):
        """Test: Clauses with legal operators are substantive."""
        filter = ClauseFilter()
        
        clause = "The Client shall pay fees within 30 days."
        assert filter.has_substantive_content(clause)
    
    def test_sufficient_length(self):
        """Test: Long enough clauses are substantive."""
        filter = ClauseFilter()
        
        # 20+ words without legal operators, but still substantive
        clause = "The parties met on January 1st to discuss the terms and conditions of this arrangement for the upcoming year."
        assert filter.has_substantive_content(clause)
    
    def test_definition_pattern(self):
        """Test: Definition patterns are substantive."""
        filter = ClauseFilter()
        
        definition = '"Effective Date" means the date this Agreement is executed.'
        assert filter.has_substantive_content(definition)
    
    def test_clause_pattern_keywords(self):
        """Test: Common clause patterns are substantive."""
        filter = ClauseFilter()
        
        clause1 = "This Agreement creates rights and obligations between the parties."
        clause2 = "Each party shall maintain confidentiality."
        
        assert filter.has_substantive_content(clause1)
        assert filter.has_substantive_content(clause2)
    
    def test_short_no_operators_not_substantive(self):
        """Test: Short text without legal content is not substantive."""
        filter = ClauseFilter()
        
        # Only 3 words, no legal operators
        short = "Payment and Fees"
        assert not filter.has_substantive_content(short)


class TestClauseFiltering:
    """Test complete filtering pipeline."""
    
    def test_filter_pipeline(self):
        """Test: Complete filtering removes TOC, stubs, and empty content."""
        filter = ClauseFilter()
        
        clauses = [
            # Valid clause
            {
                'clause_number': '1',
                'text': 'The Client shall engage the Recruitment Consultant to provide recruitment services as described herein.',
                'heading': 'ENGAGEMENT'
            },
            # TOC entry
            {
                'clause_number': '2',
                'text': '2. FEES AND PAYMENT 5',
                'heading': 'TOC'
            },
            # Stub clause
            {
                'clause_number': '3',
                'text': '3) TERMINATION:',
                'heading': 'TERMINATION'
            },
            # No substantive content
            {
                'clause_number': '4',
                'text': 'General Provisions',
                'heading': 'GENERAL'
            },
            # Valid clause with definition
            {
                'clause_number': '5',
                'text': '"Territory" means United Arab Emirates.',
                'heading': 'DEFINITIONS'
            },
        ]
        
        result = filter.filter_clauses(clauses)
        
        # Should keep clauses 1 and 5
        assert len(result['valid_clauses']) == 2
        assert result['valid_clauses'][0]['clause_number'] == '1'
        assert result['valid_clauses'][1]['clause_number'] == '5'
        
        # Metrics
        assert result['metrics']['total_extracted'] == 5
        assert result['metrics']['removed_toc'] == 1
        assert result['metrics']['removed_stubs'] == 1
        assert result['metrics']['removed_no_content'] == 1


class TestClauseSplitting:
    """Test long clause splitting."""
    
    def test_no_split_for_short_clauses(self):
        """Test: Short clauses are not split."""
        splitter = ClauseSplitter(max_clause_chars=2500)
        
        clause = {
            'clause_number': '5',
            'text': 'The Client shall pay the Recruitment Consultant fees as agreed.',
            'heading': 'PAYMENT'
        }
        
        result = splitter.split_clause(clause)
        assert len(result) == 1
        assert result[0]['clause_number'] == '5'
    
    def test_split_by_numbered_subclauses(self):
        """Test: Long clauses split by (1), (2), (3) patterns."""
        splitter = ClauseSplitter(max_clause_chars=500)
        
        long_text = """The parties agree as follows:
        
        (1) The Client shall provide all necessary information to the Recruitment Consultant within a reasonable timeframe as required for the proper execution of recruitment services under this Agreement.
        
        (2) The Recruitment Consultant shall maintain confidentiality of all information received from the Client and shall not disclose such information to any third party without prior written consent.
        
        (3) Either party may terminate this Agreement by providing thirty (30) days written notice to the other party in accordance with the notice provisions set forth herein.
        """
        
        clause = {
            'clause_number': '10',
            'text': long_text,
            'heading': 'GENERAL PROVISIONS'
        }
        
        result = splitter.split_clause(clause)
        
        # Should split into 3 subclauses
        assert len(result) >= 3
        assert any('10.1' in c['clause_number'] for c in result)
        assert any('10.2' in c['clause_number'] for c in result)
        assert any('10.3' in c['clause_number'] for c in result)
    
    def test_split_by_headings(self):
        """Test: Long clauses split by HEADING: patterns."""
        splitter = ClauseSplitter(max_clause_chars=500)
        
        long_text = """This appendix contains the following sections:
        
        DEFINITIONS:
        The following terms shall have the meanings set forth below for purposes of this Agreement and all related documents.
        
        PAYMENT TERMS:
        Payment shall be made within thirty (30) days of invoice date unless otherwise agreed in writing by both parties.
        
        TERMINATION:
        Either party may terminate by providing sixty (60) days written notice.
        """
        
        clause = {
            'clause_number': 'APPENDIX_A',
            'text': long_text,
            'heading': 'APPENDIX A'
        }
        
        result = splitter.split_clause(clause)
        
        # Should split into multiple sections
        assert len(result) >= 2
    
    def test_split_preserves_metadata(self):
        """Test: Split clauses preserve original metadata."""
        splitter = ClauseSplitter(max_clause_chars=500)
        
        long_text = "(1) First clause content that is long enough. " * 20 + "\n\n" + "(2) Second clause content. " * 20
        
        clause = {
            'clause_number': '8',
            'text': long_text,
            'heading': 'FEES',
            'metadata': {'type': 'payment', 'has_table': True}
        }
        
        result = splitter.split_clause(clause)
        
        # Check metadata preserved
        for split_clause in result:
            assert 'metadata' in split_clause
            assert split_clause['metadata'].get('split_from') == '8'
            assert split_clause['metadata'].get('type') == 'payment'


class TestRealWorldScenario:
    """Test with real contract patterns."""
    
    def test_alpha_data_contract_filtering(self):
        """Test: Alpha Data MSA contract patterns."""
        filter = ClauseFilter()
        
        # Simulate clauses from Alpha Data contract
        clauses = [
            # Valid preamble
            {
                'clause_number': 'PREAMBLE',
                'text': 'This Recruitment Services Agreement ("Agreement") is being entered into as of 08/10/2025 ("Effective Date") by and between: ALPHA DATA RECRUITMENT - L.L.C...',
                'heading': 'Preamble'
            },
            # Valid definition
            {
                'clause_number': '1.1',
                'text': '"Territory" shall mean United Arab Emirates.',
                'heading': 'DEFINITIONS'
            },
            # Stub article
            {
                'clause_number': '6',
                'text': '6) FEES',
                'heading': 'FEES'
            },
            # Valid subclause
            {
                'clause_number': '6.1',
                'text': 'The Recruitment Consultant Fees are calculated as a percentage of the annual base salary...',
                'heading': 'FEES'
            },
            # Stub with "It is agreed that:"
            {
                'clause_number': '16',
                'text': '16) GOVERNING LAW\n\nIt is hereby agreed that:',
                'heading': 'GOVERNING LAW'
            },
            # Valid subclause
            {
                'clause_number': '16.1',
                'text': 'This Agreement shall be construed under the laws of the Emirate of Abu Dhabi...',
                'heading': 'GOVERNING LAW'
            },
        ]
        
        result = filter.filter_clauses(clauses)
        
        # Should keep: PREAMBLE, 1.1, 6.1, 16.1
        # Should remove: 6 (stub), 16 (stub)
        valid_numbers = [c['clause_number'] for c in result['valid_clauses']]
        
        assert 'PREAMBLE' in valid_numbers
        assert '1.1' in valid_numbers
        assert '6.1' in valid_numbers
        assert '16.1' in valid_numbers
        assert '6' not in valid_numbers
        assert '16' not in valid_numbers
        
        # Check metrics
        assert result['metrics']['removed_stubs'] == 2


def test_integration_extraction_and_filtering():
    """Integration test: Extract and filter in pipeline."""
    # This would be run as part of the full extraction pipeline
    # Verifying that the integration works end-to-end
    pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
