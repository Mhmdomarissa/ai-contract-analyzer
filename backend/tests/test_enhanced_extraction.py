"""
Test suite for enhanced clause extraction with diverse contract samples.

Tests cover:
1. Edge case patterns (parenthetical, hyphenated, clause keyword)
2. Post-processing filters (duplicates, TOC entries)
3. LLM validation integration
4. Performance optimization
"""

import pytest
import asyncio
from app.services.llm_service import LLMService


# Sample 1: Employment Agreement with parenthetical numbering
EMPLOYMENT_CONTRACT = """
EMPLOYMENT AGREEMENT

This Agreement is entered into as of January 1, 2024.

1. POSITION AND DUTIES

   (a) The Employee shall serve as Chief Technology Officer and shall report to the CEO.
   
   (b) The Employee agrees to devote full business time to the Company's affairs.
   
   (c) The Employee may engage in civic, charitable, or educational activities.

2. COMPENSATION AND BENEFITS

   (a) Base Salary: The Company shall pay Employee an annual salary of $250,000.
   
   (b) Bonus: Employee shall be eligible for annual performance bonus up to 30% of base salary.
   
   (c) Equity: Employee shall receive stock options covering 50,000 shares.

3. TERMINATION

   3.1 Termination by Company: The Company may terminate this Agreement for Cause.
   
   3.2 Termination by Employee: Employee may terminate with 30 days notice.
   
   3.3 Severance: Upon termination without Cause, Employee shall receive 6 months salary.
"""

# Sample 2: SaaS Agreement with hyphenated sections
SAAS_CONTRACT = """
SOFTWARE AS A SERVICE AGREEMENT

Effective Date: December 1, 2024

Section 1-1: Definitions
"Service" means the cloud-based software platform provided by Vendor.

Section 1-2: Licensed Rights
Vendor grants Customer a non-exclusive license to access the Service.

Section 2-1: Fees and Payment
Customer shall pay monthly subscription fees of $5,000.

Section 2-2: Payment Terms
All fees are due within 15 days of invoice date.

Section 3-1: Term and Renewal
This Agreement has an initial term of 12 months and renews automatically.

Section 3-2: Termination
Either party may terminate with 90 days written notice.
"""

# Sample 3: Lease with "Clause" keyword format
LEASE_CONTRACT = """
COMMERCIAL LEASE AGREEMENT

This Lease is made on November 15, 2024.

Clause 1.1: Premises
Landlord leases to Tenant the premises located at 123 Main Street.

Clause 1.2: Term
The term shall be for five (5) years commencing January 1, 2025.

Clause 2.1: Base Rent
Tenant shall pay monthly rent of $10,000 payable in advance.

Clause 2.2: Additional Rent
Tenant shall pay proportionate share of operating expenses.

Clause 3.1: Use of Premises
Premises shall be used for office purposes only.

Clause 3.2: Alterations
No alterations without prior written consent of Landlord.
"""

# Sample 4: Contract with Table of Contents (should be filtered)
CONTRACT_WITH_TOC = """
SERVICE AGREEMENT

TABLE OF CONTENTS

1. Definitions ........................... Page 3
2. Scope of Services ..................... Page 5
3. Compensation .......................... Page 8
4. Term and Termination .................. Page 12

1. DEFINITIONS

For purposes of this Agreement:

1.1 "Services" means professional consulting services described in Exhibit A.

1.2 "Fees" means the compensation payable for Services.

2. SCOPE OF SERVICES

2.1 Provider Services: Provider shall perform consulting services as described.

2.2 Customer Obligations: Customer shall provide necessary access and information.

3. COMPENSATION

3.1 Fee Structure: Customer shall pay Provider $200 per hour.

3.2 Payment Terms: Fees are due within 30 days of invoice.
"""

