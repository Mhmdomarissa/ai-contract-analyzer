# Advanced Table Extraction Implementation

## Overview
Implemented a comprehensive table extraction solution using the best available tools (camelot-py and pdfplumber) with structured JSON output and automatic clause linking.

## Solution Architecture

### 1. **Table Extraction Service** (`table_extractor.py`)
- **Primary Method**: camelot-py (best for complex tables with borders)
- **Fallback Method**: pdfplumber (more reliable, works with binary data)
- **Output Format**: Structured JSON with multiple representations:
  - `headers`: Column headers
  - `rows`: Array of row objects (key-value pairs)
  - `formatted_text`: Human-readable text format for clause inclusion
  - `json_data`: Pure JSON array for programmatic access
  - `table_id`: Unique identifier for table linking

### 2. **PDF Parser Integration** (`pdf_parser.py`)
- **Enhanced**: Added `extract_tables=True` parameter
- **Behavior**: 
  - Extracts tables during PDF parsing
  - Includes formatted table text in document text
  - Stores structured tables separately for clause linking
- **Method**: `get_extracted_tables()` returns structured table data

### 3. **Clause Extraction Integration** (`clause_extraction.py`)
- **Table Linking**: Automatically links tables to clauses based on text matching
- **Metadata**: Adds `linked_tables` array to clause metadata
- **Detection**: Uses table headers and content to find relevant clauses

### 4. **Dependencies**
- **camelot-py[cv]**: Advanced table extraction (requires ghostscript, tk)
- **pdfplumber**: Fallback table extraction
- **System**: ghostscript, python3-tk (for camelot)

## Features

### ✅ Structured Table Output
```json
{
  "table_id": "table_0",
  "method": "camelot",
  "accuracy": 0.95,
  "headers": ["Column1", "Column2", "Column3"],
  "rows": [
    {"Column1": "Value1", "Column2": "Value2", "Column3": "Value3"},
    {"Column1": "Value4", "Column2": "Value5", "Column3": "Value6"}
  ],
  "row_count": 2,
  "column_count": 3,
  "formatted_text": "Column1: Value1; Column2: Value2; Column3: Value3\n...",
  "json_data": [...]
}
```

### ✅ Automatic Clause Linking
- Tables are automatically linked to clauses that reference them
- Linked tables stored in clause metadata
- `has_table` flag set automatically

### ✅ Fallback Strategy
1. Try camelot (best accuracy for complex tables)
2. Fallback to pdfplumber (more reliable)
3. Graceful degradation if both fail

### ✅ Multiple Output Formats
- **Formatted Text**: For inclusion in clause text
- **JSON Array**: For programmatic access
- **Structured Objects**: For analysis and conflict detection

## Usage

### Automatic (Default)
Tables are automatically extracted when parsing PDFs:
```python
parser = AdvancedPdfParser(extract_tables=True)
text = parser.parse(file_path="document.pdf")
tables = parser.get_extracted_tables()  # Get structured tables
```

### Manual Table Extraction
```python
from app.services.table_extractor import TableExtractor

extractor = TableExtractor(prefer_camelot=True)
tables = extractor.extract_tables_from_pdf(file_path="document.pdf")
```

### Finding Tables in Text
```python
linked_tables = extractor.find_tables_in_text(clause_text, extracted_tables)
```

## Benefits

1. **Best-in-Class Accuracy**: Uses camelot-py (industry standard for table extraction)
2. **Robust Fallback**: pdfplumber ensures extraction works even if camelot fails
3. **Structured Data**: Tables stored as JSON for easy analysis
4. **Automatic Linking**: Tables automatically linked to relevant clauses
5. **Multiple Formats**: Text, JSON, and structured objects for different use cases
6. **Conflict Detection Ready**: Structured tables enable table-aware conflict detection

## Performance

- **camelot**: Best accuracy, slower (for complex tables)
- **pdfplumber**: Good accuracy, faster (for simple tables)
- **Automatic Selection**: System chooses best method based on table complexity

## Testing

To test table extraction:
1. Upload a PDF with tables
2. Extract clauses
3. Check clause metadata for `linked_tables`
4. View JSON response to see structured table data

## Future Enhancements

1. **ML-Based Table Detection**: Use LayoutLMv3 or Table Transformer for better detection
2. **Table Conflict Detection**: Compare tables across contracts
3. **Table Validation**: Verify table structure and completeness
4. **Table Visualization**: Display tables in UI with proper formatting

## Status

✅ **Implemented and Ready**
- Table extraction service created
- PDF parser integrated
- Clause linking implemented
- Dependencies installed
- Docker image built

Ready for production use!

