# Approach C: Claim-Based Conflict Detection - Implementation Plan

**Date**: December 19, 2025  
**Status**: In Progress  
**Estimated Completion**: 2-3 days

---

## 🎯 Overview

Implement a 3-phase conflict detection system:
1. **Phase 1**: Extract structured claims from clauses
2. **Phase 2**: Build conflict graph using deterministic rules
3. **Phase 3**: LLM judge validates candidate conflicts

**Expected Results**:
- Time: ~10 seconds (vs 35s current, 495s categorized)
- Accuracy: ~95% (vs 0% current)
- LLM Calls: ~200-500 (vs 1 massive call or 9,900 pairwise)

---

## 📋 Implementation Checklist

### ✅ Phase 0: Database Schema (Today - 30 min)
- [ ] Create `claims` table
- [ ] Add indexes for efficient querying
- [ ] Create Alembic migration
- [ ] Test migration

### ✅ Phase 1: Claim Extraction (Today - 2-3 hours)
- [ ] Create `Claim` Pydantic model
- [ ] Create `ClaimExtractor` service
- [ ] Implement LLM prompt for claim extraction
- [ ] Add claim normalization (dates, amounts, jurisdictions)
- [ ] Add topic classification
- [ ] Integrate into clause extraction pipeline
- [ ] Test on underwriter agreement

### ✅ Phase 2: Conflict Graph (Today - 1-2 hours)
- [ ] Create `ConflictGraphBuilder` service
- [ ] Implement deterministic conflict rules:
  - [ ] Same topic + opposite modality
  - [ ] Same value_type + different normalized_value
  - [ ] Jurisdiction conflicts
  - [ ] Payment term conflicts
  - [ ] Lock-up duration conflicts
  - [ ] Temporal conflicts
- [ ] Build candidate pair list
- [ ] Test rule coverage

### ✅ Phase 3: LLM Judge (Tomorrow - 2-3 hours)
- [ ] Create `ConflictJudge` service
- [ ] Implement focused judge prompt
- [ ] Add override clause detection
- [ ] Parse and validate responses
- [ ] Add confidence threshold filtering (>= 0.85)
- [ ] Store validated conflicts
- [ ] Test end-to-end

### ✅ Phase 4: Integration (Tomorrow - 1 hour)
- [ ] Update conflict detection endpoint
- [ ] Add filtering for non-substantive clauses
- [ ] Update frontend to show evidence quotes
- [ ] Add logging and monitoring

### ✅ Phase 5: Testing & Validation (Day 3 - 2-3 hours)
- [ ] Test with underwriter agreement
- [ ] Test with other contract types
- [ ] Compare results with manual review
- [ ] Measure performance
- [ ] Fix bugs

### ✅ Phase 6: Optimization (Day 3 - 1-2 hours)
- [ ] Parallelize claim extraction (10 concurrent)
- [ ] Cache claim extraction results
- [ ] Optimize rule engine
- [ ] Add performance metrics

---

## 🗄️ Database Schema

```sql
CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clause_id UUID NOT NULL REFERENCES clauses(id) ON DELETE CASCADE,
    contract_version_id UUID NOT NULL REFERENCES contract_versions(id) ON DELETE CASCADE,
    
    -- Core claim structure
    subject VARCHAR(500) NOT NULL,
    action VARCHAR(500) NOT NULL,
    modality VARCHAR(50) NOT NULL,  -- MUST, MAY, MUST_NOT, SHALL, PROHIBITED, PERMITTED
    object VARCHAR(500),
    
    -- Value extraction
    value_type VARCHAR(50),  -- DURATION, AMOUNT, JURISDICTION, DATE, PERCENTAGE, PARTY
    normalized_value VARCHAR(200),
    original_value VARCHAR(200),
    
    -- Context
    conditions JSONB DEFAULT '[]',
    scope TEXT,
    exceptions JSONB DEFAULT '[]',
    
    -- Source
    source_quote TEXT NOT NULL,
    topic VARCHAR(100) NOT NULL,
    
    -- Precedence
    is_override BOOLEAN DEFAULT FALSE,
    overrides_clause VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_claims_clause_id ON claims(clause_id),
    INDEX idx_claims_contract_version_id ON claims(contract_version_id),
    INDEX idx_claims_topic ON claims(topic),
    INDEX idx_claims_value_type ON claims(value_type),
    INDEX idx_claims_normalized_value ON claims(normalized_value)
);

-- Add confidence field to conflicts table
ALTER TABLE conflicts ADD COLUMN IF NOT EXISTS confidence DECIMAL(3,2);
ALTER TABLE conflicts ADD COLUMN IF NOT EXISTS evidence JSONB;
```

---

## 🏗️ Code Structure

