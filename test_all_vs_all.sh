#!/bin/bash

# Test All-vs-All Comparison Endpoint
# This script tests the N→N comparison with 3 sample clauses

echo "🧪 Testing All-vs-All Comparison (N → N)"
echo "========================================"
echo ""

BASE_URL="http://localhost:8000/api/v1"

# Test data: 3 clauses with potential conflicts
REQUEST_BODY='{
  "clauses": [
    "Payment must be made within 30 days of invoice date.",
    "Payment is due within 60 days from receipt of goods.",
    "Late fees of 2% apply after 45 days."
  ],
  "prompt": "Analyze if these two clauses conflict with each other. Focus on payment terms and deadlines. Return JSON with: conflict (boolean), severity (Low/Medium/High), explanation (string)."
}'

echo "📤 Sending request to ${BASE_URL}/compare/all-vs-all"
echo "📊 Comparing 3 clauses (expecting 3 unique pairs)"
echo ""

# Make request and capture streaming response
curl -X POST "${BASE_URL}/compare/all-vs-all" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_BODY" \
  --no-buffer

echo ""
echo ""
echo "✅ Test completed!"
echo ""
echo "Expected results:"
echo "  - 3 comparisons total: (0,1), (0,2), (1,2)"
echo "  - Streaming SSE format with 'result', 'status', 'complete' events"
echo "  - Each result should have: clause_i_index, clause_j_index, conflict, severity, explanation"
