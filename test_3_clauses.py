#!/usr/bin/env python3
"""
Quick test with just 3 clauses to verify the system works
"""

import requests
import json

CLAUSES = [
    "This Agreement shall be governed by the laws of the United Kingdom.",
    "Disputes shall fall under the exclusive jurisdiction of the Courts of Abu Dhabi.",
    "Payment is due within 30 days of invoice date."
]

payload = {
    "clauses": CLAUSES,
    "pair_prompt": "Check for conflicts between these clauses.",
    "self_prompt": "Check this clause for internal conflicts."
}

print("Testing with 3 clauses...")
print(f"Expected: 6 comparisons (3 self + 3 pairs)\n")

response = requests.post(
    'http://localhost/api/v1/compare/all-vs-all',
    json=payload,
    stream=True,
    timeout=300
)

results = []
for line in response.iter_lines():
    if not line:
        continue
    line = line.decode('utf-8')
    if line.startswith('data: '):
        try:
            data = json.loads(line[6:])
            if data['type'] == 'result':
                result = data['data']
                results.append(result)
                check_type = "SELF" if result['is_self_check'] else "PAIR"
                conflict = "⚠️ CONFLICT" if result['conflict'] else "✓ OK"
                print(f"[{len(results)}] {check_type}: Clause {result['clause_i_index']+1} ↔ {result['clause_j_index']+1} | {conflict}")
            elif data['type'] == 'complete':
                print(f"\n✅ Complete! Total: {len(results)} comparisons")
                print(f"Conflicts: {sum(1 for r in results if r['conflict'])}")
        except:
            pass

print(f"\nReceived {len(results)} results")
