# All-vs-All Comparison (N → N) - Complete Guide

## Overview

The **All-vs-All Comparison** feature enables comprehensive clause conflict analysis by comparing every clause against every other clause in a single operation. This is ideal for detecting potential conflicts within a contract or across multiple related agreements.

## Key Concepts

### Unique Pair Generation

For `N` clauses, the system generates **N × (N-1) / 2** unique comparisons:

| Clauses | Comparisons | Pairs Generated |
|---------|-------------|-----------------|
| 2       | 1           | (0,1) |
| 3       | 3           | (0,1), (0,2), (1,2) |
| 4       | 6           | (0,1), (0,2), (0,3), (1,2), (1,3), (2,3) |
| 5       | 10          | All unique pairs where i < j |
| 10      | 45          | All unique pairs where i < j |
| 20      | 190         | All unique pairs where i < j |
| 50      | 1,225       | Maximum allowed |

**Important**: Only pairs where `i < j` are generated to avoid duplicate comparisons. The system never compares a clause with itself.

## Architecture

### Backend Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Client Submits N Clauses + Prompt                       │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Backend Generates Unique Pairs                          │
│    _generate_unique_pairs(n) → [(i,j) where i<j]           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Sequential Processing (Prevent GPU Overload)            │
│    for pair in pairs:                                       │
│        result = _compare_clause_pair(i, j)                  │
│        stream_result_via_sse(result)                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Client Receives Incremental Results                     │
│    SSE Event Types: 'result', 'status', 'complete'         │
└─────────────────────────────────────────────────────────────┘
```

### Processing Strategy

**Sequential Processing** (Not Parallel):
- Prevents GPU/RAM overload on LLM server
- Qwen2.5:32b requires ~19GB RAM per inference
- Sequential = predictable resource usage
- Parallel = potential OOM crashes

**Why Sequential is Better**:
```python
# Sequential: Peak memory = 19GB
for pair in pairs:
    result = llm.compare(pair)  # 19GB during call, releases after
    
# Parallel: Peak memory = 19GB × N concurrent calls = OOM risk
results = await asyncio.gather(*[llm.compare(p) for p in pairs])
```

### Server-Sent Events (SSE) Stream

The backend streams results as they complete:

```javascript
// Event Types
{
  type: 'result',
  data: {
    clause_i_index: 0,
    clause_j_index: 1,
    conflict: true,
    severity: 'High',
    explanation: '...',
    performance: { total_time: 2.5, tokens: 150, tokens_per_second: 60 }
  }
}

{
  type: 'status',
  data: {
    completed: 5,
    total: 10,
    message: 'Comparing clause 2 vs clause 3...'
  }
}

{
  type: 'complete',
  data: {
    total_comparisons: 10,
    conflicts_found: 3,
    total_time: 28.4
  }
}
```

## User Interface

### Dynamic Clause Input

```
┌────────────────────────────────────────┐
│ Clause 1 ↔ All others                 │
│ [Text input box]                       │
│                              [× Remove] │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Clause 2 ↔ All others                 │
│ [Text input box]                       │
│                              [× Remove] │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Clause 3 ↔ All others                 │
│ [Text input box]                       │
│                              [× Remove] │
└────────────────────────────────────────┘

