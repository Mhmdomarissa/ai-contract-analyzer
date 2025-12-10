#!/bin/bash
# Test script to verify clause extraction is working correctly

cd /home/ec2-user/apps/ai-contract-analyzer

echo "=========================================="
echo "Testing Clause Extraction"
echo "=========================================="
echo ""

docker compose exec -T worker python << 'PYEOF'
import sys
sys.path.insert(0, '/app')

from app.services import document_parser
from app.services.llm_service import LLMService

file_path = '/app/uploads/Alpha Data. Master Services Agreement - Temporary IT Resources.-Ver1 - Copy.docx'

print("Parsing document...")
text = document_parser.parse_document(file_path)
print(f"✓ Extracted {len(text):,} characters\n")

print("Extracting clauses...")
clauses = LLMService.extract_clauses_by_structure(text)
print(f"✓ Found {len(clauses)} clauses\n")

# Check for "Full Document" fallback clauses (shouldn't exist)
full_doc_clauses = [c for c in clauses if c.get('clause_number') == '0']
if full_doc_clauses:
    print(f"❌ ERROR: Found {len(full_doc_clauses)} 'Full Document' fallback clauses!")
    for c in full_doc_clauses:
        print(f"   - {c.get('category')} ({len(c.get('text', ''))} chars)")
else:
    print("✓ No 'Full Document' fallback clauses (GOOD!)\n")

# Show summary
print("Extracted clauses:")
print("-" * 80)
for i, clause in enumerate(clauses, 1):
    meta = clause.get('metadata', {})
    num = clause.get('clause_number', '?')
    cat = clause.get('category', 'No title')
    typ = meta.get('type', 'unknown')
    length = len(clause.get('text', ''))
    
    print(f"{i:2}. #{num:30} | {cat[:35]:35} | {typ:10} | {length:5} chars")

print("-" * 80)
print(f"\nTotal: {len(clauses)} clauses")

# Verification
expected_main_clauses = ['Preamble', 'AGREEMENT', 'DEFINITIONS AND INTERPRETATION', 'TERM AND SOLE AGREEMENT', 'FEE AND PAYMENT']
actual_main = [c.get('clause_number') for c in clauses if c.get('metadata', {}).get('type') != 'schedule']

print("\n" + "="*80)
if len(clauses) >= 8 and not full_doc_clauses:
    print("✓ EXTRACTION WORKING CORRECTLY!")
else:
    print("✗ EXTRACTION MAY HAVE ISSUES")
print("="*80)

PYEOF
