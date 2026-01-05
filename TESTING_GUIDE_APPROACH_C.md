# Testing Guide: Approach C Conflict Detection

## Overview
This guide will help you test the new **Approach C: Claim-Based Conflict Detection** system through the UI. The new system uses a 3-phase pipeline that's faster, more accurate, and scalable.

## What Changed?

### Old System (Problems):
- ❌ Sent all 540 clauses to LLM in one massive prompt (108,000 characters)
- ❌ LLM got overwhelmed and produced false positives
- ❌ No filtering of non-substantive clauses (page numbers, headers, TOC)
- ❌ Detected only 2 conflicts (both false positives)

### New System (Approach C):
- ✅ **Phase 1**: Extract structured claims from each clause (subject, action, modality, value)
- ✅ **Phase 2**: Use deterministic rules to find conflict candidates (reduces 145,530 pairs to ~500)
- ✅ **Phase 3**: LLM validates only the candidates (focused, accurate)
- ✅ Expected: 10-30 real conflicts with 90%+ accuracy
- ✅ Speed: ~15 seconds (vs 120+ seconds before)

---

## Prerequisites

### Containers Running:
```bash
cd /home/ec2-user/apps/ai-contract-analyzer
docker compose up -d
```

### Verify Services:
1. **Frontend**: http://3.28.252.206 (or your server IP)
2. **API**: http://3.28.252.206/api/docs
3. **Ollama**: http://51.112.105.60:11434 (remote LLM service)

---

## Test Scenario 1: Upload New Contract

### Steps:
1. **Open the UI** in your browser: `http://3.28.252.206`

2. **Upload a Contract**:
   - Click "Upload Contract" or similar button
   - Select a PDF contract (ideally 10-50 pages with multiple clauses)
   - Wait for extraction to complete

3. **What to Check**:
   - ✅ Extraction completes successfully
   - ✅ Clauses are displayed with numbering
   - ✅ Bilingual clauses are separated (if applicable)
   - ✅ Hierarchy is correct (parent/child clauses)

4. **Expected Result**:
   - Contract uploaded successfully
   - All clauses extracted
   - Ready for conflict detection

### What to Report:
```
✅/❌ Contract upload successful
✅/❌ Extraction completed
Number of clauses extracted: ___
Time taken: ___ seconds
Any errors?: ___
```

---

## Test Scenario 2: Run Conflict Detection (Main Test)

### Steps:
1. **Navigate to Conflict Detection**:
   - After contract is uploaded, look for "Detect Conflicts" or "Analyze Conflicts" button
   - Click it to start the analysis

2. **What to Monitor**:
   - Progress indicator (if available)
   - Time taken (should be 10-20 seconds for typical contract)
   - Any error messages

3. **What to Check in Results**:

   **A. Number of Conflicts Found**:
   - Should find between 10-30 conflicts (not 0, not 100+)
   - Each conflict should have:
     - Left clause number
     - Right clause number
     - Conflict type/reason
     - Confidence score (0.85-1.00)

   **B. Conflict Quality**:
   Look at 2-3 conflicts and verify they are REAL conflicts, such as:
   - ✅ Contradictory terms (e.g., "30 days" vs "60 days" for same payment)
   - ✅ Opposite obligations (e.g., "must notify" vs "shall not notify")
   - ✅ Jurisdiction conflicts (e.g., "UAE courts" vs "UK courts")
   - ✅ Override clauses (e.g., Schedule overrides main clause)
   
   NOT false positives like:
   - ❌ Different clause numbers with same content
   - ❌ Page numbers vs clause numbers
   - ❌ Section headers vs content

   **C. Evidence**:
   - Each conflict should show quotes from both clauses
   - Confidence score should be displayed
   - Conflict type should be clear

4. **Expected Results**:
   ```
   Phase 1: Claims Extracted - ~750 claims from ~300 substantive clauses
   Phase 2: Candidates Found - ~200-500 candidate pairs
   Phase 3: Conflicts Validated - 10-30 real conflicts (confidence ≥ 0.85)
   
   Total Time: 10-20 seconds
   ```

### What to Report:
```
✅/❌ Conflict detection completed
Time taken: ___ seconds
Number of conflicts found: ___
Number of claims extracted: ___ (check backend logs)
Number of candidates: ___ (check backend logs)

Sample Conflict 1:
- Clause A: ___
- Clause B: ___
- Reason: ___
- Confidence: ___
- Is it a REAL conflict?: Yes/No

Sample Conflict 2:
- Clause A: ___
- Clause B: ___
- Reason: ___
- Confidence: ___
- Is it a REAL conflict?: Yes/No

Any errors?: ___
```

---

## Test Scenario 3: Review Conflict Details

### Steps:
1. **Click on a Conflict**:
   - Select one of the detected conflicts
   - View detailed information

2. **What to Check**:
   - ✅ Both clause texts are displayed correctly
   - ✅ Conflict explanation makes sense
   - ✅ Highlighted text shows the conflicting parts
   - ✅ Confidence score is reasonable (0.85-1.00)
   - ✅ Source quotes/evidence are shown

3. **Expected Result**:
   - Clear explanation of why clauses conflict
   - Visual highlighting of conflicting terms
   - Option to mark as resolved or false positive

