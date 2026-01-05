# Dynamic Clause Comparison (A → N) - User Guide

**Updated:** December 31, 2025  
**Feature Status:** ✅ Production Ready

---

## 🎯 Overview

The **Dynamic Clause Comparison** feature allows you to compare one reference clause (Clause A) against multiple comparison clauses independently. Each comparison is explicit, individual, and processed separately.

**Key Concept:** 
```
Clause A  ↔  Clause 1  (separate analysis)
Clause A  ↔  Clause 2  (separate analysis)
Clause A  ↔  Clause 3  (separate analysis)
...
Clause A  ↔  Clause N  (separate analysis)
```

---

## 📐 UI Design

### **Layout Structure**

```
┌─────────────────────────────────────────────────────────┐
│  🎯 Dynamic Clause Comparison (A → N)                   │
│  Compare Clause A against multiple clauses              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  📌 [A] Reference Clause                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │ This clause will be compared against each       │    │
│  │ clause below independently...                   │    │
│  └─────────────────────────────────────────────────┘    │
│  Characters: 123                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  📋 Comparison Clauses           [+ Add Clause] Button  │
│  Each clause compared independently with Clause A       │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │ [1] → A ↔ 1  [Textarea: Enter clause 1]   │  [X]    │
│  └────────────────────────────────────────────┘         │
│  Characters: 89                                          │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │ [2] → A ↔ 2  [Textarea: Enter clause 2]   │  [X]    │
│  └────────────────────────────────────────────┘         │
│  Characters: 145                                         │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │ [3] → A ↔ 3  [Textarea: Enter clause 3]   │  [X]    │
│  └────────────────────────────────────────────┘         │
│  Characters: 67                                          │
│                                                          │
│  [+ Add Clause] adds more input boxes                   │
│  ─────────────────────────────────────────────          │
│  Total comparisons: 3                                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  📝 Analysis Prompt (Shared)                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Analyze these clauses for conflicts...         │    │
│  └─────────────────────────────────────────────────┘    │
│  [Reset to Default]                                     │
└─────────────────────────────────────────────────────────┘

[Start Batch Comparison]  [Clear All]
```

---

## 🔄 How It Works

### **1. Frontend UI Behavior**

#### **Clause A (Reference Box)**
- **Fixed position** at the top
- **Single textarea** for the reference clause
- This clause is used in ALL comparisons
- Shows character count
- Disabled during comparison

#### **Comparison Clause Boxes**
Each box represents **one independent comparison**:
- **Individual textarea** for that specific clause
- **Visual indicator** showing "A ↔ N" relationship
- **Index number** (1, 2, 3, ...)
- **Remove button [X]** to delete that clause
- **Character counter** for each clause
- Minimum: 1 box (always)
- Maximum: 100 boxes

#### **Add Clause Button**
- Appears at the top and within the comparison section
- Adds a new empty input box
- Each click = one new comparison clause
- Disabled when 100 clauses reached
- Disabled during comparison

#### **Remove Button [X]**
- Appears next to each comparison clause
- Removes that specific clause box
- Cannot remove last clause (minimum 1 required)
- Disabled during comparison

---

### **2. Backend Processing**

#### **API Call Structure**

```python
# Request to backend
POST /api/v1/compare/batch
{
  "source_clause": "Payment within 30 days",
  "target_clauses": [
    "Payment due in 60 days",
    "Invoice processed quarterly",  
    "Net 30 payment terms"
  ],
  "prompt": "Analyze if these clauses conflict..."
}

# Backend processes SEQUENTIALLY:
for i, target_clause in enumerate(target_clauses):
    # Call 1: A vs target[0]
    result_1 = llm_compare(
        clause_a="Payment within 30 days",
        clause_b="Payment due in 60 days",
        prompt=shared_prompt
    )
    # Stream result immediately
    yield result_1
    
    # Call 2: A vs target[1]
    result_2 = llm_compare(
        clause_a="Payment within 30 days",
        clause_b="Invoice processed quarterly",
        prompt=shared_prompt
    )
    yield result_2
    
    # Call 3: A vs target[2]
    # ... and so on
```

#### **Key Processing Details**

| Aspect | Behavior |
|--------|----------|
| **Order** | Sequential (one at a time) |
| **Independence** | Each comparison is separate |
| **API Calls** | N calls for N clauses (not N×N) |
| **Streaming** | Results sent immediately via SSE |
| **Prompt** | Same prompt used for all comparisons |
| **State** | Stateless (each call independent) |

---

### **3. Results Streaming**

#### **Server-Sent Events (SSE)**

Results are streamed back in real-time as each comparison completes:

```javascript
// Event 1: Status
{
  "type": "status",
  "message": "Starting comparison...",
  "total": 3
}

// Event 2: First result
{
  "type": "result",
  "data": {
    "index": 0,
    "conflict": true,
    "explanation": "These clauses conflict because...",
    "severity": "High",
    "performance": {
      "time_to_first_token": 0.15,
      "tokens_per_second": 45.2,
      "total_time": 0.28,
      "total_tokens": 89
    }
  }
}

// Event 3: Second result
{
  "type": "result",
  "data": {
    "index": 1,
    "conflict": false,
    ...
  }
}

// Event N+1: Completion
{
  "type": "complete",
  "message": "All comparisons completed"
}
```

---

## 📊 Performance

### **Timing**

| Scenario | Time |
|----------|------|
| **First comparison (cold start)** | 90-93 seconds |
| **Subsequent comparisons (warm)** | 0.2-0.3 seconds each |
| **10 clauses (warm)** | ~3-5 minutes total |
| **50 clauses (warm)** | ~15-25 minutes total |
| **100 clauses (warm)** | ~30-50 minutes total |

