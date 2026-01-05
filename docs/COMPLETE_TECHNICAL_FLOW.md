# Contract Processing Flow: From Upload to Conflict Detection

## Complete Technical Flow (A to Z)

This document traces the entire journey of a contract from the moment it's uploaded through the frontend until conflicts are detected and displayed.

---

## 🎯 **Overview: The 8-Stage Pipeline**

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. UPLOAD  │───▶│ 2. STORAGE   │───▶│ 3. PARSING   │───▶│ 4. TASK      │
│  (Frontend) │    │ (File System)│    │ (PDF to Text)│    │ (Celery)     │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                     │
                                                                     ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 8. DISPLAY  │◀───│ 7. RETRIEVE  │◀───│ 6. CONFLICTS │◀───│ 5. EXTRACT   │
│  (Frontend) │    │ (API Query)  │    │ (LLM Analysis)│    │ (Clauses)    │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

---

## 📋 **Stage 1: Frontend Upload**

### Location: `frontend/src/app/contracts/[id]/page.tsx` or similar

### What Happens:
1. User clicks "Upload" button
2. File is selected (PDF, DOCX, etc.)
3. Frontend creates FormData with file

### API Request:
```javascript
POST /api/v1/contracts/{contract_id}/versions/upload
Content-Type: multipart/form-data

Body:
  - file: <binary data>
  - description: "Initial version" (optional)
```

### Data Flow:
```
User Browser
    │
    │ HTTP POST (multipart/form-data)
    ▼
Nginx (Port 80)
    │
    │ Proxy to port 8000
    ▼
FastAPI Application
```

---

## 📁 **Stage 2: File Storage & Database Record**

### Location: `backend/app/api/v1/endpoints/versions.py`

### Function: `upload_contract_version()`

### Code Flow:
```python
@router.post("/{contract_id}/versions/upload")
async def upload_contract_version(
    contract_id: UUID,
    file: UploadFile,
    db: Session = Depends(get_db)
):
    # 1. Validate file type
    if not file.content_type in ALLOWED_TYPES:
        raise HTTPException(400)
    
    # 2. Save file to disk
    file_path = f"uploads/{contract_id}_{timestamp}_{filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # 3. Create database record
    contract_version = ContractVersion(
        contract_id=contract_id,
        file_path=file_path,
        file_name=file.filename,
        file_size=file_size,
        status="PENDING"
    )
    db.add(contract_version)
    db.commit()
    
    # 4. Trigger background task
    task = extract_clauses_task.delay(
        str(contract_version.id)
    )
    
    return {
        "version_id": contract_version.id,
        "task_id": task.id,
        "status": "processing"
    }
```

### Database Changes:
```sql
INSERT INTO contract_versions (
    id,
    contract_id,
    file_path,
    file_name,
    file_size,
    status,
    created_at
) VALUES (...);
```

### File System:
```
/app/uploads/
    └── f81a968d-1f1e-4819-a432-4e9ef8673eb6_20251217_103000_contract.pdf
```

---

## 🔄 **Stage 3: Celery Task Queue**

### Location: `backend/app/tasks/clause_extraction.py`

### Task: `extract_clauses_task()`

### How Celery Works:
```
FastAPI (Producer)
    │
    │ task.delay(version_id)
    ▼
Redis (Message Broker)
    │
    │ Job Queue
    ▼
Celery Worker (Consumer)
    │
    │ Executes extract_clauses_task()
    ▼
Processing...
```

### Task Configuration:
```python
@celery_app.task(
    bind=True,
    name="extract_clauses",
    max_retries=3,
    default_retry_delay=60
)
def extract_clauses_task(self, version_id: str):
    # Main extraction logic here
```

---

## 📄 **Stage 4: Document Parsing (PDF → Text)**

### Location: `backend/app/services/parsers/pdf_parser.py`

### Class: `AdvancedPdfParser`

