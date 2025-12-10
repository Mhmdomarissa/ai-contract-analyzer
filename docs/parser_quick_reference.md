# Quick Reference: Advanced Document Parsers

## Supported File Types

| Format | Extensions | Example Use Case |
|--------|-----------|------------------|
| PDF | `.pdf` | Standard contracts, scanned documents |
| Word | `.docx`, `.doc` | Contract drafts, agreements |
| Excel | `.xlsx`, `.xls`, `.csv` | Financial schedules, rate sheets |
| PowerPoint | `.pptx`, `.ppt` | Presentation contracts, proposals |
| HTML | `.html`, `.htm` | Web-based agreements, terms of service |
| Markdown | `.md`, `.markdown` | Modern contract templates |
| JSON | `.json`, `.jsonl` | Structured contract data |
| Text | `.txt` | Plain text agreements |
| Images | `.jpg`, `.png`, `.tiff`, `.bmp` | Scanned contracts (OCR) |

## File Locations

```
backend/app/services/parsers/
├── __init__.py              # Module exports
├── utils.py                 # Shared utilities
├── txt_parser.py           # Text files
├── pdf_parser.py           # PDF with OCR
├── docx_parser.py          # Word documents
├── excel_parser.py         # Excel/CSV
├── ppt_parser.py           # PowerPoint
├── html_parser.py          # HTML files
├── markdown_parser.py      # Markdown files
└── json_parser.py          # JSON/JSONL
```

## Quick Start Examples

### Upload and Parse a Contract

```python
from app.services.document_parser import parse_document

# Automatically detects format and uses appropriate parser
text = parse_document("/path/to/contract.pdf")
print(f"Extracted {len(text)} characters")
```

### Parse with Chunking

```python
from app.services.parsers.txt_parser import AdvancedTxtParser

# Create parser with 256-token chunks
parser = AdvancedTxtParser(chunk_token_num=256)

# Get chunks
chunks = parser.parse_with_chunks(file_path="large_contract.txt")

for i, chunk in enumerate(chunks):
    print(f"Chunk {i}: {chunk[:100]}...")
```

### Parse PDF with OCR

```python
from app.services.parsers.pdf_parser import AdvancedPdfParser

# Enable OCR for scanned documents
parser = AdvancedPdfParser(use_ocr=True, layout_recognition=True)

# Get structured sections
sections = parser.parse_with_layout(file_path="scanned_contract.pdf")

for section in sections:
    if section['type'] == 'table':
        print(f"Found table on page {section['page']}")
    else:
        print(f"Text on page {section['page']}: {section['text'][:100]}...")
```

### Parse Excel Workbook

```python
from app.services.parsers.excel_parser import AdvancedExcelParser

parser = AdvancedExcelParser()

# Get all sheets
sheets = parser._parse_sheets(file_path="pricing.xlsx")

for sheet_name, content in sheets:
    print(f"\n=== {sheet_name} ===")
    print(content)
```

### Parse HTML with Tables

```python
from app.services.parsers.html_parser import AdvancedHtmlParser

parser = AdvancedHtmlParser()

# Parse HTML file
text = parser.parse(file_path="terms.html")

# Or parse HTML string
html = "<html><body><p>Contract terms...</p></body></html>"
text = parser.parse(html=html)
```

### Parse JSON with Chunking

```python
from app.services.parsers.json_parser import AdvancedJsonParser

parser = AdvancedJsonParser()

# Parse with intelligent chunking at key boundaries
chunks = parser.parse_with_chunks(
    file_path="contract_data.json",
    chunk_token_count=128
)

for chunk in chunks:
    print(chunk)
```

## Testing Commands

```bash
# Test all parsers
docker compose exec api python test_parsers.py

# Test document_parser integration
docker compose exec api python test_document_parser.py

# Check container status
docker compose ps

# View API logs
docker compose logs -f api

# View worker logs
docker compose logs -f worker

# Rebuild containers (if code changes)
docker compose down
docker compose build --no-cache api worker
docker compose up -d
```

## Common Tasks

### Add a New File Type

1. Create parser in `backend/app/services/parsers/new_parser.py`
2. Add import to `backend/app/services/parsers/__init__.py`
3. Add file extension mapping in `backend/app/services/document_parser.py`
4. Add tests

### Toggle Advanced Parsers

Edit `backend/app/services/document_parser.py`:
```python
USE_ADVANCED_PARSERS = True  # Set to False for legacy parsers
```

### Adjust Chunk Size

```python
# For TXT parser - set at initialization
parser = AdvancedTxtParser(chunk_token_num=256)

# For other parsers - pass to parse_with_chunks()
chunks = parser.parse_with_chunks(
    file_path="document.pdf",
    chunk_token_count=256
)
```

### Custom Delimiters for Chunking

```python
# Use custom sentence delimiters
parser = AdvancedTxtParser(
    chunk_token_num=128,
    delimiter="\n.!?"  # Split on newlines, periods, and punctuation
)
```

## Troubleshooting

### Parser Import Error
```bash
# Ensure dependencies are installed
docker compose exec api pip list | grep -i pdfplumber
docker compose exec api pip list | grep -i pandas

# Rebuild if needed
docker compose build --no-cache api worker
```

### OCR Not Working
```bash
# Check tesseract installation
docker compose exec api tesseract --version

# Check poppler-utils for PDF to image conversion
docker compose exec api pdfinfo --version
```

### Encoding Issues
The parsers automatically handle encoding detection using chardet:
```python
from app.services.parsers.utils import find_codec, get_text

# Detect encoding
encoding = find_codec(binary_data)

# Get text with auto-encoding
text = get_text(file_path="/path/to/file.txt")
```

### Memory Issues with Large Files
Use chunking to process large files:
```python
# Process in 128-token chunks
parser = AdvancedTxtParser(chunk_token_num=128)
chunks = parser.parse_with_chunks(file_path="huge_contract.txt")

# Process chunks incrementally
for chunk in chunks:
    process_chunk(chunk)  # Your processing logic
```

## Performance Tips

1. **Use chunking for large documents** (>10MB)
2. **Disable OCR if not needed** for faster PDF processing
3. **Use CSV instead of XLSX** for large spreadsheets (faster)
4. **Cache parsed results** to avoid re-parsing
5. **Process files asynchronously** using Celery workers

## API Integration

The parsers integrate with the contract upload endpoint:

```python
# In upload endpoint (backend/app/api/v1/endpoints/contracts.py)
from app.services.document_parser import parse_document

# Parse uploaded file
parsed_text = parse_document(str(file_path))

# Save to database
version.parsed_text = parsed_text
db.commit()
```

## Environment Variables

Add to `.env` if you want to configure parsers:

```bash
# Enable/disable advanced parsers
USE_ADVANCED_PARSERS=true

# Default chunk size
DEFAULT_CHUNK_SIZE=128

# OCR language (for pytesseract)
OCR_LANG=eng

# Enable verbose logging
PARSER_LOG_LEVEL=DEBUG
```

## Further Reading

- Full implementation details: `docs/advanced_parser_implementation.md`
- DeepDoc reference: `docs/deepdoc/parser/`
- Test files: `backend/test_parsers.py`, `backend/test_document_parser.py`