[+ Add Clause] (Max 50)
```

### Real-Time Results Display

Results appear incrementally as comparisons complete:

```
┌─────────────────────────────────────────────────────┐
│ Results (3 / 10)                                    │
│ [3 Conflicts] [7 No Conflicts]                      │
├─────────────────────────────────────────────────────┤
│ Clause 1 ↔ Clause 2 | ⚠️ Conflict | High Severity  │
│ The payment terms in Clause 1 contradict...         │
│ ⏱️ 2.5s | ⚡ 60 tok/s                               │
├─────────────────────────────────────────────────────┤
│ Clause 1 ↔ Clause 3 | ✅ No Conflict                │
│ These clauses are compatible...                     │
│ ⏱️ 1.8s | ⚡ 75 tok/s                               │
├─────────────────────────────────────────────────────┤
│ Clause 2 ↔ Clause 3 | ⚠️ Conflict | Medium Severity│
│ Termination notice periods differ...                │
│ ⏱️ 2.2s | ⚡ 68 tok/s                               │
└─────────────────────────────────────────────────────┘
```

### Progress Tracking

```
Progress
[████████████████░░░░░░░░░░░░░░░░░░] 30%
Completed: 3 / 10
```

## API Endpoint

### Request

**POST** `/api/v1/compare/all-vs-all`

```json
{
  "clauses": [
    "Payment must be made within 30 days of invoice date.",
    "Payment is due within 60 days.",
    "Late fees apply after 45 days."
  ],
  "prompt": "Analyze if these clauses conflict with each other. Focus on payment terms, deadlines, and obligations."
}
```

**Constraints**:
- Minimum clauses: 2
- Maximum clauses: 50
- Empty clauses are automatically filtered out
- Prompt is optional (uses default if omitted)

### Response (SSE Stream)

```
data: {"type":"status","data":{"message":"Starting all-vs-all comparison for 3 clauses (3 pairs)"}}

data: {"type":"result","data":{"clause_i_index":0,"clause_j_index":1,"conflict":true,"severity":"High",...}}

data: {"type":"result","data":{"clause_i_index":0,"clause_j_index":2,"conflict":false,...}}

data: {"type":"result","data":{"clause_i_index":1,"clause_j_index":2,"conflict":true,"severity":"Medium",...}}

data: {"type":"complete","data":{"total_comparisons":3,"conflicts_found":2,"total_time":7.2}}
```

## Code Structure

### Backend

**File**: `backend/app/api/v1/endpoints/all_vs_all_compare.py`

```python
# Key Functions

def _generate_unique_pairs(n: int) -> List[Tuple[int, int]]:
    """Generate all unique clause pairs (i, j) where i < j"""
    return [(i, j) for i in range(n) for j in range(i+1, n)]

async def _compare_clause_pair(
    i: int, j: int, 
    clause_i: str, clause_j: str, 
    prompt: str
) -> ComparisonResult:
    """Compare a single pair of clauses via LLM"""
    # Build prompt, call LLM, parse response, track performance
    pass

async def _generate_all_vs_all_stream(
    clauses: List[str], 
    prompt: str
) -> AsyncGenerator[str, None]:
    """SSE generator for streaming results"""
    pairs = _generate_unique_pairs(len(clauses))
    for i, j in pairs:
        result = await _compare_clause_pair(i, j, ...)
        yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
    yield f"data: {json.dumps({'type': 'complete', ...})}\n\n"

@router.post("/all-vs-all", response_class=StreamingResponse)
async def compare_all_vs_all(request: CompareAllVsAllRequest):
    """Main endpoint"""
    return StreamingResponse(
        _generate_all_vs_all_stream(request.clauses, request.prompt),
        media_type="text/event-stream"
    )
```

### Frontend

**Redux Slice**: `frontend/src/features/allVsAllComparison/allVsAllComparisonSlice.ts`

```typescript
interface AllVsAllComparisonState {
  clauses: string[];              // User input clauses
  prompt: string;                 // Analysis prompt
  results: ComparisonResult[];    // Accumulated results
  isComparing: boolean;           // Comparison in progress
  totalComparisons: number;       // N*(N-1)/2
  completedCount: number;         // Progress tracking
  error: string | null;
}

