"""
Complete Approach C Pipeline Test

This script tests the full claim-based conflict detection pipeline:
1. Extract claims from clauses
2. Build conflict graph (deterministic rules)
3. LLM judge validates candidates
4. Store high-confidence conflicts
"""
import asyncio
import sys
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.claim import Claim
from app.models.clause import Clause
from app.models.conflict import Conflict
from app.services.claim_extractor import ClaimExtractor
from app.services.conflict_graph_builder import ConflictGraphBuilder
from app.services.conflict_judge import ConflictJudge
from app.core.config import settings


async def test_full_pipeline():
    """Run the complete claim-based conflict detection pipeline."""
    
    print("=" * 80)
    print("APPROACH C: CLAIM-BASED CONFLICT DETECTION - FULL PIPELINE TEST")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Get latest contract version
        print("\n📄 Step 1: Loading latest contract version...")
        latest_version = db.query(Clause).order_by(Clause.created_at.desc()).first()
        if not latest_version:
            print("❌ No clauses found in database")
            return
        
        contract_version_id = latest_version.contract_version_id
        print(f"✅ Contract Version: {contract_version_id}")
        
        # Get all clauses for this version
        clauses = db.query(Clause).filter(
            Clause.contract_version_id == contract_version_id
        ).all()
        
        print(f"✅ Loaded {len(clauses)} clauses")
        
        # Phase 1: Extract Claims
        print("\n" + "=" * 80)
        print("PHASE 1: CLAIM EXTRACTION")
        print("=" * 80)
        
        # Check if claims already exist
        existing_claims = db.query(Claim).filter(
            Claim.contract_version_id == contract_version_id
        ).count()
        
        if existing_claims > 0:
            print(f"⚠️  Found {existing_claims} existing claims")
            response = input("Delete and re-extract? (y/n): ")
            if response.lower() == 'y':
                print("🗑️  Deleting existing claims...")
                db.query(Claim).filter(
                    Claim.contract_version_id == contract_version_id
                ).delete()
                db.commit()
                print("✅ Deleted")
                existing_claims = 0
        
        if existing_claims == 0:
            print(f"\n🔍 Extracting claims from {len(clauses)} clauses...")
            print("(This will take ~6 seconds for 300 clauses)")
            
            extractor = ClaimExtractor(
                ollama_url=settings.OLLAMA_URL,
                model="qwen2.5:32b"
            )
            
            total_claims = await extractor.extract_and_store_claims(
                db=db,
                contract_version_id=str(contract_version_id),
                clauses=clauses
            )
            
            print(f"\n✅ PHASE 1 COMPLETE: Extracted {total_claims} claims")
        else:
            total_claims = existing_claims
            print(f"\n✅ Using {total_claims} existing claims")
        
        # Load all claims
        claims = db.query(Claim).filter(
            Claim.contract_version_id == contract_version_id
        ).all()
        
        print(f"\n📊 Claim Statistics:")
        print(f"   Total claims: {len(claims)}")
        
        # Count by topic
        from collections import Counter
        topics = Counter(c.topic for c in claims)
        print(f"   Topics:")
        for topic, count in topics.most_common():
            print(f"      {topic}: {count}")
        
        # Phase 2: Build Conflict Graph
        print("\n" + "=" * 80)
        print("PHASE 2: CONFLICT GRAPH (DETERMINISTIC RULES)")
        print("=" * 80)
        
        graph_builder = ConflictGraphBuilder()
        candidates = graph_builder.find_conflict_candidates(claims)
        
        print(f"\n✅ PHASE 2 COMPLETE: Found {len(candidates)} candidate pairs")
        print(f"   (Reduced from {len(claims) * (len(claims)-1) // 2} total pairs)")
        print(f"   Reduction: {100 * (1 - len(candidates) / max(1, len(claims) * (len(claims)-1) // 2)):.1f}%")
        
        if len(candidates) == 0:
            print("\n⚠️  No conflict candidates found. This might indicate:")
            print("   1. The contract has no conflicts (good!)")
            print("   2. Claims extraction needs refinement")
            print("   3. Conflict rules need adjustment")
            return
        
        # Show sample candidates
        print(f"\n📋 Sample Candidates (first 5):")
        for i, (c1, c2) in enumerate(candidates[:5], 1):
            print(f"\n   Candidate {i}:")
            print(f"      Claim 1: {c1.subject} {c1.action} (modality={c1.modality}, value={c1.normalized_value})")
            print(f"      Claim 2: {c2.subject} {c2.action} (modality={c2.modality}, value={c2.normalized_value})")
            print(f"      Topic: {c1.topic}")
        
        # Phase 3: LLM Judge
        print("\n" + "=" * 80)
        print("PHASE 3: LLM JUDGE (VALIDATE CANDIDATES)")
        print("=" * 80)
        
        print(f"\n🤖 Judging {len(candidates)} candidate pairs...")
        print(f"   (This will take ~{len(candidates) * 0.02:.1f} seconds)")
        
        judge = ConflictJudge(
            ollama_url=settings.OLLAMA_URL,
            model="qwen2.5:32b"
        )
        
        conflicts = await judge.judge_conflicts(
            db=db,
            candidates=candidates,
            contract_version_id=str(contract_version_id)
        )
        
        print(f"\n✅ PHASE 3 COMPLETE: Validated {len(conflicts)} real conflicts")
        print(f"   Confidence threshold: >= 0.85")
        print(f"   False positive rate: {100 * (1 - len(conflicts) / max(1, len(candidates))):.1f}%")
        
        # Show conflict details
        if len(conflicts) > 0:
            print(f"\n🚨 DETECTED CONFLICTS:")
            print("=" * 80)
            
            for i, conflict in enumerate(conflicts[:10], 1):
                print(f"\n   Conflict {i}:")
                print(f"      Type: {conflict.get('conflict_type', 'N/A')}")
                print(f"      Severity: {conflict.get('severity', 'N/A')}")
                print(f"      Confidence: {conflict.get('confidence', 0):.2f}")
                print(f"      Why: {conflict.get('why', 'N/A')[:150]}...")
                print(f"      Resolution: {conflict.get('resolution', 'N/A')[:150]}...")
            
            if len(conflicts) > 10:
                print(f"\n   ... and {len(conflicts) - 10} more conflicts")
        else:
            print("\n✅ No conflicts detected (contract is consistent)")
        
        # Summary
        print("\n" + "=" * 80)
        print("PIPELINE SUMMARY")
        print("=" * 80)
        print(f"✅ Clauses processed: {len(clauses)}")
        print(f"✅ Claims extracted: {total_claims}")
        print(f"✅ Candidate pairs: {len(candidates)}")
        print(f"✅ Real conflicts: {len(conflicts)}")
        print(f"✅ Time estimate: ~{6 + len(candidates) * 0.02:.1f} seconds")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("\n🚀 Starting Approach C Pipeline Test...")
    asyncio.run(test_full_pipeline())
    print("\n✅ Test complete!")