### Code Flow:
```python
def parse(file_path: str) -> str:
    # 1. Try PyMuPDF (fitz) - Fast and accurate
    doc = fitz.open(file_path)
    text = ""
    
    for page in doc:
        # Extract text with layout preservation
        text += page.get_text("text")
        
        # Extract tables if present
        if self.extract_tables:
            tables = self.table_extractor.extract(page)
            text += format_tables_as_text(tables)
    
    # 2. Fallback to pdfplumber if fitz fails
    if not text or len(text) < 100:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
    
    # 3. OCR for scanned PDFs (if enabled)
    if self.use_ocr and is_scanned(text):
        images = convert_from_path(file_path)
        for img in images:
            text += pytesseract.image_to_string(img)
    
    return text
```

### Output Example:
```
GLOBAL MASTER SERVICES & FRAMEWORK AGREEMENT

1. DEFINITIONS AND INTERPRETATION
1.1 "Affiliate" means any entity directly or indirectly controlling...
1.2 "Confidential Information" includes oral, written, visual...

2. SCOPE OF SERVICES
2.1 The Supplier shall provide the Services as requested...
(a) Services may be provided onsite, offshore...
(b) The Client may modify the scope...

APPENDIX A – SERVICE LEVEL AGREEMENT
A.1 Service availability shall be 99.9%.
A.2 Penalties shall apply if availability drops below 98%.
```

---

## ✂️ **Stage 5: Clause Extraction (Text → Structured Clauses)**

### Location: `backend/app/services/hierarchical_clause_extractor.py`

### Class: `HierarchicalClauseExtractor`

### 7-Phase Extraction Process:

#### **Phase 1: Detect Appendices**
```python
def _detect_appendices_and_schedules(text):
    pattern = r'^\s*((?:APPENDIX|SCHEDULE|EXHIBIT)\s+([A-Z0-9]+))'
    
    for match in re.finditer(pattern, text):
        appendix_boundaries.append({
            'pos': match.start(),
            'full_label': 'APPENDIX A',
            'identifier': 'A'
        })
```

**Output:**
```python
appendix_boundaries = [
    {'pos': 2500, 'full_label': 'APPENDIX A', 'identifier': 'A'},
    {'pos': 2800, 'full_label': 'APPENDIX B', 'identifier': 'B'},
    {'pos': 3100, 'full_label': 'SCHEDULE 1', 'identifier': '1'}
]
```

#### **Phase 2: Find Clause Boundaries**
```python
def _find_all_boundaries(text):
    patterns = {
        'sub_sub_sub': r'(\d+\.\d+\.\d+\.\d+)',  # 1.1.1.1
        'sub_sub': r'(\d+\.\d+\.\d+)',           # 1.1.1
        'sub': r'(\d+\.\d+)',                    # 1.1
        'main': r'(\d+)[\.\)]',                  # 1. or 1)
        'appendix_clause': r'([A-Z])\.(\d+)',    # A.1
        'lettered': r'(\([a-z]\))'               # (a)
    }
    
    for pattern_type, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            boundaries.append({
                'pos': match.start(),
                'label': match.group(1),
                'type': pattern_type
            })
```

**Output:**
```python
boundaries = [
    {'pos': 150, 'label': '1', 'type': 'main'},
    {'pos': 200, 'label': '1.1', 'type': 'sub'},
    {'pos': 350, 'label': '1.2', 'type': 'sub'},
    {'pos': 500, 'label': '2', 'type': 'main'},
    {'pos': 550, 'label': '2.1', 'type': 'sub'},
    {'pos': 600, 'label': '(a)', 'type': 'lettered'},
    {'pos': 700, 'label': '(b)', 'type': 'lettered'},
    {'pos': 2500, 'label': 'APPENDIX A', 'type': 'appendix_header'},
    {'pos': 2550, 'label': 'A.1', 'type': 'appendix_clause'}
]
```

#### **Phase 3: Extract Preamble**
```python
def _extract_preamble(text, boundaries):
    first_clause_pos = boundaries[0]['pos']
    if first_clause_pos > 100:
        preamble_text = text[0:first_clause_pos]
        clauses.append({
            'clause_number': 'PREAMBLE',
            'text': preamble_text,
            'parent_clause_id': None,
            'depth_level': 0
        })
```