// Key Actions
addClause(text)           // Add new clause input
removeClause(index)       // Remove clause
updateClause({index, value}) // Edit clause text
startComparison({totalComparisons, clauseCount})
addResult(result)         // New result from SSE
completeComparison()      // All done
```

**Component**: `frontend/src/components/AllVsAllComparison.tsx`

- Dynamic clause inputs with add/remove
- "Compare All" button
- Real-time SSE result streaming
- Progress bar and metrics
- Conflict highlighting with severity badges

## Usage Examples

### Example 1: Payment Terms Conflict

**Input**:
```
Clause 1: "Payment must be made within 30 days of invoice date."
Clause 2: "Payment is due within 60 days from receipt of goods."
Clause 3: "Late fees of 2% apply after 45 days."
```

**Comparisons**: 3 (pairs: 0-1, 0-2, 1-2)

**Expected Results**:
- **Clause 1 ↔ Clause 2**: ⚠️ Conflict - Different payment deadlines (30 vs 60 days)
- **Clause 1 ↔ Clause 3**: ⚠️ Conflict - Late fees apply before/after payment deadline
- **Clause 2 ↔ Clause 3**: ✅ No Conflict - 60-day deadline aligns with 45-day late fee threshold

### Example 2: Termination Notice Periods

**Input**:
```
Clause 1: "Either party may terminate with 90 days written notice."
Clause 2: "Termination requires 60 days notice to the other party."
Clause 3: "Notice must be provided via certified mail."
Clause 4: "Either party may terminate immediately for cause."
```

**Comparisons**: 6 (pairs: 0-1, 0-2, 0-3, 1-2, 1-3, 2-3)

**Expected Results**:
- **Clause 1 ↔ Clause 2**: ⚠️ High Conflict - Inconsistent notice periods (90 vs 60 days)
- **Clause 1 ↔ Clause 3**: ✅ No Conflict - Compatible (notice + delivery method)
- **Clause 1 ↔ Clause 4**: ⚠️ Medium Conflict - General termination vs immediate termination
- **Clause 2 ↔ Clause 3**: ✅ No Conflict - Compatible (notice + delivery method)
- **Clause 2 ↔ Clause 4**: ⚠️ Medium Conflict - Notice period vs immediate termination
- **Clause 3 ↔ Clause 4**: ✅ No Conflict - Delivery method doesn't conflict with immediate termination

### Example 3: Large-Scale Analysis (10 Clauses)

**Input**: 10 clauses from different sections of a contract

**Comparisons**: 45 (pairs: 0-1, 0-2, ..., 8-9)

**Processing Time**:
- Average per comparison: 2.5 seconds
- Total time: ~112 seconds (~2 minutes)
- Results streamed incrementally (user sees progress)

## Performance Characteristics

### Time Complexity

| Clauses | Comparisons | Est. Time (2.5s/comparison) |
|---------|-------------|------------------------------|
| 2       | 1           | 2.5 seconds |
| 5       | 10          | 25 seconds |
| 10      | 45          | 112 seconds (~2 min) |
| 20      | 190         | 475 seconds (~8 min) |
| 50      | 1,225       | 3,062 seconds (~51 min) |

**Note**: Times are estimates. Actual performance depends on:
- LLM server load
- Clause length (longer = more tokens = slower)
- Network latency
- Model keep-alive status (cold start adds ~90s first time)

### Resource Usage

**LLM Server (Qwen2.5:32b)**:
- RAM per inference: ~19GB
- Sequential processing: Peak RAM = 19GB (constant)
- Keep-alive: 30 minutes (stays warm between calls)

**Backend Server**:
- RAM: Minimal (streaming, no buffering)
- CPU: Low (I/O bound, waiting for LLM)
- Network: Sustained SSE connection

**Frontend**:
- RAM: Accumulates results in Redux store
- For 1,225 results (50 clauses): ~5-10MB
- No performance issues with large result sets

## Best Practices

### 1. Clause Preparation

✅ **Good**:
```
- Clear, complete sentences
- One concept per clause
- Specific terms and deadlines
- Consistent formatting
```

❌ **Bad**:
```
- Incomplete fragments: "Payment within..."
- Multiple concepts in one clause
- Vague terms: "Payment within a reasonable time"
- Mixed languages or unclear references
```

### 2. Prompt Engineering

**Default Prompt** (Conflict Detection):
```
Analyze if these two clauses conflict with each other.
A conflict exists when clauses contradict, create inconsistency, 
or cannot coexist without issues.

Return JSON:
{
  "conflict": true/false,
  "severity": "Low"/"Medium"/"High",
  "explanation": "Detailed explanation..."
}
```

**Custom Prompts**:
```
# Consistency Check
"Check if these clauses are consistent in terminology, deadlines, and obligations."

