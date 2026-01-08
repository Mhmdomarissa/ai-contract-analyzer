#!/usr/bin/env python3
"""
Test script for 30-clause comparison with intentional conflicts
"""

import requests
import json
import time
import sys

# 30 test clauses - including intentional conflicts
CLAUSES = [
    # Jurisdiction conflicts (1-3)
    "11.7 This Agreement shall be governed by and construed in accordance with the laws of the United Kingdom.",
    "16.1 Disputes arising under this Agreement shall fall under the exclusive jurisdiction of the Courts of the Emirate of Abu Dhabi.",
    "Any legal proceedings must be conducted in the courts of New York State.",
    
    # Payment terms conflicts (4-6)
    "Payment is due within 30 days of invoice date.",
    "All invoices must be paid within 15 days of receipt.",
    "Payment terms are net 60 days from the date of invoice.",
    
    # Termination conflicts (7-9)
    "Either party may terminate this Agreement with 90 days written notice.",
    "This Agreement may be terminated by either party with 30 days notice.",
    "Termination requires 6 months advance written notification.",
    
    # Liability caps conflicts (10-12)
    "Total liability under this Agreement shall not exceed $100,000.",
    "Maximum liability is capped at $1,000,000 for all claims.",
    "Liability is limited to the amount paid in the previous 12 months.",
    
    # Confidentiality period conflicts (13-15)
    "Confidential information must be protected for 5 years after termination.",
    "All confidential information remains protected indefinitely.",
    "Confidentiality obligations expire 2 years after the Agreement ends.",
    
    # IP ownership conflicts (16-18)
    "All intellectual property created shall be owned by the Client.",
    "The Contractor retains all rights to intellectual property developed.",
    "Intellectual property shall be jointly owned by both parties.",
    
    # Non-compete conflicts (19-21)
    "Employee agrees not to compete for 2 years in the same industry.",
    "Non-compete restrictions shall apply for 5 years post-employment.",
    "No non-compete restrictions shall apply after termination.",
    
    # Working hours (22-24)
    "Standard working hours are 9 AM to 5 PM Monday through Friday.",
    "Employees must be available 24/7 for emergency support.",
    "Work schedule is flexible with no fixed hours required.",
    
    # Notice period conflicts (25-27)
    "All notices must be sent via registered mail to the addresses specified.",
    "Electronic mail to the designated email addresses constitutes valid notice.",
    "Notices are only valid if delivered in person with written acknowledgment.",
    
    # Amendment procedure conflicts (28-30)
    "This Agreement may only be amended by written document signed by both parties.",
    "Amendments can be made verbally if confirmed by email within 5 business days.",
    "Any party may unilaterally modify terms with 30 days notice to the other party."
]

DEFAULT_PAIR_PROMPT = """You are a legal expert and contract review machine. Here are two clauses from the same contract. Your job is to check the language and terms of both clauses and check for the following;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict\""""

DEFAULT_SELF_PROMPT = """You are a legal expert and contract review machine. Here is a clause from a contract. Your job is to check the language and terms of the clause and see if any of the statements therein meet the following conditions;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict\""""


