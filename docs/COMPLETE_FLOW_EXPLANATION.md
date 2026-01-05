# Complete Flow: From File Upload to Conflict Detection

A detailed and accurate explanation of how the AI Contract Analyzer processes documents.

---

## Overview

```
User Uploads File
      ↓
1. FILE UPLOAD & VALIDATION (Synchronous, ~5 sec)
      ↓
2. DOCUMENT PARSING - Text Extraction (Synchronous, ~2 sec)
      ↓
3. DATABASE STORAGE (Synchronous, ~1 sec)
      ↓
4. CLAUSE EXTRACTION (Celery Background Task, ~2-3 min)
   ├── REGEX-based extraction (HierarchicalClauseExtractor)
   ├── Post-processing filters
   └── Optional LLM validation
      ↓
5. CONFLICT DETECTION (Celery Background Task, ~5-25 min)
   ├── Candidate pair selection (keyword clustering)
   └── LLM validation with evidence
      ↓
Results Displayed to User
```

---

## PHASE 1: FILE UPLOAD & VALIDATION

**Endpoint:** `POST /api/v1/contracts/upload`  
**File:** `backend/app/api/v1/endpoints/contracts.py`

### What Happens:

```python
# 1. Validate filename exists
if not file.filename:
    raise HTTPException(400, "File name is required")

# 2. Validate file extension
file_ext = Path(file.filename).suffix.lower()
supported = ['.pdf', '.docx', '.doc', '.txt']
if file_ext not in supported:
    raise HTTPException(400, "Unsupported file type")

# 3. Save file to disk
upload_dir = Path("uploads")
file_path = upload_dir / file.filename
with file_path.open("wb") as buffer:
    shutil.copyfileobj(file.file, buffer)

# 4. Check file size (max 512 MB)
file_size_mb = file_path.stat().st_size / (1024 * 1024)
if file_size_mb > 512:
    file_path.unlink()
    raise HTTPException(413, "File too large")

# 5. Check encryption
if document_parser.is_encrypted(str(file_path)):
    file_path.unlink()
    raise HTTPException(400, "Encrypted files not supported")
```

---

## PHASE 2: DOCUMENT PARSING (Text Extraction)

**File:** `backend/app/services/document_parser.py`  
**Also:** `backend/app/services/parsers/pdf_parser.py`, `docx_parser.py`

### For PDF Files:

```python
# Uses PyMuPDF (fitz) for text extraction
from app.services.parsers.pdf_parser import AdvancedPdfParser

parser = AdvancedPdfParser(
    use_ocr=True,           # OCR for scanned pages
    layout_recognition=True, # Preserve document structure
    extract_tables=True      # Extract tables separately
)
text = parser.parse(file_path=file_path)
tables = parser.get_extracted_tables()
```

### For DOCX Files:

```python
# Uses python-docx
from app.services.parsers.docx_parser import AdvancedDocxParser

parser = AdvancedDocxParser(extract_tables=True)
text = parser.parse(file_path=file_path)
tables = parser.get_extracted_tables()
```

### Language Detection:

```python
# Detect Arabic characters (Unicode range \u0600-\u06FF)
has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
has_english = any(char.isascii() and char.isalpha() for char in text)

if has_arabic and has_english:
    language = 'bilingual'
elif has_arabic:
    language = 'arabic'
else:
    language = 'english'
```

---

## PHASE 3: DATABASE STORAGE

**File:** `backend/app/services/contracts.py`

### Tables Created:

```sql
-- 1. Main contract record
INSERT INTO contracts (id, title, description, status, created_at)
VALUES ('uuid', 'Contract Name', 'Uploaded: file.pdf', 'draft', NOW());

-- 2. Contract version (stores the actual content)
INSERT INTO contract_versions (
    id, contract_id, version_number, content, file_path,
    file_size, file_type, language, page_count, created_at
) VALUES (
    'uuid', 'contract_uuid', 1, 'full extracted text',
    '/uploads/file.pdf', 1024000, '.pdf', 'english', 30, NOW()
);
```

### Response to Frontend:

```json
{
    "id": "contract-uuid",
    "title": "Contract Name",
    "latest_version": {
        "id": "version-uuid",
        "version_number": 1,
        "content_preview": "First 500 characters...",
        "language": "english",
        "file_size": 1024000,
        "page_count": 30
    }
}
```

---

## PHASE 4: CLAUSE EXTRACTION (Background Task)

**Trigger:** User clicks "Extract Clauses" button  
**Endpoint:** `POST /api/v1/contracts/{contract_id}/extract-clauses`

### Step 4.1: Create Analysis Run & Queue Task

```python
# API creates tracking record and returns immediately
run = AnalysisRun(
    contract_version_id=version.id,
    type="CLAUSE_EXTRACTION",
    status="PENDING"
)
db.add(run)
db.commit()

# Queue Celery task
extract_clauses_task.delay(run.id)

# Return immediately (HTTP 202 Accepted)
return {"id": run.id, "status": "PENDING"}
```

### Step 4.2: Frontend Polls for Status

```typescript
// Poll every 3 seconds
const poll = setInterval(async () => {
    const response = await fetch(
        `/api/v1/contracts/${contractId}/extract-clauses/${runId}`
    );
    const job = await response.json();
    
    if (job.run.status === 'COMPLETED') {
        clearInterval(poll);
        displayClauses(job.clauses);
    } else if (job.run.status === 'FAILED') {
        clearInterval(poll);
        showError(job.run.error_message);
    }
}, 3000);
```

### Step 4.3: Celery Worker Processes (Background)

**File:** `backend/app/tasks/clause_extraction.py`

#### 4.3.1: Load Document Content

```python
@celery_app.task(name="app.tasks.extract_clauses")
def extract_clauses_task(run_id: str):
    db = SessionLocal()
    
    run = db.query(AnalysisRun).filter_by(id=run_id).first()
    run.status = "RUNNING"
    db.commit()
    
    # Get the document text
    version = db.query(ContractVersion).filter_by(
        id=run.contract_version_id
    ).first()
    text = document_parser.parse_document(version.file.storage_path)
```

#### 4.3.2: REGEX-Based Clause Extraction (NOT LLM!)

**File:** `backend/app/services/hierarchical_clause_extractor.py`

```python
# The extraction is REGEX-BASED, not LLM-based!
from app.services.hierarchical_clause_extractor import HierarchicalClauseExtractor

extractor = HierarchicalClauseExtractor()
clauses = extractor.extract_clauses(text)
```

**The HierarchicalClauseExtractor works in 8 phases:**

```
Phase 1: Detect Appendices/Schedules (REGEX)
    Pattern: r'(APPENDIX|ANNEX|SCHEDULE|EXHIBIT)\s+([A-Z0-9]+)'
    
Phase 2: Find All Clause Boundaries (REGEX)
    Patterns:
    - Numbered: r'(\d+)\)\s+([A-Z][A-Z\s]+)'  → "1) DEFINITIONS"
    - Decimal: r'(\d+\.\d+)\s+'               → "1.1", "4.2.3"
    - Lettered: r'\(([a-z])\)'                → "(a)", "(b)"
    
Phase 3: Extract Preamble (REGEX)
    Text before first numbered clause
    
Phase 4: Extract All Clauses (REGEX + Position Tracking)
    For each boundary found, extract text until next boundary
    
Phase 5: Build Hierarchy Tree (CODE LOGIC)
    Parent-child relationships:
    - "1" is parent of "1.1", "1.2"
    - "1.1" is parent of "1.1.1", "1.1.2"
    
Phase 6: Inherit Headings from Parents (CODE LOGIC)
    If clause 1 = "PAYMENT", then 1.1, 1.2 inherit "PAYMENT"
    
Phase 7: Detect Override Clauses (KEYWORD MATCHING)
    Keywords: "notwithstanding", "shall prevail", "supersede"
    
Phase 8: Validate Extraction Quality (CODE LOGIC)
    Check for missing clauses, gaps in numbering
```

**Example REGEX Patterns Used:**