# Legal Compliance
"Identify if these clauses comply with [regulation] and highlight any conflicts."

# Risk Assessment
"Assess legal risks if both clauses are enforced simultaneously."
```

### 3. Optimal Clause Count

| Clauses | Use Case | Comparison Time |
|---------|----------|-----------------|
| 2-5     | Quick check, single contract section | < 30 seconds |
| 5-10    | Contract review, related agreements | 1-2 minutes |
| 10-20   | Comprehensive analysis, multiple contracts | 5-10 minutes |
| 20+     | Enterprise-level, full contract suite | 10-50 minutes |

**Recommendation**: 
- For large contracts (50+ clauses), break into logical sections
- Compare sections individually (5-10 clauses each)
- Then compare section representatives if needed

### 4. Handling Long Running Comparisons

For 20+ clauses (190+ comparisons):

1. **Split into batches**: Compare related clauses first
2. **Use specific prompts**: Narrow focus to reduce LLM processing time
3. **Monitor progress**: Watch the progress bar and incremental results
4. **Keep browser tab active**: SSE connections may timeout if tab sleeps

### 5. Interpreting Results

**Conflict Severity Guide**:
- **High**: Direct contradiction, cannot coexist, requires immediate resolution
- **Medium**: Potential issues, may cause confusion, should be reviewed
- **Low**: Minor inconsistency, edge case scenario, informational

**False Positives**:
- LLM may flag stylistic differences as conflicts
- Review "Low" severity results manually
- Consider rephrasing clauses for clarity

## Troubleshooting

### Issue: "Comparison Timeout"

**Symptoms**: Comparison stops mid-way, no new results

**Causes**:
- LLM server overloaded
- Network interruption
- Individual comparison exceeds 5-minute timeout

**Solutions**:
1. Reduce clause count
2. Shorten clause text
3. Check LLM server status
4. Retry with fewer clauses

### Issue: "Inconsistent Results"

**Symptoms**: Same pair compared twice yields different results

**Causes**:
- LLM non-deterministic behavior (temperature > 0)
- Different prompt wording
- Model hallucination

**Solutions**:
1. Use consistent prompts
2. Review conflicting results manually
3. Consider using temperature=0 for deterministic results (backend config)

### Issue: "High Memory Usage in Browser"

**Symptoms**: Browser tab slows down with many results

**Causes**:
- Redux store accumulates large result arrays
- 1,000+ results (45+ clauses) = significant RAM

**Solutions**:
1. Limit to 20-30 clauses per session
2. Clear results before starting new comparison
3. Use "Clear All" button regularly

## Comparison with Other Features

| Feature | Comparison Count | Use Case | Processing Time |
|---------|------------------|----------|-----------------|
| **A vs B** | 1 | Quick single comparison | ~2.5 seconds |
| **1 → N Batch** | N | Compare source clause against N targets | N × 2.5 seconds |
| **N → N All-vs-All** | N × (N-1) / 2 | Comprehensive contract analysis | (N × (N-1) / 2) × 2.5 seconds |

**When to Use Each**:
- **A vs B**: Testing, quick checks, single clause validation
- **1 → N**: Compare new clause against existing contract clauses
- **N → N**: Full contract analysis, conflict matrix, comprehensive review

## Advanced Usage

### Scenario 1: Contract Merger Analysis

**Context**: Merging two contracts with 15 clauses each (30 total)

**Strategy**:
1. Run N→N on Contract A clauses (15 clauses = 105 comparisons)
2. Run N→N on Contract B clauses (15 clauses = 105 comparisons)
3. Run 1→N batch: Each Contract A clause vs all Contract B clauses (15 × 15 = 225 comparisons)
4. Total: 435 comparisons

**Alternative**: Run N→N on all 30 clauses (435 comparisons directly)

### Scenario 2: Contract Amendment Validation

**Context**: Adding 5 new clauses to existing 20-clause contract

**Strategy**:
1. First, use **1 → N Batch**: Each new clause vs existing 20 (5 × 20 = 100 comparisons)
2. Then, use **N → N**: Compare 5 new clauses among themselves (10 comparisons)
3. Total: 110 comparisons (faster than re-analyzing all 25)

### Scenario 3: Multi-Contract Suite Analysis

**Context**: 5 contracts with 10 clauses each (50 total)

**Strategy**:
1. **Per-contract analysis**: Run N→N on each contract (5 × 45 = 225 comparisons)
2. **Cross-contract analysis**: Select 2 key clauses per contract (10 total), run N→N (45 comparisons)
3. Total: 270 comparisons (vs 1,225 if comparing all 50 directly)

## API Integration Examples

### Python Client

```python
import requests
import json