#### **Phase 4: Extract Clause Text**
```python
def _extract_all_clauses(text, boundaries):
    for i, boundary in enumerate(boundaries):
        # Find end position (before next clause)
        if i < len(boundaries) - 1:
            next_pos = boundaries[i + 1]['pos']
            # Find last newline before next clause
            end_pos = text.rfind('\n', boundary['pos'], next_pos)
        else:
            end_pos = len(text)
        
        clause_text = text[boundary['pos']:end_pos].strip()
        
        clauses.append({
            'clause_number': boundary['label'],
            'text': clause_text,
            'parent_clause_id': None,  # Set later
            'depth_level': 0,          # Set later
            'category': categorize(clause_text),
            'start_char': boundary['pos'],
            'end_char': end_pos
        })
```

#### **Phase 5: Build Hierarchy Tree**
```python
def _build_hierarchy():
    for clause in clauses:
        clause_num = clause['clause_number']
        
        # Example: "1.1" -> parent is "1"
        if '.' in clause_num:
            parts = clause_num.rsplit('.', 1)
            parent_num = parts[0]
            
            if parent_num in clause_lookup:
                parent = clause_lookup[parent_num]
                clause['parent_clause_id'] = parent_num
                clause['depth_level'] = parent['depth_level'] + 1
        
        # Example: "(a)" -> parent is nearest numeric clause
        elif clause_num.startswith('('):
            # Find previous numeric clause
            for prev_clause in reversed(clauses[:current_index]):
                if prev_clause['clause_number'][0].isdigit():
                    clause['parent_clause_id'] = prev_clause['clause_number']
                    clause['depth_level'] = prev_clause['depth_level'] + 1
                    break
```

**Output:**
```python
clauses = [
    {
        'clause_number': '1',
        'parent_clause_id': None,
        'depth_level': 0,
        'text': '1. DEFINITIONS AND INTERPRETATION',
        'category': 'DEFINITIONS'
    },
    {
        'clause_number': '1.1',
        'parent_clause_id': '1',  # ← Parent relationship
        'depth_level': 1,         # ← First child level
        'text': '1.1 "Affiliate" means...',
        'category': 'DEFINITIONS'
    },
    {
        'clause_number': '2.1',
        'parent_clause_id': '2',
        'depth_level': 1,
        'text': '2.1 The Supplier shall provide...',
        'category': 'SCOPE'
    },
    {
        'clause_number': '(a)',
        'parent_clause_id': '2.1',  # ← Nested under 2.1
        'depth_level': 2,            # ← Second child level
        'text': '(a) Services may be provided onsite...',
        'category': 'SCOPE'
    }
]
```

#### **Phase 6: Inherit Headings**
```python
def _inherit_headings():
    for clause in clauses:
        if clause['parent_clause_id']:
            parent = clause_lookup[clause['parent_clause_id']]
            # Inherit category from parent
            clause['category'] = parent['category']
```

#### **Phase 7: Detect Override Clauses**
```python
def _detect_override_clauses():
    override_keywords = [
        'notwithstanding',
        'shall prevail',
        'in the event of conflict',
        'shall override'
    ]
    
    for clause in clauses:
        text_lower = clause['text'].lower()
        if any(keyword in text_lower for keyword in override_keywords):
            clause['is_override_clause'] = True
```

**Final Output:**
```python
clauses = [
    {
        'clause_number': '2.2',
        'parent_clause_id': '2',
        'depth_level': 1,
        'text': '2.2 Notwithstanding Clause 2.1, the Supplier...',
        'category': 'SCOPE',
        'is_override_clause': True,  # ← Detected as override
        'start_char': 800,
        'end_char': 950
    }
]
```

---

## 💾 **Stage 6: Database Storage**

### Location: `backend/app/tasks/clause_extraction.py`

### Function: `extract_clauses_task()` (continued)

### Two-Pass Storage:

#### **Pass 1: Create All Clauses**
```python
clause_number_to_db_id = {}

for index, clause_data in enumerate(clauses):
    clause_obj = Clause(
        contract_version_id=version_id,
        clause_number=clause_data['clause_number'],
        heading=clause_data.get('heading'),
        text=clause_data['text'],
        order_index=index,
        depth_level=clause_data.get('depth_level', 0),
        is_override_clause=clause_data.get('is_override_clause', False),
        # parent_clause_id set in pass 2
    )
    session.add(clause_obj)

session.flush()  # Get IDs without committing
```