```python
# Article headings: "1) DEFINITIONS", "6) FEES"
article_pattern = re.compile(
    r'(?:^|\n)\s*(\d+)\)\s+([A-Z][A-Z\s,&\-]+?)(?:\n|$)',
    re.MULTILINE
)

# Decimal numbered clauses: "1.1", "4.2.3"
decimal_pattern = re.compile(
    r'(?:^|\n)\s*(\d+(?:\.\d+)+)\s+',
    re.MULTILINE
)

# Lettered sub-clauses: "(a)", "(b)", "(c)"
lettered_pattern = re.compile(
    r'(?:^|\n)\s*\(([a-z])\)\s+',
    re.MULTILINE
)

# Appendix/Schedule headers
appendix_pattern = re.compile(
    r'^\s*(APPENDIX|ANNEX|SCHEDULE|EXHIBIT)\s+([A-Z0-9]+)',
    re.MULTILINE | re.IGNORECASE
)
```

#### 4.3.3: Post-Processing Filters

**File:** `backend/app/services/clause_filters.py`

```python
from app.services.clause_filters import ClauseFilter, ClauseSplitter

# Step 1: Remove non-substantive clauses
clause_filter = ClauseFilter(
    min_clause_words=10,    # Must have 10+ words
    min_clause_chars=40,    # Must have 40+ characters
    max_stub_chars=180      # Stubs < 180 chars removed
)

filter_result = clause_filter.filter_clauses(clauses)
# Removes: TOC entries, stubs, empty clauses

# Step 2: Split long clauses
clause_splitter = ClauseSplitter(
    max_clause_chars=2500,  # Split if > 2500 chars
    min_split_chars=100     # Each split must be 100+ chars
)

for clause in clauses:
    splits = clause_splitter.split_clause(clause)
```

#### 4.3.4: Optional LLM Validation

```python
# LLM validation is OPTIONAL (controlled by settings)
enable_validation = settings.ENABLE_CLAUSE_VALIDATION  # Default: True

if enable_validation:
    from app.services.clause_validator import ClauseValidator
    validator = ClauseValidator(llm_service)
    result = await validator.validate_clauses(clauses, text)
    
    # LLM checks:
    # - Are clause boundaries correct?
    # - Is any clause text truncated?
    # - Quality score for each clause
```

#### 4.3.5: Bilingual Text Separation

```python
# For each clause, separate English and Arabic
for clause_data in clauses:
    text = clause_data['text']
    
    # Separate by character detection
    english_text, arabic_text, is_bilingual = separate_bilingual_text(text)
    
    clause = Clause(
        text=text,                    # Original (both languages)
        arabic_text=arabic_text,      # Arabic portion only
        is_bilingual=is_bilingual,
        language='bilingual' if is_bilingual else 'en'
    )
```

#### 4.3.6: Store in Database

```python
# Delete existing clauses for this version (re-extraction)
session.query(Clause).filter(
    Clause.contract_version_id == version.id
).delete()

# Insert new clauses
for index, clause_data in enumerate(clauses):
    clause = Clause(
        contract_version_id=version.id,
        clause_number=clause_data['clause_number'],  # "1.1", "4.2"
        text=clause_data['text'],
        heading=clause_data.get('heading'),          # "PAYMENT"
        category=clause_data.get('category'),
        order_index=index,
        depth_level=clause_data.get('depth_level', 0),
        is_override_clause=clause_data.get('is_override_clause', False)
    )
    session.add(clause)

session.commit()

# Update run status
run.status = "COMPLETED"
run.finished_at = datetime.utcnow()
session.commit()
```

---

## PHASE 5: CONFLICT DETECTION (Background Task)

**Trigger:** User clicks "Detect Conflicts" button  
**Endpoint:** `POST /api/v1/contracts/{contract_id}/detect-conflicts`

### Step 5.1: Create Analysis Run & Queue Task

```python
# API creates tracking record and returns immediately
run = AnalysisRun(
    contract_version_id=version.id,
    type="CONFLICT_DETECTION",
    status="PENDING"
)
db.add(run)
db.commit()

# Queue Celery task
analyze_contract_conflicts.delay(str(run.id), strategy="fast_accurate")

# Return immediately (HTTP 202 Accepted)
return {"id": run.id, "status": "PENDING"}
```

### Step 5.2: Celery Worker Processes

**File:** `backend/app/tasks/conflict_analysis.py`  
**File:** `backend/app/services/fast_accurate_detector.py`