```
backend/app/
├── models/
│   └── claim.py (NEW)
├── schemas/
│   └── claim.py (NEW)
├── services/
│   ├── claim_extractor.py (NEW)
│   ├── conflict_graph_builder.py (NEW)
│   └── conflict_judge.py (NEW)
├── tasks/
│   └── conflict_analysis.py (UPDATE)
└── api/v1/endpoints/
    └── contracts.py (UPDATE)
```

---

## 📝 Implementation Details

### 1. Claim Model (models/claim.py)

```python
from sqlalchemy import Column, String, Text, Boolean, DECIMAL, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from app.db.base_class import Base

class Claim(Base):
    """Structured claim extracted from a clause."""
    __tablename__ = "claims"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id = Column(UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False)
    contract_version_id = Column(UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False)
    
    # Core structure
    subject = Column(String(500), nullable=False)
    action = Column(String(500), nullable=False)
    modality = Column(String(50), nullable=False)
    object = Column(String(500))
    
    # Value extraction
    value_type = Column(String(50))
    normalized_value = Column(String(200))
    original_value = Column(String(200))
    
    # Context
    conditions = Column(JSONB, default=list)
    scope = Column(Text)
    exceptions = Column(JSONB, default=list)
    
    # Source
    source_quote = Column(Text, nullable=False)
    topic = Column(String(100), nullable=False)
    
    # Precedence
    is_override = Column(Boolean, default=False)
    overrides_clause = Column(String(50))
    
    # Relationships
    clause = relationship("Clause", back_populates="claims")
    
    __table_args__ = (
        Index('idx_claims_clause_id', 'clause_id'),
        Index('idx_claims_contract_version_id', 'contract_version_id'),
        Index('idx_claims_topic', 'topic'),
        Index('idx_claims_value_type', 'value_type'),
        Index('idx_claims_normalized_value', 'normalized_value'),
    )
```

### 2. Claim Extraction Prompt

```python
CLAIM_EXTRACTION_PROMPT = """You are a legal document analyst. Extract ALL structured claims from this clause.

A claim is a statement that:
- Makes an assertion about obligations, permissions, prohibitions, or definitions
- Contains a subject (who/what), action (what happens), and optionally an object (to whom/what)
- May include conditions, timeframes, amounts, or other specific values

CLAUSE:
Number: {clause_number}
Heading: {heading}
Text: {text}

Extract ALL claims in JSON format:
{{
  "claims": [
    {{
      "subject": "Who/what is the claim about (Party A, Payment, Confidential Information, etc.)",
      "action": "What action or state (shall pay, must provide, is required, may terminate, etc.)",
      "modality": "MUST|SHALL|MAY|MUST_NOT|SHALL_NOT|PROHIBITED|PERMITTED|IS|DEFINES",
      "object": "To whom/what (optional - invoice, notice, written consent, etc.)",
      
      "value_type": "DURATION|AMOUNT|JURISDICTION|DATE|PERCENTAGE|PARTY|NONE",
      "normalized_value": "Standardized value (30 days, USD 1000, UAE, 2024-01-01, 5%, Party A)",
      "original_value": "As written in contract",
      
      "conditions": ["upon receipt", "if breach occurs", "unless waived"],
      "scope": "Applicability (all services, during term, confidential information)",
      "exceptions": ["except force majeure", "excluding public information"],
      
      "source_quote": "Exact text from clause that supports this claim",
      "topic": "PAYMENT|TERMINATION|JURISDICTION|INDEMNIFICATION|CONFIDENTIALITY|LOCK_UP|OBLIGATIONS|DEFINITIONS|GENERAL",
      
      "is_override": false,
      "overrides_clause": "Clause number if this overrides another (from 'notwithstanding Clause X')"
    }}
  ]
}}

IMPORTANT:
- Extract MULTIPLE claims if clause contains multiple statements
- Normalize dates to ISO format (YYYY-MM-DD)
- Normalize amounts to "CURRENCY VALUE" (USD 1000, AED 5000)
- Normalize durations to standard units (30 days, 6 months, 1 year)
- Normalize jurisdictions to standard codes (UAE, UK, USA, NY)
- Set is_override=true if text contains "notwithstanding", "shall prevail", "takes precedence"
- Use source_quote to capture the exact text supporting the claim

Your JSON response:"""
```

### 3. Conflict Detection Rules