#### **Pass 2: Set Parent Relationships**
```python
# Build mapping: clause_number → database ID
for clause in session.query(Clause).filter_by(
    contract_version_id=version_id
).all():
    clause_number_to_db_id[clause.clause_number] = clause.id

# Set parent_clause_id (UUID references)
for index, clause_data in enumerate(clauses):
    parent_clause_number = clause_data.get('parent_clause_id')
    
    if parent_clause_number and parent_clause_number in clause_number_to_db_id:
        clause_obj = session.query(Clause).filter_by(
            contract_version_id=version_id,
            order_index=index
        ).first()
        
        parent_uuid = clause_number_to_db_id[parent_clause_number]
        clause_obj.parent_clause_id = parent_uuid

session.commit()
```

### Database State After Storage:
```sql
-- clauses table
id                                   | clause_number | parent_clause_id                     | depth_level | is_override | text
-------------------------------------|---------------|--------------------------------------|-------------|-------------|------
a1b2c3d4-...                        | 1             | NULL                                 | 0           | false       | 1. DEFINITIONS...
e5f6g7h8-...                        | 1.1           | a1b2c3d4-...                        | 1           | false       | 1.1 "Affiliate"...
i9j0k1l2-...                        | 2             | NULL                                 | 0           | false       | 2. SCOPE...
m3n4o5p6-...                        | 2.1           | i9j0k1l2-...                        | 1           | false       | 2.1 The Supplier...
q7r8s9t0-...                        | (a)           | m3n4o5p6-...                        | 2           | false       | (a) Services may...
u1v2w3x4-...                        | 2.2           | i9j0k1l2-...                        | 1           | true        | 2.2 Notwithstanding...
```

---

## 🔍 **Stage 7: Conflict Detection**

### Location: `backend/app/services/llm_service.py`

### Function: `identify_conflicts()`

### When It Runs:
- Automatically after clause extraction completes
- Or manually triggered via API: `POST /api/v1/conflicts/analyze`

### Code Flow:

#### **Step 1: Load All Clauses**
```python
clauses = session.query(Clause).filter_by(
    contract_version_id=version_id
).order_by(Clause.order_index).all()

# Convert to LLM format
clause_contexts = [
    {
        "id": str(clause.id),
        "clause_number": clause.clause_number,
        "text": clause.text,
        "category": get_category(clause),
        "is_override_clause": clause.is_override_clause
    }
    for clause in clauses
]
```

#### **Step 2: Filter Out Override Clauses**
```python
# Don't analyze override clauses - they're intentional
non_override_clauses = [
    c for c in clause_contexts 
    if not c.get('is_override_clause', False)
]
```

#### **Step 3: Category-Based Grouping**
```python
# Group clauses by category for efficient comparison
categories = {}
for clause in non_override_clauses:
    category = clause.get('category', 'Uncategorized')
    if category not in categories:
        categories[category] = []
    categories[category].append(clause)
```

#### **Step 4: Pairwise Conflict Detection**
```python
conflicts = []

# Only compare clauses within same category
for category, category_clauses in categories.items():
    for i, clause1 in enumerate(category_clauses):
        for clause2 in category_clauses[i+1:]:
            # Call LLM to detect conflict
            prompt = f"""
            Analyze these two clauses for conflicts:
            
            Clause {clause1['clause_number']}:
            {clause1['text']}
            
            Clause {clause2['clause_number']}:
            {clause2['text']}
            
            Do they contradict each other? Respond with:
            - conflict: true/false
            - severity: high/medium/low
            - explanation: brief description
            """
            
            response = ollama.chat(
                model='qwen2.5:32b',
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            result = parse_json(response['message']['content'])
            
            if result['conflict']:
                conflicts.append({
                    'left_clause_id': clause1['id'],
                    'right_clause_id': clause2['id'],
                    'severity': result['severity'],
                    'explanation': result['explanation']
                })
```

#### **Step 5: Store Conflicts in Database**
```python
for conflict_data in conflicts:
    conflict = Conflict(
        contract_version_id=version_id,
        left_clause_id=UUID(conflict_data['left_clause_id']),
        right_clause_id=UUID(conflict_data['right_clause_id']),
        severity=conflict_data['severity'],
        explanation=conflict_data['explanation'],
        status='UNRESOLVED'
    )
    session.add(conflict)

session.commit()
```