#### 5.2.1: Load All Clauses

```python
@celery_app.task(name="app.tasks.analyze_contract_conflicts")
def analyze_contract_conflicts(run_id: str, strategy: str = "fast_accurate"):
    db = SessionLocal()
    
    run = db.query(AnalysisRun).filter_by(id=run_id).first()
    run.status = "RUNNING"
    db.commit()
    
    # Load all extracted clauses
    clauses = db.query(Clause).filter(
        Clause.contract_version_id == run.contract_version_id
    ).order_by(Clause.order_index).all()
    
    # For Ver2: 155 clauses loaded
```

#### 5.2.2: Choose Detection Strategy

```python
if strategy == "fast_accurate":
    from app.services.fast_accurate_detector import FastAccurateDetector
    detector = FastAccurateDetector(db, ollama_url, model="qwen2.5:32b")
    
elif strategy == "accurate":
    from app.services.accurate_conflict_detector import AccurateConflictDetector
    detector = AccurateConflictDetector(db, ollama_url, model="qwen2.5:32b")

result = await detector.detect_conflicts(contract_version_id)
```

### Step 5.3: STAGE 1 - Smart Pair Selection (No LLM)

**File:** `backend/app/services/fast_accurate_detector.py`

```python
def _select_candidate_pairs(self, clauses: List[Clause]) -> Set[Tuple[str, str]]:
    """
    Select potential conflict pairs using keyword clustering.
    This is DETERMINISTIC - no LLM involved.
    """
    pairs = set()
    
    # METHOD 1: Override clause detection
    override_keywords = [
        "notwithstanding", "subject to", "except as",
        "unless otherwise", "in lieu of", "supersede"
    ]
    
    override_clauses = []
    for clause in clauses:
        if any(kw in clause.text.lower() for kw in override_keywords):
            override_clauses.append(clause)
    
    # Override clauses paired with ALL other clauses
    for override in override_clauses:
        for other in clauses:
            if override.id != other.id:
                pairs.add((str(override.id), str(other.id)))
    
    # METHOD 2: Keyword clustering
    keyword_groups = {
        'payment': ['payment', 'fee', 'invoice', 'cost', 'price'],
        'termination': ['terminate', 'cancellation', 'end', 'expiry'],
        'liability': ['liable', 'liability', 'indemnify', 'damage'],
        'subcontractor': ['subcontractor', 'subcontract', 'third party'],
        'warranty': ['warrant', 'guarantee', 'assurance'],
        'confidential': ['confidential', 'proprietary', 'secret'],
        'intellectual_property': ['intellectual property', 'ip', 'patent'],
        'force_majeure': ['force majeure', 'act of god'],
        'dispute': ['dispute', 'arbitration', 'mediation'],
        'governing_law': ['governing law', 'jurisdiction']
    }
    
    # Group clauses by keyword
    clusters = {name: [] for name in keyword_groups}
    for clause in clauses:
        text_lower = clause.text.lower()
        for name, keywords in keyword_groups.items():
            if any(kw in text_lower for kw in keywords):
                clusters[name].append(clause)
    
    # All pairs within same cluster
    for cluster_clauses in clusters.values():
        for i, c1 in enumerate(cluster_clauses):
            for c2 in cluster_clauses[i+1:]:
                pairs.add((str(c1.id), str(c2.id)))
    
    return pairs  # ~800-2000 pairs for 155 clauses
```

**Example Output:**
```
Override clauses found: 3
  - Clause 10: "notwithstanding the above..."
  
Keyword clusters:
  - payment: [Clause 10, 12, 15, 23] → 6 pairs
  - liability: [Clause 5, 8, 20, 31] → 6 pairs
  - subcontractor: [Clause 5, 7] → 1 pair
  - termination: [Clause 18, 22, 45] → 3 pairs
  
Total candidate pairs: 2,187 pairs
Total batches: 55 (40 pairs per batch)
```

### Step 5.4: STAGE 2 - LLM Validation with Evidence