### **Why Sequential?**

The system processes comparisons **one at a time** (not in parallel) because:

1. **Resource Management** - Prevents overwhelming the LLM server
2. **Quality Assurance** - Maintains consistent response quality
3. **Memory Safety** - Qwen2.5:32b needs ~40GB RAM per request
4. **GPU Limitation** - Single GPU can't handle 100 parallel requests
5. **Reliability** - No crashes, predictable performance

---

## 💡 Usage Examples

### **Example 1: Payment Terms Analysis**

```
Clause A:
"Payment shall be made within 30 days of invoice date"

Comparison Clauses:
1. "Payment due within 60 days of receipt"
2. "Net 30 payment terms apply"
3. "Quarterly invoicing with 45-day terms"
4. "Payment within one month of billing"

Expected Results:
✅ Clause 1: CONFLICT (30 days vs 60 days)
✅ Clause 2: NO CONFLICT (same meaning)
✅ Clause 3: CONFLICT (quarterly vs 30 days)
✅ Clause 4: NO CONFLICT (one month ≈ 30 days)
```

### **Example 2: Jurisdiction Analysis**

```
Clause A:
"This agreement shall be governed by the laws of the UAE"

Comparison Clauses:
1. "UK law applies to all disputes"
2. "Dubai courts have exclusive jurisdiction"
3. "Arbitration in London under UK law"
4. "Subject to UAE Federal Law"

Expected Results:
✅ Clause 1: CONFLICT (UAE vs UK)
✅ Clause 2: NO CONFLICT (Dubai is in UAE)
✅ Clause 3: CONFLICT (UAE vs UK arbitration)
✅ Clause 4: NO CONFLICT (same jurisdiction)
```

---

## 🎯 Best Practices

### **1. Clause Selection**
- ✅ Compare clauses dealing with **similar topics**
- ✅ Look for **different values** (dates, percentages, amounts)
- ✅ Check for **contradictory obligations**
- ❌ Don't compare completely unrelated clauses

### **2. Prompt Engineering**
- ✅ Be specific about what constitutes a "conflict"
- ✅ Request severity levels (High/Medium/Low)
- ✅ Ask for clear explanations
- ✅ Include resolution suggestions

### **3. Performance Tips**
- ✅ Run warmup script first: `bash scripts/warmup_model.sh`
- ✅ Keep model warm with: `bash scripts/keep_model_alive.sh`
- ✅ Start with small batches (5-10 clauses) to test prompts
- ✅ Use clear, concise clause text (avoid entire sections)

### **4. Result Interpretation**
- ✅ Review **severity levels** to prioritize
- ✅ Read **explanations** for context
- ✅ Check **performance metrics** for quality issues
- ✅ Look for patterns across multiple conflicts

---

## 🔧 Technical Details

### **Frontend Component**
- **File:** `frontend/src/components/BatchComparison.tsx`
- **State Management:** Redux Toolkit (`batchComparisonSlice.ts`)
- **Styling:** Tailwind CSS with shadcn/ui components

### **Backend Endpoint**
- **File:** `backend/app/api/v1/endpoints/batch_compare.py`
- **Method:** POST
- **Path:** `/api/v1/compare/batch`
- **Response Type:** Server-Sent Events (SSE)

### **LLM Configuration**
- **Model:** Qwen2.5:32b (19GB)
- **Server:** 51.112.105.60:11434 (Ollama)
- **Keep-Alive:** 30 minutes
- **Temperature:** 0.7
- **Top-P:** 0.9

---

## 🐛 Troubleshooting

### **Issue: First comparison takes 90+ seconds**
**Solution:** This is expected (cold start). Run warmup script before batch:
```bash
bash scripts/warmup_model.sh
```

### **Issue: Results not streaming**
**Solution:** Check nginx configuration has buffering disabled:
```nginx
proxy_buffering off;
proxy_cache off;
X-Accel-Buffering: no;
```

### **Issue: "Cannot remove" error when clicking [X]**
**Solution:** You must keep at least 1 comparison clause. Add another clause first.

### **Issue: "Maximum Reached" when adding clauses**
**Solution:** Limit is 100 clauses per batch. Start a new comparison or remove unused clauses.

---

## 📚 Related Documentation

- [EXTENDED_TESTING_FEATURES.md](./EXTENDED_TESTING_FEATURES.md) - Complete feature overview
- [PERFORMANCE_ANALYSIS.md](./PERFORMANCE_ANALYSIS.md) - Cold start analysis and solutions
- [backend/app/api/v1/endpoints/batch_compare.py](./backend/app/api/v1/endpoints/batch_compare.py) - Backend implementation
- [frontend/src/components/BatchComparison.tsx](./frontend/src/components/BatchComparison.tsx) - Frontend implementation

---

## ✅ Summary

**What This Feature Does:**
- Provides explicit, dynamic input boxes for each comparison clause
- Makes the comparison logic visual and clear: A ↔ 1, A ↔ 2, A ↔ 3
- Processes each comparison independently with separate LLM calls
- Streams results in real-time as they complete
- Tracks performance metrics for each comparison

**What This Feature Does NOT Do:**
- ❌ Does not compare all clauses against all clauses (N×N)
- ❌ Does not batch multiple clauses into one LLM call
- ❌ Does not run comparisons in parallel
- ❌ Does not persist results to database (temporary testing only)

**Perfect For:**
- Testing conflict detection prompts
- Analyzing payment terms across contracts
- Checking jurisdiction consistency
- Identifying contradictory obligations
- Quick ad-hoc clause comparisons