### Database State After Conflict Detection:
```sql
-- conflicts table
id          | left_clause_id | right_clause_id | severity | explanation                    | status
------------|----------------|-----------------|----------|--------------------------------|------------
conflict-1  | clause-id-5    | clause-id-12    | high     | Payment terms contradict...   | UNRESOLVED
conflict-2  | clause-id-8    | clause-id-15    | medium   | Termination periods differ... | UNRESOLVED
```

---

## 📤 **Stage 8: API Retrieval & Frontend Display**

### Location: `backend/app/api/v1/endpoints/contracts.py`

### Endpoint: `GET /api/v1/contracts/{contract_id}/clauses`

```python
@router.get("/{contract_id}/clauses")
def get_contract_clauses(
    contract_id: UUID,
    version_id: UUID = None,
    db: Session = Depends(get_db)
):
    # Get latest version if not specified
    if not version_id:
        version = db.query(ContractVersion).filter_by(
            contract_id=contract_id
        ).order_by(ContractVersion.created_at.desc()).first()
        version_id = version.id
    
    # Load clauses with hierarchy
    clauses = db.query(Clause).filter_by(
        contract_version_id=version_id
    ).order_by(Clause.order_index).all()
    
    # Build hierarchy tree
    clause_tree = build_tree(clauses)
    
    return {
        "clauses": [
            {
                "id": str(clause.id),
                "clause_number": clause.clause_number,
                "heading": clause.heading,
                "text": clause.text,
                "depth_level": clause.depth_level,
                "parent_clause_id": str(clause.parent_clause_id) if clause.parent_clause_id else None,
                "is_override_clause": clause.is_override_clause,
                "children": get_children(clause.id, clauses)
            }
            for clause in clauses
        ]
    }
```

### Endpoint: `GET /api/v1/contracts/{contract_id}/conflicts`

```python
@router.get("/{contract_id}/conflicts")
def get_conflicts(
    contract_id: UUID,
    version_id: UUID = None,
    db: Session = Depends(get_db)
):
    conflicts = db.query(Conflict).join(
        ContractVersion
    ).filter(
        ContractVersion.contract_id == contract_id,
        Conflict.status != 'RESOLVED'
    ).all()
    
    return {
        "conflicts": [
            {
                "id": str(conflict.id),
                "left_clause": {
                    "id": str(conflict.left_clause.id),
                    "clause_number": conflict.left_clause.clause_number,
                    "text": conflict.left_clause.text
                },
                "right_clause": {
                    "id": str(conflict.right_clause.id),
                    "clause_number": conflict.right_clause.clause_number,
                    "text": conflict.right_clause.text
                },
                "severity": conflict.severity,
                "explanation": conflict.explanation,
                "status": conflict.status
            }
            for conflict in conflicts
        ]
    }
```

### Frontend Display:
```typescript
// Fetch clauses
const clauses = await fetch(`/api/v1/contracts/${id}/clauses`)

// Fetch conflicts
const conflicts = await fetch(`/api/v1/contracts/${id}/conflicts`)

// Render hierarchy tree
<ClauseTree clauses={clauses} />

// Render conflicts
<ConflictsList conflicts={conflicts} />
```

---

## 🗄️ **Database Schema Overview**

```sql
-- Contracts (top level)
contracts
    id (UUID, PK)
    name
    description
    created_at

-- Versions (each upload)
contract_versions
    id (UUID, PK)
    contract_id (FK → contracts.id)
    file_path
    file_name
    status (PENDING/PROCESSING/COMPLETED/FAILED)
    parsed_text (full extracted text)
    created_at

-- Clauses (extracted from version)
clauses
    id (UUID, PK)
    contract_version_id (FK → contract_versions.id)
    clause_number (e.g., "1.1", "(a)", "A.1")
    heading
    text
    order_index (0, 1, 2, ...)
    parent_clause_id (FK → clauses.id) ← SELF-REFERENCE
    depth_level (0, 1, 2, ...)
    is_override_clause (true/false)
    category (PAYMENT, CONFIDENTIALITY, etc.)
    created_at

-- Conflicts (detected between clauses)
conflicts
    id (UUID, PK)
    contract_version_id (FK → contract_versions.id)
    left_clause_id (FK → clauses.id)
    right_clause_id (FK → clauses.id)
    severity (high/medium/low)
    explanation (text)
    status (UNRESOLVED/RESOLVED/IGNORED)
    created_at
```