```python
async def _validate_with_evidence(
    self, 
    clauses: List[Clause], 
    candidate_pairs: Set[Tuple[str, str]]
) -> List[Dict]:
    """
    Send pairs to LLM for validation.
    LLM must provide EXACT QUOTES as evidence.
    """
    validated = []
    batch_size = 40
    
    for batch_idx, batch in enumerate(batched(candidate_pairs, batch_size)):
        # Prepare batch data
        batch_data = []
        for c1_id, c2_id in batch:
            c1 = get_clause_by_id(c1_id)
            c2 = get_clause_by_id(c2_id)
            batch_data.append({
                "pair_id": f"{c1.clause_number}_{c2.clause_number}",
                "clause1": {"number": c1.clause_number, "text": c1.text},
                "clause2": {"number": c2.clause_number, "text": c2.text}
            })
        
        # LLM prompt
        prompt = f"""
Analyze these clause pairs for LEGAL CONFLICTS.

STRICT CRITERIA - A conflict exists ONLY if:
1. Both clauses address the SAME topic/subject
2. Both apply to the SAME scenario/situation
3. Both affect the SAME party/obligation
4. The instructions are MUTUALLY EXCLUSIVE (cannot follow both)

EVIDENCE REQUIRED:
- You MUST quote EXACT text from BOTH clauses
- Quotes must be word-for-word from the original
- If you cannot find exact conflicting text, it is NOT a conflict

PAIRS TO ANALYZE:
{json.dumps(batch_data, indent=2)}

Return JSON array (empty if no conflicts):
[
  {{
    "pair_id": "10_12",
    "conflict_type": "PAYMENT_METHOD",
    "severity": "HIGH",
    "left_quote": "exact quote from clause showing conflict",
    "right_quote": "exact quote from other clause showing conflict",
    "explanation": "Why these quotes contradict each other",
    "confidence": 0.95
  }}
]
"""
        
        # Call Ollama
        response = await httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": "qwen2.5:32b",
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1}  # Low for consistency
            },
            timeout=180.0
        )
        
        conflicts = json.loads(response.json()["response"])
        
        # Validate evidence exists
        for conflict in conflicts:
            if (conflict.get("left_quote") and 
                conflict.get("right_quote") and
                conflict.get("confidence", 0) >= 0.85):
                validated.append(conflict)
        
        logger.info(f"Batch {batch_idx+1}/{total_batches}: {len(conflicts)} found")
    
    return validated
```

### Step 5.5: Store Conflicts in Database

```python
# Store validated conflicts
for conflict_data in validated_conflicts:
    c1_num, c2_num = conflict_data["pair_id"].split("_")
    c1 = get_clause_by_number(c1_num)
    c2 = get_clause_by_number(c2_num)
    
    conflict = Conflict(
        contract_version_id=version.id,
        left_clause_id=c1.id,
        right_clause_id=c2.id,
        conflict_type=conflict_data["conflict_type"],
        severity=conflict_data["severity"],
        description=conflict_data["explanation"],
        left_quote=conflict_data["left_quote"],
        right_quote=conflict_data["right_quote"],
        score=conflict_data["confidence"],
        analysis_run_id=run.id
    )
    db.add(conflict)

db.commit()

# Update run status
run.status = "COMPLETED"
run.finished_at = datetime.utcnow()
db.commit()
```

---

## PHASE 6: RESULTS DISPLAY

### Frontend Receives Results

```json
{
    "run_id": "...",
    "status": "COMPLETED",
    "conflicts": [
        {
            "id": "conflict-uuid",
            "left_clause": {
                "number": "10",
                "text": "Agency shall reconcile all fees..."
            },
            "right_clause": {
                "number": "12",
                "text": "Fixed lump sum payment..."
            },
            "conflict_type": "PAYMENT_METHOD",
            "severity": "HIGH",
            "description": "Clause 10 requires reconciliation, Clause 12 specifies fixed payment",
            "left_quote": "reconcile all the fees within 48 hours",
            "right_quote": "fixed lump sum payment mutually agreed",
            "score": 0.95
        }
    ],
    "conflicts_count": 5
}
```

---

## SUMMARY: What Uses REGEX vs LLM