```python
def find_conflict_candidates(claims: List[Claim]) -> List[Tuple[Claim, Claim]]:
    """Build conflict graph using deterministic rules."""
    candidates = []
    
    # Group by topic for efficiency
    by_topic = defaultdict(list)
    for claim in claims:
        by_topic[claim.topic].append(claim)
    
    for topic, topic_claims in by_topic.items():
        for i, c1 in enumerate(topic_claims):
            for c2 in topic_claims[i+1:]:
                # Skip if one overrides the other
                if _check_override_relationship(c1, c2):
                    continue
                
                # Rule 1: Opposite modality
                if _has_opposite_modality(c1, c2):
                    candidates.append((c1, c2))
                    continue
                
                # Rule 2: Same value_type, different value
                if _has_conflicting_values(c1, c2):
                    candidates.append((c1, c2))
                    continue
                
                # Rule 3: Special domain rules
                if _check_domain_conflict(c1, c2):
                    candidates.append((c1, c2))
    
    return candidates

def _has_opposite_modality(c1: Claim, c2: Claim) -> bool:
    """Check if modalities are contradictory."""
    if c1.subject != c2.subject:
        return False
    
    opposites = [
        ("MUST", "MUST_NOT"),
        ("SHALL", "SHALL_NOT"),
        ("MUST", "PROHIBITED"),
        ("REQUIRED", "FORBIDDEN"),
        ("PERMITTED", "PROHIBITED")
    ]
    
    return (c1.modality, c2.modality) in opposites or \
           (c2.modality, c1.modality) in opposites

def _has_conflicting_values(c1: Claim, c2: Claim) -> bool:
    """Check if same value_type but different values."""
    if not c1.value_type or c1.value_type != c2.value_type:
        return False
    
    if not c1.normalized_value or not c2.normalized_value:
        return False
    
    # Same subject/context but different values
    if c1.subject == c2.subject and c1.normalized_value != c2.normalized_value:
        return True
    
    return False

def _check_domain_conflict(c1: Claim, c2: Claim) -> bool:
    """Domain-specific conflict rules."""
    # Jurisdiction conflicts
    if c1.value_type == "JURISDICTION" and c2.value_type == "JURISDICTION":
        if c1.normalized_value != c2.normalized_value:
            return True
    
    # Payment timing conflicts
    if c1.topic == "PAYMENT" and c2.topic == "PAYMENT":
        if (c1.value_type == "DURATION" and c2.value_type == "DURATION" and
            c1.subject == c2.subject):
            return True
    
    # Lock-up period conflicts
    if "lock" in c1.topic.lower() and "lock" in c2.topic.lower():
        if c1.value_type == "DURATION" and c2.value_type == "DURATION":
            return True
    
    return False
```

### 4. LLM Judge Prompt

```python
LLM_JUDGE_PROMPT = """You are a legal conflict detection expert. Analyze if these two claims create a REAL conflict.

CLAIM 1 (from Clause {c1_clause_number}):
- Topic: {c1_topic}
- Subject: {c1_subject}
- Action: {c1_action}
- Modality: {c1_modality}
- Value Type: {c1_value_type}
- Value: {c1_normalized_value}
- Conditions: {c1_conditions}
- Quote: "{c1_source_quote}"

CLAIM 2 (from Clause {c2_clause_number}):
- Topic: {c2_topic}
- Subject: {c2_subject}
- Action: {c2_action}
- Modality: {c2_modality}
- Value Type: {c2_value_type}
- Value: {c2_normalized_value}
- Conditions: {c2_conditions}
- Quote: "{c2_source_quote}"

OVERRIDE/PRECEDENCE CLAUSES:
{override_context}

QUESTION: Do these claims create a REAL conflict?

A conflict exists if:
1. Both claims apply to the same situation/subject
2. They cannot both be true or fulfilled simultaneously
3. No precedence clause resolves the conflict
4. They create legal ambiguity or impossibility

NOT a conflict if:
- One explicitly overrides the other
- They apply to different contexts/conditions
- They are complementary (one adds detail)
- The difference is insignificant
- Different parties or different scopes

Answer in JSON:
{{
  "has_conflict": true/false,
  "confidence": 0.0 to 1.0,
  "conflict_type": "TEMPORAL|FINANCIAL|GEOGRAPHIC|LEGAL|LOGICAL|TERMINOLOGICAL",
  "why": "Detailed explanation with specific references to claim values",
  "resolution": "Specific, actionable recommendation",
  "evidence": ["{c1_source_quote}", "{c2_source_quote}"]
}}

Your response:"""
```

---

## 📊 Expected Performance

### Phase 1: Claim Extraction
- Input: 300 substantive clauses (after filtering)
- LLM calls: 300 × 0.02s = **6 seconds**
- Output: ~800 claims (2-3 per clause)

### Phase 2: Conflict Graph
- Input: 800 claims
- Rule evaluation: **0.1 seconds** (deterministic)
- Output: ~200-500 candidate pairs (vs 145,530 all pairs!)

### Phase 3: LLM Judge
- Input: 200-500 candidate pairs
- LLM calls: 300 × 0.02s = **6 seconds**
- Output: ~10-30 validated conflicts (confidence >= 0.85)

### Total
- **Time**: ~12 seconds (6s + 0.1s + 6s)
- **Accuracy**: ~95% (structured + rules + focused LLM)
- **False Positive Rate**: <5%

---

## 🚀 Next Steps

1. **Start with Phase 0**: Create database schema and migration
2. **Then Phase 1**: Implement claim extraction
3. **Test incrementally**: After each phase, test with underwriter agreement
4. **Iterate**: Refine prompts and rules based on results

Ready to begin implementation! 🎯