---

## ⚙️ **Technology Stack Summary**

### Backend Services:
- **FastAPI**: REST API framework
- **Celery**: Async task queue (clause extraction, conflict detection)
- **Redis**: Message broker for Celery
- **PostgreSQL**: Relational database
- **Ollama (qwen2.5:32b)**: LLM for conflict detection
- **PyMuPDF/pdfplumber**: PDF parsing
- **Tesseract OCR**: Scanned document processing

### Key Libraries:
- **SQLAlchemy**: ORM for database
- **Alembic**: Database migrations
- **Pydantic**: Data validation
- **Regex (re)**: Pattern matching for clause extraction

### Frontend:
- **Next.js**: React framework
- **TypeScript**: Type-safe JavaScript
- **TailwindCSS**: Styling

---

## 🔄 **Complete Data Flow Summary**

```
1. UPLOAD
   User → Frontend → POST /api/v1/contracts/{id}/versions/upload
   
2. STORAGE
   FastAPI → Save file to disk → Create contract_version record
   
3. TASK QUEUE
   FastAPI → Celery.delay(extract_clauses_task) → Redis → Worker
   
4. PARSING
   Worker → AdvancedPdfParser.parse() → Raw text
   
5. EXTRACTION
   Worker → HierarchicalClauseExtractor.extract_clauses()
   
   Phase 1: Detect appendices
   Phase 2: Find boundaries (1, 1.1, (a), A.1)
   Phase 3: Extract preamble
   Phase 4: Extract clause text
   Phase 5: Build hierarchy (parent_clause_id, depth_level)
   Phase 6: Inherit headings
   Phase 7: Detect overrides (notwithstanding, shall prevail)
   
   Output: List of structured clauses with hierarchy
   
6. DATABASE STORAGE
   Worker → Two-pass storage:
   - Pass 1: INSERT clauses (get UUIDs)
   - Pass 2: UPDATE parent_clause_id (map clause_number → UUID)
   
7. CONFLICT DETECTION
   Worker → LLMService.identify_conflicts()
   - Load clauses
   - Filter out override clauses
   - Group by category
   - Pairwise comparison (LLM call for each pair)
   - Store conflicts in database
   
8. RETRIEVAL
   Frontend → GET /api/v1/contracts/{id}/clauses
   Frontend → GET /api/v1/contracts/{id}/conflicts
   
9. DISPLAY
   Frontend renders:
   - Hierarchical clause tree
   - Conflict highlights
   - Override clause badges
```

---

## 📊 **Performance Metrics**

Typical processing times for a 50-clause contract:

1. **Upload**: ~0.5 seconds (file I/O)
2. **PDF Parsing**: ~1-2 seconds (PyMuPDF)
3. **Clause Extraction**: ~1 second (regex + hierarchy building)
4. **Database Storage**: ~0.5 seconds (2-pass insert + update)
5. **Conflict Detection**: ~30-60 seconds (LLM calls for ~1,225 pairs)
6. **Total**: ~35-65 seconds end-to-end

Optimization note: Conflict detection is the bottleneck (O(n²) pairwise comparisons with LLM).

---

## 🎯 **Key Design Decisions**

1. **Why Two-Pass Storage?**
   - Can't set parent_clause_id UUID until parent clause exists in DB
   - Pass 1 creates all clauses, Pass 2 links them

2. **Why Hierarchy in Extraction Phase?**
   - Easier to build hierarchy from text structure than from flat database
   - String-based clause_number matching simpler than UUID navigation

3. **Why Filter Override Clauses?**
   - Override clauses intentionally contradict other clauses
   - Detecting them as conflicts would create false positives

4. **Why Category-Based Conflict Detection?**
   - Reduces comparison pairs (only PAYMENT vs PAYMENT, not PAYMENT vs LIABILITY)
   - Improves LLM accuracy (similar context)

5. **Why Celery for Background Tasks?**
   - Non-blocking API responses (returns immediately)
   - Scalable (can add more workers)
   - Retry mechanism for transient failures

---

**End of Technical Flow Documentation**