| Component | Method | Details |
|-----------|--------|---------|
| **Clause Extraction** | REGEX | `HierarchicalClauseExtractor` uses regex patterns |
| **Clause Filtering** | CODE | `ClauseFilter` removes TOC, stubs |
| **Clause Splitting** | CODE | `ClauseSplitter` splits long clauses |
| **Clause Validation** | LLM (optional) | `ClauseValidator` checks boundaries |
| **Pair Selection** | KEYWORD MATCHING | Deterministic clustering by topic |
| **Conflict Validation** | LLM | Ollama qwen2.5:32b verifies conflicts |

---

## PERFORMANCE CHARACTERISTICS

### For Ver2 Alpha Data MSA (155 clauses):

| Phase | Time | Method |
|-------|------|--------|
| Upload & Validation | ~5 sec | HTTP, File I/O |
| Document Parsing | ~2 sec | PyMuPDF/python-docx |
| Clause Extraction | ~2-3 min | REGEX + optional LLM validation |
| Pair Selection | ~30 sec | Keyword clustering (no LLM) |
| Conflict Validation | ~20-25 min | 55 batches × ~25 sec per batch |
| **Total** | **~25-30 min** | |

### Database Records Created:

```
contracts: 1 row
contract_versions: 1 row
analysis_runs: 2 rows (extraction + detection)
clauses: 155 rows
conflicts: 5-70 rows (varies by contract)
```

---

## CURRENT LIMITATIONS

1. **Speed**: 55 LLM batches takes 20-25 minutes
2. **Consistency**: LLM may give different results on same input
3. **Edge Cases**: No detection of conflicts within same clause
4. **False Positives**: Some detected conflicts may not be true legal conflicts

---

## ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                │
│  (Next.js + Redux)                                              │
│  - Upload form                                                  │
│  - Clause viewer                                                │
│  - Conflict viewer                                              │
│  - Polling for background task status                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      NGINX (Reverse Proxy)                      │
│  - Routes /api/* to FastAPI                                     │
│  - Routes /* to Next.js                                         │
│  - 30 min timeout for long requests                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI (API Server)                       │
│  - /upload: File upload & parsing                               │
│  - /extract-clauses: Queue extraction task                      │
│  - /detect-conflicts: Queue detection task                      │
│  - /clauses, /conflicts: Fetch results                          │
└──────────┬──────────────────────────────────────────────────────┘
           │                                      
           ▼                                      
┌──────────────────────┐              ┌───────────────────────────┐
│     POSTGRESQL       │              │      REDIS (Queue)        │
│  - contracts         │              │  - Celery task queue      │
│  - contract_versions │              │  - Background job status  │
│  - clauses           │              └─────────────┬─────────────┘
│  - conflicts         │                            │
│  - analysis_runs     │                            ▼
└──────────────────────┘              ┌───────────────────────────┐
                                      │    CELERY WORKER          │
                                      │  - extract_clauses_task   │
                                      │  - analyze_conflicts_task │
                                      └─────────────┬─────────────┘
                                                    │
                                                    ▼
                                      ┌───────────────────────────┐
                                      │   OLLAMA (LLM Server)     │
                                      │   51.112.105.60:11434     │
                                      │   Model: qwen2.5:32b      │
                                      └───────────────────────────┘
```

---

## FILES REFERENCE

| File | Purpose |
|------|---------|
| `backend/app/api/v1/endpoints/contracts.py` | API endpoints |
| `backend/app/tasks/clause_extraction.py` | Celery task for extraction |
| `backend/app/tasks/conflict_analysis.py` | Celery task for detection |
| `backend/app/services/hierarchical_clause_extractor.py` | REGEX clause extraction |
| `backend/app/services/clause_filters.py` | Post-processing filters |
| `backend/app/services/clause_validator.py` | Optional LLM validation |
| `backend/app/services/fast_accurate_detector.py` | Conflict detection (current) |
| `backend/app/services/accurate_conflict_detector.py` | Alternative detector |
| `backend/app/services/llm_service.py` | LLM API wrapper |
| `backend/app/services/document_parser.py` | Document text extraction |
| `backend/app/models/clause.py` | Clause database model |
| `backend/app/models/conflict.py` | Conflict database model |
| `frontend/src/features/contract/contractSlice.ts` | Redux state & API calls |