### What to Report:
```
✅/❌ Conflict details displayed correctly
✅/❌ Explanation is clear and accurate
✅/❌ Text highlighting works
✅/❌ Can interact with conflict (mark resolved, etc.)
```

---

## Test Scenario 4: Re-run Analysis (Optional)

### Steps:
1. **Re-run Conflict Detection** on the same contract
2. **What to Check**:
   - Should be faster (claims already in database)
   - Should find same conflicts
   - No duplicate conflicts created

### What to Report:
```
✅/❌ Re-run completed
Time taken: ___ seconds
Same conflicts found?: Yes/No
Any duplicates?: Yes/No
```

---

## Test Scenario 5: Test with Known Contract (Underwriter Agreement)

If you have the "underwriter agreement.pdf" that we tested before:

### Steps:
1. **Upload the underwriter agreement** (if not already uploaded)
2. **Run conflict detection**
3. **Compare Results**:

   **Old System (Before)**:
   - Found 2 conflicts (both false positives)
   - Clause "0.03" vs "4.5" (page number vs clause)
   - SCHEDULE 8 vs "6.3" (appendix vs wrong content)

   **New System (Expected)**:
   - Should find 10-30 REAL conflicts
   - Examples:
     - Payment terms differences
     - Termination conditions conflicts
     - Jurisdiction contradictions
     - Override clauses

### What to Report:
```
Number of conflicts found: ___
Are they REAL conflicts?: Yes/No
Examples of conflicts found:
1. ___
2. ___
3. ___

Any false positives?: Yes/No
If yes, describe: ___
```

---

## How to Check Backend Logs (For Technical Details)

If you want to see detailed information:

```bash
# Check API logs
docker compose logs -f api --tail=100

# Check claims in database
docker compose exec -T db psql -U contract_admin -d contracts -c "
  SELECT COUNT(*) as total_claims, 
         COUNT(DISTINCT topic) as topics,
         COUNT(CASE WHEN value_type != 'NONE' THEN 1 END) as claims_with_values
  FROM claims;
"

# Check conflicts in database
docker compose exec -T db psql -U contract_admin -d contracts -c "
  SELECT COUNT(*) as total_conflicts,
         AVG(confidence) as avg_confidence,
         MIN(confidence) as min_confidence,
         MAX(confidence) as max_confidence
  FROM conflicts
  WHERE confidence IS NOT NULL;
"
```

---

## Success Criteria

The test is successful if:

✅ **Performance**: Conflict detection completes in 10-20 seconds (not 2+ minutes)

✅ **Accuracy**: Finds 10-30 conflicts (not 0, not 100+)

✅ **Quality**: At least 80% of conflicts are REAL conflicts (not false positives)

✅ **Confidence**: All conflicts have confidence ≥ 0.85

✅ **Evidence**: Each conflict shows clear evidence and explanation

✅ **Stability**: No crashes, no errors, can re-run multiple times

---

## Common Issues and Solutions

### Issue: "No conflicts found"
**Check**:
- Are claims being extracted? (Check database)
- Is Ollama reachable? (Test: `curl http://51.112.105.60:11434/api/tags`)
- Any errors in API logs?

### Issue: "Too many conflicts (100+)"
**Possible Cause**: Confidence threshold too low or rules too broad
**Check**: Conflict confidence scores - should all be ≥ 0.85

### Issue: "All conflicts are false positives"
**Possible Cause**: Extraction or filtering issues
**Check**: Sample claims in database - should capture substantive obligations

### Issue: "Process takes too long (>60 seconds)"
**Possible Cause**: Network latency to remote Ollama or too many LLM calls
**Check**: 
- Is Phase 2 filtering working? (Should reduce to ~500 candidates)
- Network latency to 51.112.105.60?

---

## Reporting Template

Please provide this information after testing:

```markdown
## Test Results - Approach C Conflict Detection

**Date**: ___
**Contract**: ___ (name/description)
**Contract Size**: ___ pages, ___ clauses

### Performance
- Upload time: ___ seconds
- Extraction time: ___ seconds
- Conflict detection time: ___ seconds
- Total time: ___ seconds

### Results
- Claims extracted: ___
- Conflict candidates: ___
- Conflicts found: ___
- Average confidence: ___

### Quality Assessment
Total conflicts: ___
Real conflicts: ___ (___%)
False positives: ___ (___%)

### Sample Conflicts
1. Clause ___ vs Clause ___: ___
   Real conflict?: Yes/No
   
2. Clause ___ vs Clause ___: ___
   Real conflict?: Yes/No
   
3. Clause ___ vs Clause ___: ___
   Real conflict?: Yes/No

### Issues Encountered
- Issue 1: ___
- Issue 2: ___

### Overall Assessment
✅/❌ System works as expected
✅/❌ Performance improved
✅/❌ Accuracy improved
✅/❌ Ready for production

### Recommendations
___
```

---

## Next Steps After Testing

Based on your test results, we can:
1. **Adjust confidence threshold** if too many/few conflicts
2. **Refine extraction prompts** if claim quality is poor
3. **Tune conflict rules** if finding wrong types of conflicts
4. **Optimize performance** if speed is an issue
5. **Integrate with UI** for better user experience

Please run the tests and share your results!