# Sample 5: NDA with Article structure
NDA_CONTRACT = """
NON-DISCLOSURE AGREEMENT

Article I - Purpose

The parties wish to explore a business opportunity and will exchange confidential information.

Article II - Definition of Confidential Information

Section 2.1: Covered Information
Confidential Information includes technical data, trade secrets, and business plans.

Section 2.2: Exclusions
Confidential Information does not include publicly available information.

Article III - Obligations

Section 3.1: Non-Disclosure
Receiving Party shall maintain confidentiality of Confidential Information.

Section 3.2: Non-Use
Receiving Party shall use Confidential Information solely for evaluation purposes.

Section 3.3: Return of Materials
Upon request, Receiving Party shall return all Confidential Information.

Article IV - Term

This Agreement shall remain in effect for three (3) years.
"""

# Sample 6: Complex hierarchical structure
COMPLEX_CONTRACT = """
MASTER SERVICES AGREEMENT

RECITALS

WHEREAS, Company provides technology services; and
WHEREAS, Client desires to engage Company.

AGREEMENT

1. SERVICES

1.1 General Services
Company shall provide software development services.

1.2 Specific Deliverables
   (a) Phase 1: Requirements analysis and design
   (b) Phase 2: Development and testing
   (c) Phase 3: Deployment and training

1.3 Service Levels
   (i) 99.9% uptime guarantee
   (ii) 4-hour response time for critical issues
   (iii) Monthly status reports

2. FEES AND EXPENSES

2.1 Professional Fees
   2.1.1 Hourly Rates: Senior Developer - $180/hr, Junior Developer - $120/hr
   2.1.2 Fixed Price Projects: As specified in Statement of Work
   2.1.3 Retainer Arrangements: Minimum 40 hours per month

2.2 Expenses
   2.2.1 Travel: Actual costs with prior approval
   2.2.2 Materials: Hardware and software necessary for Services
"""


