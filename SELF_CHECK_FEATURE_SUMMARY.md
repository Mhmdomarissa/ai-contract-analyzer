# N→N Feature Update: Self-Consistency Checks + Dual Prompts

## ✅ Implementation Complete

### What Changed

The N→N All-vs-All comparison feature now includes **self-consistency checks** alongside pair comparisons, with two separate prompts for each type.

### New Comparison Formula

**Before**: N × (N-1) / 2 pair comparisons only  
**After**: **N × (N+1) / 2** total comparisons

Breaking down:
- **N self-checks**: Each clause checked against itself for internal consistency
- **N × (N-1) / 2 pair-checks**: Each unique pair compared

#### Examples:
| Clauses | Self-Checks | Pair-Checks | Total | Time Est. |
|---------|-------------|-------------|-------|-----------|
| 2 | 2 | 1 | **3** | ~7.5s |
| 3 | 3 | 3 | **6** | ~15s |
| 5 | 5 | 10 | **15** | ~37.5s |
| 10 | 10 | 45 | **55** | ~2.3 min |
| 20 | 20 | 190 | **210** | ~8.75 min |

---

## Two Default Prompts

### Prompt A: Self-Consistency Check
**Used for**: Clause vs itself (i == j)

```
You are a legal expert and contract review machine. Here is a clause from a contract. Your job is to check the language and terms of the clause and see if any of the statements therein meet the following conditions;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict"
```

### Prompt B: Pair Comparison
**Used for**: Clause vs another clause (i != j)

```
You are a legal expert and contract review machine. Here are two clauses from the same contract. Your job is to check the language and terms of both clauses and check for the following;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict"
```

---

## Technical Changes

### Backend (`backend/app/api/v1/endpoints/all_vs_all_compare.py`)

✅ **Request Model**: Now accepts two prompts
```python
class AllVsAllComparisonRequest(BaseModel):
    clauses: List[str]
    pair_prompt: str  # For clause vs clause
    self_prompt: str  # For clause vs itself
```

✅ **Response Model**: Includes self-check indicator
```python
class PairComparisonResult(BaseModel):
    clause_i_index: int
    clause_j_index: int
    is_self_check: bool  # NEW!
    conflict: bool
    explanation: str
    severity: str
    performance: Dict[str, Any]
```

✅ **Pair Generation**: Now includes self-pairs
```python
def _generate_all_pairs(n: int) -> List[Tuple[int, int]]:
    """Generates (0,0), (1,1), ..., (n-1,n-1), (0,1), (0,2), ..."""
    pairs = []
    # Self-checks first
    for i in range(n):
        pairs.append((i, i))
    # Pair-checks
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((i, j))
    return pairs
```

✅ **Comparison Logic**: Uses appropriate prompt based on type
```python
async def _compare_clause_pair(..., is_self_check: bool = False):
    if is_self_check:
        # Use self_prompt, single clause in prompt
    else:
        # Use pair_prompt, two clauses in prompt
```

### Frontend

#### Redux Slice (`frontend/src/features/allVsAllComparison/allVsAllComparisonSlice.ts`)

✅ **State**: Now stores both prompts
```typescript
export interface AllVsAllComparisonState {
  clauses: string[];
  pairPrompt: string;  // NEW!
  selfPrompt: string;  // NEW!
  results: PairComparisonResult[];
  isComparing: boolean;
  totalComparisons: number;
  completedCount: number;
  error: string | null;
  clauseCount: number;
}
```

✅ **Actions**: Separate setters for each prompt
```typescript
setPairPrompt(state, action)
setSelfPrompt(state, action)
resetPairPrompt(state)
resetSelfPrompt(state)
```

✅ **Result Interface**: Includes is_self_check
```typescript
export interface PairComparisonResult {
  clause_i_index: number;
  clause_j_index: number;
  is_self_check: boolean;  // NEW!
  conflict: boolean;
  explanation: string;
  severity: string;
  performance: { ... }
}
```

#### UI Component (`frontend/src/components/AllVsAllComparison.tsx`)

✅ **Dual Prompt Editors**: Side-by-side layout
- Left: "Pair Comparison Prompt" - For clause vs clause
- Right: "Self-Check Prompt" - For clause vs itself
- Each has its own "Reset to Default" button

✅ **Updated Comparison Count Display**:
```
Total comparisons: 3 self + 3 pair = 6
```

✅ **Result Cards**: Show self-check badge
```tsx
{result.is_self_check ? (
  <>Clause {result.clause_i_index + 1} (Self-Check)</>
) : (
  <>Clause {result.clause_i_index + 1} ↔ Clause {result.clause_j_index + 1}</>
)}
{result.is_self_check && (
  <Badge variant="secondary">Self-Consistency</Badge>
)}
```

✅ **API Request**: Sends both prompts
```typescript
body: JSON.stringify({
  clauses: validClauses,
  pair_prompt: pairPrompt,
  self_prompt: selfPrompt,
})
```

---

## How It Works

### Comparison Order

For 3 clauses, the system processes:

1. **Clause 0 (Self-Check)** - Internal consistency check
2. **Clause 1 (Self-Check)** - Internal consistency check
3. **Clause 2 (Self-Check)** - Internal consistency check
4. **Clause 0 ↔ Clause 1** - Pair comparison
5. **Clause 0 ↔ Clause 2** - Pair comparison
6. **Clause 1 ↔ Clause 2** - Pair comparison

**Total**: 6 comparisons (3 self + 3 pair)

### LLM Prompt Construction

**Self-Check Example**:
```
[Self-Consistency Prompt]

**Clause 1:**
Payment must be made within 30 days of invoice date.

Please analyze this clause according to the instructions above.
```

