# Migration, Performance, and Bilingual Testing Guide

## Table of Contents
1. [Migration Guide](#migration-guide)
2. [Performance Benchmarks](#performance-benchmarks)
3. [Bilingual Testing Guide](#bilingual-testing-guide)

---

## Migration Guide

### Upgrading to Bilingual Support

When upgrading to the version with bilingual clause separation support, you must run database migrations to add the new columns to the `clauses` table.

### Prerequisites
- Ensure you have a database backup before running migrations
- Verify that Alembic is installed and configured
- Ensure database connection is active

### Migration Steps

1. **Stop the application services** (if running):
   ```bash
   cd /home/ec2-user/apps/ai-contract-analyzer
   docker compose down
   ```

2. **Run the Alembic migration**:
   ```bash
   docker compose run --rm api alembic upgrade head
   ```

   Or if running locally:
   ```bash
   cd backend
   alembic upgrade head
   ```

3. **Verify the migration**:
   The migration adds three new columns to the `clauses` table:
   - `english_text` (TEXT, nullable): Separated English text from bilingual clauses
   - `arabic_text` (TEXT, nullable): Separated Arabic text from bilingual clauses
   - `is_bilingual` (BOOLEAN, default=False): Flag indicating if clause contains both languages

4. **Restart the application**:
   ```bash
   docker compose up -d
   ```

### Migration Details

**Migration File**: `alembic/versions/add_bilingual_separate_fields.py`

**What it does**:
- Adds `english_text` column to store separated English text
- Adds `arabic_text` column to store separated Arabic text
- Adds `is_bilingual` boolean flag to mark bilingual clauses
- Handles existing columns gracefully (checks before adding to avoid duplicates)

**Backward Compatibility**:
- Existing clauses will have `is_bilingual=False` by default
- `english_text` and `arabic_text` will be `NULL` for existing clauses
- The original `text` field remains unchanged, preserving existing data
- All existing functionality continues to work

### Rollback (if needed)

If you need to rollback the migration:
```bash
docker compose run --rm api alembic downgrade -1
```

**Warning**: Rolling back will remove the `english_text`, `arabic_text`, and `is_bilingual` columns. Any data stored in these columns will be lost.

---

## Performance Benchmarks

### Overview

This section documents the performance characteristics of the contract analysis system, including extraction speed, table processing overhead, and LLM analysis latency.

### Extraction Performance

#### Baseline Metrics (English-only PDFs)

| Document Type | Pages | Extraction Time | Clauses Extracted | Time per Clause |
|--------------|-------|----------------|-------------------|-----------------|
| Simple Contract | 5-10 | ~3-5 seconds | 15-25 | ~0.2s |
| Complex Contract | 20-30 | ~8-12 seconds | 40-60 | ~0.2s |
| Tabular Contract | 10-15 | ~12-18 seconds | 25-35 | ~0.5s |

#### Table Extraction Overhead

Table extraction adds processing time due to:
- **Camelot extraction**: ~2-4 seconds per table (high accuracy)
- **PDFPlumber fallback**: ~1-2 seconds per table (faster, good accuracy)
- **Bilingual separation**: ~0.1-0.3 seconds per clause

**Table Extraction Breakdown**:
- Simple table (5-10 rows): ~2-3 seconds
- Complex table (20+ rows, merged cells): ~4-6 seconds
- Multiple tables per page: Linear scaling

#### Bilingual Processing Overhead

Bilingual text separation adds minimal overhead:
- **Language detection**: ~0.01-0.05 seconds per clause
- **Text separation**: ~0.05-0.15 seconds per clause
- **Total overhead**: ~0.1-0.3 seconds per bilingual clause

**Impact on Overall Extraction**:
- English-only contracts: No overhead
- Bilingual contracts: ~10-15% increase in extraction time
- Tabular bilingual contracts: ~15-20% increase (due to table + bilingual processing)

### LLM Conflict Detection Performance

#### Analysis Latency

| Contract Size | Clauses | LLM Analysis Time | Time per Clause |
|--------------|---------|-------------------|-----------------|
| Small | 10-20 | ~15-25 seconds | ~1.2s |
| Medium | 30-50 | ~40-60 seconds | ~1.3s |
| Large | 60-100 | ~90-150 seconds | ~1.5s |

**Factors Affecting Performance**:
- **Model**: qwen2.5:32b (current model)
- **Context size**: All clauses sent in single request for contextual analysis
- **Response parsing**: JSON parsing adds ~0.5-1 second
- **Network latency**: If LLM is remote, add network overhead

#### Optimization Notes

- **Batch processing**: All clauses analyzed in one LLM call (more efficient than individual calls)
- **Contextual analysis**: Single request ensures full contract understanding
- **Caching**: Consider implementing clause caching for repeated analyses

### Performance Recommendations

1. **For Production**:
   - Use async processing for large contracts (>50 clauses)
   - Implement progress tracking for long-running extractions
   - Consider queue system (Celery) for batch processing

2. **For Development**:
   - Use smaller test contracts for faster iteration
   - Monitor Docker container resource usage
   - Check LLM service response times

3. **Scaling Considerations**:
   - Table extraction is CPU-intensive (consider dedicated workers)
   - LLM calls are I/O bound (can parallelize multiple contracts)
   - Database queries are optimized with eager loading

## Context Limit Handling for LLM

### When the Contract Fits
- **Single-shot**: If all clauses fit in the LLM context window, keep the current single-request flow. This gives the highest contextual accuracy and matches existing “short contract” behavior.

### When the Contract Exceeds Context
Use a deterministic two-pass strategy to preserve accuracy:

1. **Chunking Strategy**
   - Split clauses into ordered chunks (e.g., 40-60 clauses per chunk) with a small overlap window (e.g., last 2-3 clauses of the previous chunk) to retain boundary context.
   - Preserve the exact clause IDs in each chunk prompt. The LLM must return IDs exactly as sent.
   - For tabular clauses, keep the table-formatted text within the same chunk as the surrounding paragraph clauses.

2. **Per-Chunk Conflict Detection**
   - Run `identify_conflicts` per chunk.
   - Discard conflicts involving “Gap” clauses or self-references, as in the single-shot flow.

3. **Merge and De-duplicate**
   - Normalize clause pairs as sorted tuples `(min(id1,id2), max(id1,id2))`.
   - De-duplicate identical pairs; if severities differ, keep the highest severity and the most detailed description.

4. **Cross-Chunk Pass (Optional for Very Large Docs)**
   - Build a lightweight cross-chunk summary prompt: for each chunk, include only clause headings/short numbers plus any per-chunk conflicts.
   - Ask the LLM to surface conflicts that may span non-overlapping chunks (e.g., jurisdiction, term definitions, payment terms). Keep the same ID normalization rules.

5. **Quality Guardrails**
   - Reject/skip any conflict whose clause IDs are not present in the master clause list.
   - If a clause ID uses sub-numbering (e.g., “2.6”) or “Clause2” labels, normalize to the parent number as already done in `find_clause_id`.
   - Be conservative: if confidence is low, drop the conflict (matches single-shot behavior).

### Testing Large-Contract Handling
- **Baseline**: Run the same small/medium contract in single-shot and chunked mode; outputs should be functionally identical (same conflicts or empty list).
- **Large English-only PDF**: Confirm chunked flow produces conflicts and no ID mismatches.
- **Bilingual tabular PDF**: Verify chunked flow still separates languages, preserves table text in the prompt, and returns valid IDs.
- **Regression**: Re-run a known short contract to confirm no change in results versus the historic single-shot run.

### Benchmarking Your Environment

To measure performance in your environment:

```bash
# Time extraction for a test contract
time docker compose exec api python -c "
from app.services.parsers.pdf_parser import AdvancedPdfParser
import time
start = time.time()
parser = AdvancedPdfParser(extract_tables=True)
text = parser.parse('path/to/test.pdf')
tables = parser.get_extracted_tables()
print(f'Extraction time: {time.time() - start:.2f}s')
print(f'Tables found: {len(tables)}')
"
```

---

## Bilingual Testing Guide

### Overview

This guide covers testing procedures for bilingual (English-Arabic) contract processing, including extraction accuracy, RTL display verification, and conflict detection validation.

### Test Contract Types

#### 1. English-Only Contracts
- **Purpose**: Baseline testing, ensure no regression
- **Test Files**: Any standard English PDF contract
- **Expected Behavior**:
  - `is_bilingual = False`
  - `english_text = NULL` (original text in `text` field)
  - `arabic_text = NULL`
  - UI displays standard text (no language separation)

#### 2. Arabic-Only Contracts
- **Purpose**: Verify Arabic text handling
- **Test Files**: Arabic PDF contracts
- **Expected Behavior**:
  - `is_bilingual = False`
  - `english_text = NULL`
  - `arabic_text = NULL` (original text in `text` field)
  - UI displays Arabic text with RTL support

#### 3. Bilingual Contracts (Mixed Text)
- **Purpose**: Primary bilingual functionality test
- **Test Files**: Contracts with English and Arabic mixed in same clauses
- **Expected Behavior**:
  - `is_bilingual = True`
  - `english_text` contains only English text
  - `arabic_text` contains only Arabic text
  - `text` contains original mixed text (for LLM compatibility)
  - UI displays separated English and Arabic sections

#### 4. Bilingual Tabular Contracts
- **Purpose**: Test table extraction with bilingual content
- **Test Files**: Contracts with tables containing both languages
- **Example**: `docs/Contract_Template.pdf`
- **Expected Behavior**:
  - Tables extracted correctly
  - Bilingual text in table cells separated
  - Clauses linked to tables maintain bilingual separation
  - UI displays tables with proper language separation

### Testing Checklist

#### ✅ Extraction Testing

- [ ] **Upload English-only PDF**
  - Verify extraction completes successfully
  - Check database: `is_bilingual = False` for all clauses
  - Verify `text` field contains original content

- [ ] **Upload Arabic-only PDF**
  - Verify extraction completes successfully
  - Check database: `is_bilingual = False` for all clauses
  - Verify Arabic text preserved correctly

- [ ] **Upload Bilingual PDF (mixed text)**
  - Verify extraction completes successfully
  - Check database: `is_bilingual = True` for bilingual clauses
  - Verify `english_text` contains only English
  - Verify `arabic_text` contains only Arabic
  - Verify `text` contains original mixed text

- [ ] **Upload Bilingual Tabular PDF**
  - Verify table extraction works
  - Verify bilingual text in tables is separated
  - Verify clauses linked to tables maintain separation

#### ✅ Database Verification

```sql
-- Check bilingual clauses
SELECT 
    id, 
    clause_number, 
    is_bilingual,
    CASE 
        WHEN english_text IS NOT NULL THEN LENGTH(english_text)
        ELSE 0 
    END as english_length,
    CASE 
        WHEN arabic_text IS NOT NULL THEN LENGTH(arabic_text)
        ELSE 0 
    END as arabic_length,
    LENGTH(text) as original_length
FROM clauses
WHERE contract_version_id = '<your_contract_version_id>'
ORDER BY order_index;
```

**Expected Results**:
- Bilingual clauses: `is_bilingual = True`, both `english_text` and `arabic_text` populated
- Monolingual clauses: `is_bilingual = False`, one language field populated or NULL
- `text` field always contains original content

#### ✅ UI Display Testing

- [ ] **English-only Contract**
  - UI shows standard text display
  - No language labels visible
  - No color-coded sections

- [ ] **Arabic-only Contract**
  - UI shows Arabic text with RTL (right-to-left) direction
  - Text flows from right to left
  - No language labels (single language)

- [ ] **Bilingual Contract**
  - UI shows two separate sections:
    - **English section**: Blue background (`bg-blue-50`), LTR direction
    - **Arabic section**: Green background (`bg-green-50`), RTL direction
  - Each section has language label ("ENGLISH" / "ARABIC")
  - Text in each section is properly separated
  - No mixed text visible in individual sections

- [ ] **Bilingual Tabular Contract**
  - Tables display correctly
  - Table cells with bilingual content show separated sections
  - RTL works correctly for Arabic table content

#### ✅ RTL Display Verification

**What to Check**:
1. **Text Direction**:
   - Arabic text flows right-to-left
   - English text flows left-to-right
   - Mixed content properly separated

2. **Alignment**:
   - Arabic section: Right-aligned text
   - English section: Left-aligned text

3. **Punctuation**:
   - Arabic punctuation appears correctly
   - Numbers and dates display properly in both languages

4. **UI Elements**:
   - Language labels appear correctly
   - Color coding (blue/green) is visible
   - Borders and spacing are correct

**Browser Testing**:
- Test in Chrome, Firefox, Safari, Edge
- Verify RTL works in all browsers
- Check responsive design on mobile devices

#### ✅ Conflict Detection Testing

- [ ] **English-only Contract**
  - Conflict detection runs successfully
  - Conflicts reference correct clause IDs
  - Conflict descriptions are accurate
  - UI displays conflicts correctly

- [ ] **Bilingual Contract**
  - Conflict detection runs successfully
  - LLM receives full context (original `text` field with both languages)
  - Conflicts reference correct clause IDs
  - Conflict descriptions account for both languages
  - UI displays conflicting clauses with proper language separation

- [ ] **Tabular Bilingual Contract**
  - Conflict detection includes table content
  - Conflicts reference clauses with linked tables
  - Table data considered in conflict analysis

### Test Contract Files

**Location**: `docs/` directory

**Available Test Files**:
- `Contract_Template.pdf`: Bilingual tabular contract (primary test file)
- `COMMERCIAL LEASE AGREEMENT.pdf`: English-only contract
- Additional test files as needed

### Running Tests

#### Manual Testing via API

1. **Upload Contract**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/contracts/upload \
     -F "file=@docs/Contract_Template.pdf"
   ```

2. **Check Extraction Status**:
   ```bash
   curl http://localhost:8000/api/v1/contracts/{contract_id}
   ```

3. **List Clauses**:
   ```bash
   curl http://localhost:8000/api/v1/contracts/{contract_id}/clauses
   ```

4. **Verify Bilingual Separation**:
   ```bash
   curl http://localhost:8000/api/v1/contracts/{contract_id}/clauses | jq '.[] | select(.is_bilingual == true) | {clause_number, english_text, arabic_text}'
   ```

5. **Run Conflict Detection**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/contracts/{contract_id}/detect-conflicts
   ```

#### Automated Testing (Future)

Consider creating automated tests:
- Unit tests for `separate_bilingual_text()` function
- Integration tests for extraction pipeline
- E2E tests for UI display
- Performance benchmarks

### Known Issues and Limitations

1. **OCR Quality**: Scanned documents with poor OCR may have incorrect language detection
2. **Mixed Scripts**: Very dense mixed text (word-by-word alternation) may not separate perfectly
3. **Table Cells**: Complex table cells with multiple languages may require manual review
4. **Font Encoding**: Ensure PDFs use proper UTF-8 encoding for Arabic text

### Troubleshooting

#### Issue: Bilingual clauses not separating
- **Check**: Language detection logic in `separate_bilingual_text()`
- **Verify**: PDF text encoding is UTF-8
- **Solution**: Check extraction logs for language detection results

#### Issue: RTL not working in UI
- **Check**: `dir="rtl"` attribute on Arabic sections
- **Verify**: CSS supports RTL (Tailwind default supports it)
- **Solution**: Inspect element in browser DevTools

#### Issue: Conflicts not detected in bilingual contracts
- **Check**: LLM receives full `text` field (not separated)
- **Verify**: Clause IDs are correctly mapped
- **Solution**: Check backend logs for LLM request/response

### Reporting Test Results

When reporting test results, include:
- Contract type (English-only, Arabic-only, Bilingual, Tabular)
- Number of clauses extracted
- Number of bilingual clauses detected
- RTL display verification (pass/fail)
- Conflict detection accuracy
- Any issues encountered

---

## Summary

This guide provides comprehensive documentation for:
1. **Migration**: Step-by-step upgrade instructions with rollback procedures
2. **Performance**: Benchmarks and optimization recommendations
3. **Bilingual Testing**: Complete testing checklist and verification procedures

For questions or issues, refer to the main project documentation or contact the development team.