def compare_all_clauses(clauses, prompt=None):
    url = "http://localhost:8000/api/v1/compare/all-vs-all"
    
    response = requests.post(
        url,
        json={"clauses": clauses, "prompt": prompt},
        stream=True
    )
    
    results = []
    for line in response.iter_lines():
        if line.startswith(b'data: '):
            data = json.loads(line[6:])
            if data['type'] == 'result':
                results.append(data['data'])
                print(f"✓ Clause {data['data']['clause_i_index']} ↔ {data['data']['clause_j_index']}")
            elif data['type'] == 'complete':
                print(f"Done! {data['data']['total_comparisons']} comparisons")
    
    return results

# Usage
clauses = [
    "Payment within 30 days.",
    "Payment within 60 days.",
    "Late fees after 45 days."
]

results = compare_all_clauses(clauses)
conflicts = [r for r in results if r['conflict']]
print(f"Found {len(conflicts)} conflicts")
```

### JavaScript/Node.js Client

```javascript
async function compareAllClauses(clauses, prompt) {
  const response = await fetch('http://localhost:8000/api/v1/compare/all-vs-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clauses, prompt })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const results = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'result') {
          results.push(data.data);
          console.log(`✓ Clause ${data.data.clause_i_index} ↔ ${data.data.clause_j_index}`);
        }
      }
    }
  }

  return results;
}

// Usage
const clauses = [
  "Payment within 30 days.",
  "Payment within 60 days.",
  "Late fees after 45 days."
];

const results = await compareAllClauses(clauses);
const conflicts = results.filter(r => r.conflict);
console.log(`Found ${conflicts.length} conflicts`);
```

## Future Enhancements

### Planned Features

1. **Parallel Processing (Optional)**
   - User toggle: Sequential (safe) vs Parallel (fast but risky)
   - Intelligent batching: Process 2-3 pairs concurrently
   - Resource monitoring: Auto-throttle if server overloaded

2. **Result Export**
   - Export to CSV, JSON, PDF
   - Conflict matrix visualization
   - Executive summary generation

3. **Smart Filtering**
   - Filter results by severity
   - Show only conflicts
   - Group by clause indices

4. **Conflict Graph Visualization**
   ```
   Clause 1 ──── ⚠️ ──── Clause 2
        │                    │
       ✅                   ⚠️
        │                    │
   Clause 3 ──── ✅ ──── Clause 4
   ```

5. **AI-Powered Suggestions**
   - Automated resolution suggestions
   - Clause rewording recommendations
   - Precedence rules for conflicting clauses

## Related Documentation

- [Dynamic Comparison Guide](./DYNAMIC_COMPARISON_GUIDE.md) - Overview of all comparison features
- [Batch Comparison](./BATCH_COMPARISON.md) - 1 → N comparison details
- [Architecture Overview](./COMPLETE_TECHNICAL_FLOW.md) - System architecture
- [API Reference](./API_REFERENCE.md) - Full API documentation

## Support

For issues, questions, or feature requests related to N→N comparison:
1. Check this guide first
2. Review [Troubleshooting](#troubleshooting) section
3. Check server logs: `docker logs backend`
4. Test with minimal clauses (2-3) to isolate issues

---

**Version**: 1.0  
**Last Updated**: 2024-01-XX  
**Compatibility**: Backend v1.0+, Frontend v1.0+