**Pair-Check Example**:
```
[Pair Comparison Prompt]

**Clause 1:**
Payment must be made within 30 days of invoice date.

**Clause 2:**
Payment is due within 60 days from receipt of goods.

Please analyze these two clauses according to the instructions above.
```

---

## Testing

### Verified Working

✅ Backend API accepts `pair_prompt` and `self_prompt`  
✅ Generates N×(N+1)/2 total comparisons  
✅ Self-checks executed with self-prompt  
✅ Pair-checks executed with pair-prompt  
✅ Results include `is_self_check` field  
✅ Frontend displays two prompt editors  
✅ UI shows self-check badge on results  
✅ All linting passed  
✅ Containers rebuilt and deployed  

### Test Results (2 clauses)

```
Comparison 1: Clause 0 (Self-Check) ✅
  - is_self_check: true
  - Used self_prompt
  - No conflicts found

Comparison 2: Clause 1 (Self-Check) ✅
  - is_self_check: true
  - Used self_prompt
  - No conflicts found

Comparison 3: Clause 0 ↔ Clause 1 ✅
  - is_self_check: false
  - Used pair_prompt
  - No conflicts found

Total: 3 comparisons in ~15 seconds
```

---

## Usage Guide

### 1. Add Your Clauses (2-50)

Each clause will be:
- Checked against itself (self-consistency)
- Compared with all other clauses (pair comparison)

### 2. Customize Prompts (Optional)

**Pair Comparison Prompt**: How to compare two different clauses  
**Self-Check Prompt**: How to check a clause for internal consistency

Both have "Reset to Default" buttons.

### 3. Click "Compare All"

Watch as results stream in real-time:
- Self-checks appear first (one per clause)
- Pair comparisons follow (all unique pairs)

### 4. Review Results

Each result shows:
- **Badge**: "Self-Consistency" for self-checks
- **Title**: "Clause N (Self-Check)" or "Clause N ↔ Clause M"
- **Conflict Status**: Yes/No with severity
- **Explanation**: LLM analysis
- **Performance**: Time and tokens/sec

---

## Use Cases

### Self-Consistency Checks Catch:
- Internal contradictions within a clause
- Ambiguous or conflicting terms in the same sentence
- Undefined references or circular logic
- Inconsistent timelines or amounts

### Pair Comparisons Catch:
- Conflicts between different clauses
- Contradictory obligations across sections
- Incompatible terms for the same aspect
- Legal ambiguity when clauses interact

---

## Performance

### Comparison Times (Sequential Processing)

| Clauses | Self-Checks | Pair-Checks | Total Comparisons | Est. Time @ 2.5s each |
|---------|-------------|-------------|-------------------|------------------------|
| 2 | 2 | 1 | 3 | 7.5 seconds |
| 3 | 3 | 3 | 6 | 15 seconds |
| 5 | 5 | 10 | 15 | 37.5 seconds |
| 10 | 10 | 45 | 55 | 2 minutes 17 seconds |
| 20 | 20 | 190 | 210 | 8 minutes 45 seconds |
| 50 | 50 | 1,225 | 1,275 | 53 minutes 7 seconds |

### Resource Usage

- **LLM Server**: 19GB RAM per inference (sequential = constant peak)
- **Backend**: Minimal (streaming, no buffering)
- **Frontend**: 5-10MB for typical result sets

---

## API Changes

### Request Format

**Before**:
```json
{
  "clauses": ["clause 1", "clause 2"],
  "prompt": "single prompt for all"
}
```

**After**:
```json
{
  "clauses": ["clause 1", "clause 2"],
  "pair_prompt": "prompt for clause vs clause",
  "self_prompt": "prompt for clause vs itself"
}
```

### Response Format

**Added Field**:
```json
{
  "type": "result",
  "data": {
    "clause_i_index": 0,
    "clause_j_index": 0,
    "is_self_check": true,  // NEW!
    "conflict": false,
    "explanation": "...",
    "severity": "Unknown",
    "performance": { ... }
  }
}
```

---

## Deployment

**Status**: ✅ **DEPLOYED AND LIVE**

**Access**: http://localhost/

**Tab**: "All vs All (N → N)"

**Containers**: All 6 containers running

**Date**: January 6, 2026

---

## Files Modified

### Backend
- ✅ `backend/app/api/v1/endpoints/all_vs_all_compare.py` (61 lines changed)

### Frontend
- ✅ `frontend/src/features/allVsAllComparison/allVsAllComparisonSlice.ts` (80 lines changed)
- ✅ `frontend/src/components/AllVsAllComparison.tsx` (120 lines changed)

### Documentation
- ✅ `SELF_CHECK_FEATURE_SUMMARY.md` (this file)

---

## Benefits

### 1. Comprehensive Analysis
- Catches internal clause issues AND inter-clause conflicts
- No need for separate self-consistency tool

### 2. Flexible Prompts
- Tailor analysis style for each check type
- Different detection strategies for self vs pair

### 3. Clear Attribution
- Easy to see which results are self-checks
- Badge and label distinguish check type

### 4. Efficient Processing
- Both check types in single operation
- Streaming results for immediate visibility

---

## Next Steps

### For Users:
1. Open http://localhost/
2. Click "All vs All (N → N)" tab
3. Add your clauses
4. Review/edit both prompts (optional)
5. Click "Compare All"
6. Watch self-checks appear first, then pairs!

### Future Enhancements:
- Filter results by type (self-check vs pair-check)
- Statistics: "X self-conflicts, Y pair-conflicts"
- Export self-checks separately from pairs
- Batch processing: "Self-checks first, pairs later"

---

**Version**: 2.0  
**Feature**: Self-Consistency Checks + Dual Prompts  
**Status**: ✅ Live  
**Deployment**: January 6, 2026
