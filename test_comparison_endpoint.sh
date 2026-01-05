#!/bin/bash

echo "Testing the Clause Comparison Endpoint..."
echo ""
echo "Sending test request with two sample clauses..."
echo ""

curl -X POST "http://localhost/api/v1/compare/clauses" \
  -H "Content-Type: application/json" \
  -d '{
    "clause_a": "The Client shall pay the Contractor within 30 days of invoice receipt.",
    "clause_b": "Payment is due within 60 days from the date of invoice.",
    "prompt": "Compare these two clauses and identify if there is a conflict regarding payment terms."
  }' | python3 -m json.tool

echo ""
echo "Test complete!"
