# Conflict Detection Refinement - Quick Reference

## What Changed?

### 1. Clause Classification (Automatic)
Every clause is now automatically classified into one of 12 functions:
- **PAYMENT** - Payment terms, fees, invoicing
- **TERMINATION** - Contract termination clauses
- **GOVERNING_LAW_JURISDICTION** - Legal jurisdiction, governing law
- **CONFIDENTIALITY** - NDA, confidential information
- **INDEMNITY_LIABILITY** - Liability, indemnification, damages
- **FORCE_MAJEURE** - Force majeure events
- **NOTICES** - Notice procedures
- **AMENDMENTS** - Amendment/variation procedures
- **DEFINITIONS** - Definitions, interpretations
- **SCOPE_SERVICES** - Scope of work, deliverables
- **EXECUTION_SIGNATURES** - Signature blocks, execution
- **MISC_ADMIN** - Everything else

### 2. Compatibility Filtering
Only compatible clause pairs are compared:
```
✅ Payment vs Payment
✅ Termination vs Termination
✅ Jurisdiction vs Jurisdiction
❌ Payment vs Amendments (BLOCKED)
❌ Payment vs Execution (BLOCKED)
❌ Payment vs Notices (BLOCKED)
```

### 3. Classification Results
LLM now classifies each relationship:
- **TRUE_CONFLICT** → Stored in database
- **AMBIGUITY** → Stored in database
- **VALID_OVERRIDE** → NOT stored (logged only)
- **EXCEPTION** → NOT stored (logged only)
- **COMPLEMENTARY** → NOT stored (logged only)
- **NOT_RELATED** → NOT stored (logged only)

### 4. Severity Calculation
New materiality-based severity:
```python
# Old (confidence-only)
0.95+ → CRITICAL
0.90-0.94 → HIGH
0.85-0.89 → MEDIUM

# New (materiality + function + type)
JurisdictionMismatch → CRITICAL (always)
Core functions (Payment, Termination, etc.) → HIGH
Ambiguity → MEDIUM (always)
Other → Based on materiality assessment
```

### 5. Highlight Spans
Conflicts now include exact text evidence:
```json
{
  "highlights": [
    {
      "clause_id": "...",
      "snippet": "payment within 30 days",
      "start_char": 45,
      "end_char": 68
    }
  ]
}
```

## API Impact

### Request (No Change)
```
POST /{contract_id}/detect-conflicts?strategy=enhanced
```

### Response (Enhanced)
```json
{
  "id": "...",
  "severity": "HIGH",
  "score": 0.92,
  "summary": "ValueMismatch: Payment terms differ",
  "explanation": "TRUE_CONFLICT: Payment terms differ: Net 30 vs Net 60",
  "left_clause": {...},
  "right_clause": {...},
  "highlights": [
    {
      "clause_id": "...",
      "snippet": "Net 30 days",
      "start_char": 50,
      "end_char": 61
    },
    {
      "clause_id": "...",
      "snippet": "Net 60 days",
      "start_char": 102,
      "end_char": 113
    }
  ]
}
```

## Expected Results

### Scenario 1: Payment vs Amendments
**Before:**
```
❌ Conflict detected: "Payment Net 30" vs "Amendments in writing"
   Stored as conflict
```

**After:**
```
✅ Filtered by compatibility gate (PAYMENT vs AMENDMENTS incompatible)
   NOT stored - never sent to LLM
```

### Scenario 2: Override Clause
**Before:**
```
❌ Conflict detected: "Payment Net 30" vs "Notwithstanding 3.1, Net 60"
   Stored as conflict
```

**After:**
```
✅ Sent to LLM → Returns "VALID_OVERRIDE"
   NOT stored (only TRUE_CONFLICT/AMBIGUITY stored)
```

### Scenario 3: Jurisdiction Mismatch
**Before:**
```
✅ Conflict detected with severity based on confidence
   If confidence=0.88 → severity=MEDIUM
```

**After:**
```
✅ TRUE_CONFLICT with conflict_type=JurisdictionMismatch
   severity=CRITICAL (always, regardless of confidence)
```

## Code Integration

### Using Classification
```python
from app.services.clause_classifier import classify_clause_function

# Automatic classification
for clause in clauses:
    clause.analysis_results["clause_function"] = classify_clause_function(
        clause.text,
        clause.heading
    )
```

### Checking Compatibility
```python
from app.services.clause_classifier import is_pair_allowed

# Check if two clauses can be compared
if is_pair_allowed(func1, func2):
    # Compare these clauses
    pass
```

### Override Bypass
```python
# Tier1 override pairs bypass compatibility
is_tier1 = (left_id, right_id) in tier1_pairs
if is_pair_allowed(func1, func2, is_override_or_xref=is_tier1):
    # Allowed
    pass
```

## Testing Commands

```bash
# Test classification
pytest tests/test_conflict_detection_refined.py::TestClauseClassification -v

# Test compatibility
pytest tests/test_conflict_detection_refined.py::TestCompatibilityGate -v

# Test scenarios
pytest tests/test_conflict_detection_refined.py::TestConflictDetectionScenarios -v

# All tests
pytest tests/test_conflict_detection_refined.py -v
```

## Monitoring Logs

Look for these new log messages:

```
🏷️  Classifying clause functions...
🚦 After compatibility filtering: 150 pairs (filtered 87 incompatible)
✅ Batch 1/3: 2 conflicts stored (filtered 3 non-conflicts)
```

## Common Questions

**Q: Will this affect existing conflicts in the database?**  
A: No, existing conflicts remain unchanged. New detection runs use the new logic.

**Q: Do I need to run migrations?**  
A: No, all fields already exist. We're just populating them now.

**Q: What if classification is wrong?**  
A: Classification is deterministic (keyword-based). You can adjust rules in `clause_classifier.py`.

**Q: Can I disable compatibility filtering?**  
A: Yes, set `is_override_or_xref=True` in `is_pair_allowed()` to bypass.

**Q: Why are fewer conflicts being stored?**  
A: By design! We're filtering out false positives (VALID_OVERRIDE, NOT_RELATED, etc.).

## Files to Review

1. `/backend/app/services/clause_classifier.py` - Classification logic
2. `/backend/app/services/enhanced_conflict_detector.py` - Enhanced detector
3. `/backend/app/services/conflict_detector.py` - Standard detector
4. `/backend/tests/test_conflict_detection_refined.py` - Test suite

## Rollback

If needed, revert these 3 files:
```bash
git checkout backend/app/services/enhanced_conflict_detector.py
git checkout backend/app/services/conflict_detector.py
rm backend/app/services/clause_classifier.py
```

No database changes to undo.

---

**Implementation:** Complete  
**Risk Level:** Low (additive changes only)  
**Breaking Changes:** None (API unchanged)