def test_comparison():
    """Run the 30-clause comparison test"""
    
    n = len(CLAUSES)
    expected_total = n * (n + 1) // 2  # n self-checks + n*(n-1)/2 pairs
    
    print(f"🧪 Testing with {n} clauses")
    print(f"📊 Expected total comparisons: {expected_total} ({n} self-checks + {n*(n-1)//2} pairs)")
    print(f"⏱️  Estimated time: ~{expected_total * 2.5 / 60:.1f} minutes (at 2.5s per comparison)\n")
    
    # Expected conflicts (rough estimate based on clause groupings)
    print("🎯 Expected conflicts:")
    print("   - Jurisdiction: Clauses 1, 2, 3 (UK vs Abu Dhabi vs New York)")
    print("   - Payment terms: Clauses 4, 5, 6 (30d vs 15d vs 60d)")
    print("   - Termination: Clauses 7, 8, 9 (90d vs 30d vs 6mo)")
    print("   - Liability: Clauses 10, 11, 12 (different cap amounts)")
    print("   - And more...\n")
    
    payload = {
        "clauses": CLAUSES,
        "pair_prompt": DEFAULT_PAIR_PROMPT,
        "self_prompt": DEFAULT_SELF_PROMPT
    }
    
    print("🚀 Starting comparison...\n")
    start_time = time.time()
    
    try:
        response = requests.post(
            'http://localhost/api/v1/compare/all-vs-all',
            json=payload,
            stream=True,
            timeout=3600  # 1 hour timeout
        )
        
        if response.status_code != 200:
            print(f"❌ Error: HTTP {response.status_code}")
            print(response.text)
            return
        
        results_count = 0
        conflicts_count = 0
        self_checks_count = 0
        pair_checks_count = 0
        last_progress_time = time.time()
        
        print("📡 Receiving results via SSE...\n")
        
        for line in response.iter_lines():
            if not line:
                continue
                
            line = line.decode('utf-8')
            
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])
                    
                    if data['type'] == 'result':
                        result = data['data']
                        results_count += 1
                        
                        if result['is_self_check']:
                            self_checks_count += 1
                            check_type = "SELF"
                        else:
                            pair_checks_count += 1
                            check_type = "PAIR"
                        
                        if result['conflict']:
                            conflicts_count += 1
                            conflict_marker = "⚠️ "
                        else:
                            conflict_marker = "✓ "
                        
                        elapsed = time.time() - start_time
                        avg_time = elapsed / results_count
                        remaining = (expected_total - results_count) * avg_time
                        
                        # Print every 10 results or every 5 seconds
                        if results_count % 10 == 0 or (time.time() - last_progress_time) > 5:
                            print(f"{conflict_marker}[{results_count}/{expected_total}] {check_type}: "
                                  f"Clause {result['clause_i_index']+1} ↔ {result['clause_j_index']+1} | "
                                  f"Conflict: {result['conflict']} | "
                                  f"{result['performance']['total_time']:.1f}s | "
                                  f"ETA: {remaining/60:.1f}min")
                            last_progress_time = time.time()
                    
                    elif data['type'] == 'complete':
                        total_time = time.time() - start_time
                        print(f"\n✅ Comparison completed!")
                        print(f"📊 Statistics:")
                        print(f"   Total comparisons: {results_count}/{expected_total}")
                        print(f"   Self-checks: {self_checks_count}/{n}")
                        print(f"   Pair-checks: {pair_checks_count}/{n*(n-1)//2}")
                        print(f"   Conflicts found: {conflicts_count}")
                        print(f"   No conflicts: {results_count - conflicts_count}")
                        print(f"   Total time: {total_time/60:.1f} minutes")
                        print(f"   Avg time per comparison: {total_time/results_count:.2f}s")
                        
                        if results_count == expected_total:
                            print(f"\n✅ SUCCESS: All {expected_total} comparisons completed!")
                        else:
                            print(f"\n⚠️  WARNING: Only {results_count}/{expected_total} completed!")
                            print(f"   Missing: {expected_total - results_count} comparisons")
                        
                        return results_count, conflicts_count, total_time
                    
                    elif data['type'] == 'error':
                        print(f"\n❌ Error: {data['message']}")
                        return results_count, conflicts_count, time.time() - start_time
                    
                except json.JSONDecodeError as e:
                    print(f"⚠️  Failed to parse JSON: {line[:100]}")
                    continue
        
        # If we exit the loop without completion
        total_time = time.time() - start_time
        print(f"\n⚠️  Stream ended without completion message")
        print(f"   Received: {results_count}/{expected_total} comparisons")
        print(f"   Time elapsed: {total_time/60:.1f} minutes")
        
        return results_count, conflicts_count, total_time
        
    except requests.exceptions.Timeout:
        print("❌ Request timed out after 1 hour")
        return 0, 0, 3600
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0, 0


if __name__ == "__main__":
    print("=" * 80)
    print("30-CLAUSE COMPARISON TEST")
    print("=" * 80)
    print()
    
    results_count, conflicts_count, total_time = test_comparison()
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    expected = 30 * 31 // 2  # 465 total comparisons
    
    if results_count == expected:
        print("✅ Test PASSED - All comparisons completed")
    elif results_count > expected * 0.9:
        print("⚠️  Test PARTIAL - Most comparisons completed")
    else:
        print("❌ Test FAILED - Many comparisons missing")
    
    print(f"\nResults: {results_count}/{expected} comparisons")
    print(f"Conflicts: {conflicts_count}")
    print(f"Duration: {total_time/60:.1f} minutes")
    
    sys.exit(0 if results_count == expected else 1)