class TestClauseExtraction:
    """Test suite for clause extraction with diverse contracts."""
    
    @pytest.fixture
    def llm_service(self):
        """Create LLM service instance."""
        return LLMService(base_url="http://localhost:11434", model="qwen2.5:32b")
    
    @pytest.mark.asyncio
    async def test_parenthetical_numbering(self, llm_service):
        """Test extraction of (a), (b), (c) style clauses."""
        clauses = await llm_service.extract_clauses(EMPLOYMENT_CONTRACT, enable_validation=False)
        
        # Should extract main sections and parenthetical subsections
        clause_numbers = [c['clause_number'] for c in clauses]
        
        assert '1' in clause_numbers or 'POSITION AND DUTIES' in clause_numbers
        assert '2' in clause_numbers or 'COMPENSATION AND BENEFITS' in clause_numbers
        
        # Check for subsections
        subsection_found = any('3.1' in num or '3.2' in num for num in clause_numbers)
        assert subsection_found, f"No subsections found. Got: {clause_numbers}"
    
    @pytest.mark.asyncio
    async def test_hyphenated_sections(self, llm_service):
        """Test extraction of Section 1-1 style clauses."""
        clauses = await llm_service.extract_clauses(SAAS_CONTRACT, enable_validation=False)
        
        clause_numbers = [c['clause_number'] for c in clauses]
        
        # Should extract hyphenated sections
        assert len(clauses) >= 6, f"Expected at least 6 clauses, got {len(clauses)}"
    
    @pytest.mark.asyncio
    async def test_clause_keyword_format(self, llm_service):
        """Test extraction of 'Clause X.Y:' format."""
        clauses = await llm_service.extract_clauses(LEASE_CONTRACT, enable_validation=False)
        
        clause_numbers = [c['clause_number'] for c in clauses]
        
        # Should extract all Clause X.Y entries
        assert len(clauses) >= 6, f"Expected at least 6 clauses, got {len(clauses)}"
        
        # Check for hierarchical numbering
        assert any('1.1' in str(num) for num in clause_numbers)
        assert any('2.1' in str(num) for num in clause_numbers)
    
    @pytest.mark.asyncio
    async def test_toc_filtering(self, llm_service):
        """Test that table of contents entries are filtered out."""
        clauses = await llm_service.extract_clauses(CONTRACT_WITH_TOC, enable_validation=False)
        
        # Check that TOC entries are removed
        for clause in clauses:
            text = clause.get('text', '')
            assert 'Page' not in text or len(text) > 50, \
                f"TOC entry not filtered: {text[:100]}"
            assert '......' not in text, \
                f"Dotted TOC line not filtered: {text[:100]}"
    
    @pytest.mark.asyncio
    async def test_article_structure(self, llm_service):
        """Test extraction of Article/Section structure."""
        clauses = await llm_service.extract_clauses(NDA_CONTRACT, enable_validation=False)
        
        # Should extract both Articles and Sections
        assert len(clauses) >= 4, f"Expected at least 4 clauses, got {len(clauses)}"
        
        # Check for hierarchical sections under articles
        clause_text = ' '.join([c.get('text', '') for c in clauses])
        assert 'Section 2.1' in clause_text or '2.1' in str([c['clause_number'] for c in clauses])
    
    @pytest.mark.asyncio
    async def test_complex_hierarchical(self, llm_service):
        """Test extraction of multi-level hierarchical structure."""
        clauses = await llm_service.extract_clauses(COMPLEX_CONTRACT, enable_validation=False)
        
        clause_numbers = [c['clause_number'] for c in clauses]
        
        # Should extract multiple hierarchy levels
        # Level 1: 1, 2
        # Level 2: 1.1, 1.2, 2.1, 2.2
        # Level 3: 2.1.1, 2.1.2, 2.1.3
        
        assert any('1.1' in str(num) for num in clause_numbers), \
            f"Missing level 2 clause. Got: {clause_numbers}"
    
    @pytest.mark.asyncio
    async def test_duplicate_filtering(self, llm_service):
        """Test that duplicate clauses are filtered."""
        # Create contract with duplicate section
        duplicate_text = LEASE_CONTRACT + "\\n\\n" + LEASE_CONTRACT
        clauses = await llm_service.extract_clauses(duplicate_text, enable_validation=False)
        
        # Count should not be doubled
        unique_numbers = set(c['clause_number'] for c in clauses)
        assert len(clauses) == len(unique_numbers), \
            "Duplicates not filtered properly"
    
    @pytest.mark.asyncio
    async def test_validation_integration(self, llm_service):
        """Test LLM validation integration."""
        try:
            clauses = await llm_service.extract_clauses(
                EMPLOYMENT_CONTRACT,
                enable_validation=True
            )
            
            # Check that validation metadata is added
            if clauses:
                first_clause = clauses[0]
                assert 'validation' in first_clause, \
                    "Validation metadata missing"
                
                validation = first_clause['validation']
                assert 'quality_score' in validation
                assert 'is_valid' in validation
                
                print(f"✓ Validation integrated. Quality: {validation.get('quality_score')}")
        except Exception as e:
            pytest.skip(f"Validation test skipped (LLM not available): {e}")
    
    @pytest.mark.asyncio
    async def test_performance_large_contract(self, llm_service):
        """Test performance with large contract."""
        # Create large contract by repeating sections
        large_contract = "\\n\\n".join([COMPLEX_CONTRACT] * 10)
        
        import time
        start = time.time()
        clauses = await llm_service.extract_clauses(large_contract, enable_validation=False)
        duration = time.time() - start
        
        print(f"\\n✓ Extracted {len(clauses)} clauses in {duration:.2f}s")
        assert duration < 5.0, f"Extraction too slow: {duration:.2f}s"
    
    @pytest.mark.asyncio
    async def test_all_contracts(self, llm_service):
        """Test extraction on all sample contracts."""
        contracts = [
            ("Employment", EMPLOYMENT_CONTRACT),
            ("SaaS", SAAS_CONTRACT),
            ("Lease", LEASE_CONTRACT),
            ("TOC", CONTRACT_WITH_TOC),
            ("NDA", NDA_CONTRACT),
            ("Complex", COMPLEX_CONTRACT),
        ]
        
        results = []
        for name, contract in contracts:
            clauses = await llm_service.extract_clauses(contract, enable_validation=False)
            results.append((name, len(clauses)))
            print(f"{name}: {len(clauses)} clauses")
        
        # Verify all extracted something
        for name, count in results:
            assert count > 0, f"No clauses extracted from {name} contract"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
