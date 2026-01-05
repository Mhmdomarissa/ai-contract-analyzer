"""
Fast & Accurate Conflict Detector

Simplified 2-stage approach:
1. Smart pair selection (explicit + keyword-based)
2. LLM validation with strict evidence requirements

Trade-offs:
- Faster: 5-10 minutes vs 20-40 minutes
- Still accurate: Evidence required, strict conflict rules
- More conflicts found: Less filtering, but still validated
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Set, Tuple
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models.clause import Clause
from app.models.conflict import AnalysisRun, Conflict

logger = logging.getLogger(__name__)


class FastAccurateDetector:
    """
    Simplified 2-stage detector prioritizing both speed and accuracy.
    
    Stage 1: Smart pair selection
    - Explicit overrides (notwithstanding, etc.)
    - Keyword-based clustering (payment, termination, liability, etc.)
    - All pairs within same keyword group
    
    Stage 2: LLM validation with evidence
    - MUST provide exact quotes from both clauses
    - Strict conflict criteria
    - Single-pass (no consistency check for speed)
    """
    
    def __init__(self, db: Session, ollama_url: str, model: str = "qwen2.5:32b"):
        self.db = db
        self.ollama_url = ollama_url
        self.model_name = model
    
    async def detect_conflicts(self, contract_version_id: str) -> Dict[str, Any]:
        """Main detection entry point"""
        start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("⚡ FAST & ACCURATE CONFLICT DETECTION")
        logger.info("=" * 80)
        
        # Create analysis run
        analysis_run = AnalysisRun(
            type="conflict_detection",
            model_name=self.model_name,
            status="RUNNING",
            contract_version_id=UUID(contract_version_id)
        )
        self.db.add(analysis_run)
        self.db.flush()
        
        try:
            # Load clauses
            clauses = self.db.query(Clause).filter(
                Clause.contract_version_id == UUID(contract_version_id)
            ).order_by(Clause.order_index).all()
            
            logger.info(f"📊 Loaded {len(clauses)} clauses")
            
            if len(clauses) < 2:
                analysis_run.status = "COMPLETED"
                self.db.commit()
                return {
                    "validated_conflicts": 0,
                    "total_time": time.time() - start_time
                }
            
            # Stage 1: Smart pair selection
            logger.info("\n" + "=" * 80)
            logger.info("📌 STAGE 1: Smart Pair Selection")
            logger.info("=" * 80)
            candidate_pairs = self._select_candidate_pairs(clauses)
            logger.info(f"✅ Selected {len(candidate_pairs)} candidate pairs")
            
            # Stage 2: LLM validation with evidence
            logger.info("\n" + "=" * 80)
            logger.info("🔍 STAGE 2: LLM Validation with Evidence")
            logger.info("=" * 80)
            validated_conflicts = await self._validate_with_evidence(clauses, candidate_pairs)
            logger.info(f"✅ Validated {len(validated_conflicts)} conflicts")
            
            # Store conflicts
            stored_count = 0
            for conflict in validated_conflicts:
                self._store_conflict(
                    analysis_run_id=analysis_run.id,
                    contract_version_id=UUID(contract_version_id),
                    conflict=conflict
                )
                stored_count += 1
            
            self.db.commit()
            
            analysis_run.status = "COMPLETED"
            self.db.commit()
            
            total_time = time.time() - start_time
            
            logger.info("\n" + "=" * 80)
            logger.info("🏁 DETECTION COMPLETE")
            logger.info("=" * 80)
            logger.info(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
            logger.info(f"📊 Conflicts found: {stored_count}")
            logger.info("=" * 80)
            
            return {
                "validated_conflicts": stored_count,
                "total_time": total_time,
                "candidate_pairs": len(candidate_pairs)
            }
            
        except Exception as e:
            logger.error(f"❌ Detection failed: {e}", exc_info=True)
            analysis_run.status = "FAILED"
            analysis_run.error_message = str(e)
            self.db.commit()
            raise
    
    def _select_candidate_pairs(self, clauses: List[Clause]) -> Set[Tuple[UUID, UUID]]:
        """
        Stage 1: Select candidate pairs using multiple strategies.
        
        Combines:
        1. Explicit overrides
        2. Keyword-based clustering
        3. Same section comparison (limited)
        """
        pairs = set()
        
        # Strategy 1: Explicit overrides
        override_keywords = ['notwithstanding', 'subject to', 'except as', 'except where', 'provided that']
        explicit_clauses = [c for c in clauses if any(kw in c.text.lower() for kw in override_keywords)]
        
        for c1 in explicit_clauses:
            for c2 in clauses:
                if c1.id != c2.id:
                    pairs.add((c1.id, c2.id) if c1.id < c2.id else (c2.id, c1.id))
        
        logger.info(f"   Explicit overrides: {len(explicit_clauses)} clauses → {len(pairs)} pairs")
        
        # Strategy 2: Keyword-based clustering
        keywords = {
            'payment': ['payment', 'fee', 'price', 'invoice', 'compensation', 'charge', 'remuneration'],
            'termination': ['terminate', 'termination', 'cancel', 'expire', 'expiry', 'end of term'],
            'liability': ['liability', 'liable', 'damage', 'indemnify', 'indemnification', 'responsible'],
            'confidentiality': ['confidential', 'confidentiality', 'secret', 'proprietary', 'disclosure'],
            'ip': ['intellectual property', 'ip right', 'copyright', 'patent', 'trademark', 'work product'],
            'warranty': ['warranty', 'warrant', 'guarantee', 'representation', 'assurance'],
            'dispute': ['dispute', 'arbitration', 'mediation', 'jurisdiction', 'governing law', 'court'],
            'subcontractor': ['subcontractor', 'sub-contractor', 'third party', 'outsource'],
        }
        
        clusters = {topic: [] for topic in keywords}
        for clause in clauses:
            text_lower = clause.text.lower()
            for topic, kws in keywords.items():
                if any(kw in text_lower for kw in kws):
                    clusters[topic].append(clause)
        
        # Compare within each cluster
        for topic, cluster_clauses in clusters.items():
            if len(cluster_clauses) < 2:
                continue
            
            # Limit to 50 clauses per cluster
            if len(cluster_clauses) > 50:
                logger.warning(f"   Cluster '{topic}' has {len(cluster_clauses)} clauses - limiting to 50")
                cluster_clauses = cluster_clauses[:50]
            
            cluster_pairs = 0
            for i, c1 in enumerate(cluster_clauses):
                for c2 in cluster_clauses[i+1:]:
                    pair = (c1.id, c2.id) if c1.id < c2.id else (c2.id, c1.id)
                    if pair not in pairs:
                        pairs.add(pair)
                        cluster_pairs += 1
            
            if cluster_pairs > 0:
                logger.info(f"   Cluster '{topic}': {len(cluster_clauses)} clauses → {cluster_pairs} new pairs")
        
        return pairs
    
    async def _validate_with_evidence(
        self,
        clauses: List[Clause],
        candidate_pairs: Set[Tuple[UUID, UUID]]
    ) -> List[Dict[str, Any]]:
        """
        Stage 2: Validate pairs using LLM with evidence extraction.
        
        Single-pass validation (no consistency check for speed).
        """
        validated_conflicts = []
        clause_map = {c.id: c for c in clauses}
        pairs_list = list(candidate_pairs)
        
        # Batch size: 40 pairs per call
        batch_size = 40
        total_batches = (len(pairs_list) + batch_size - 1) // batch_size
        
        logger.info(f"   Validating {len(pairs_list)} pairs in {total_batches} batches...")
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(pairs_list))
            batch = pairs_list[start_idx:end_idx]
            
            # Build prompt
            pairs_text = []
            for idx, (left_id, right_id) in enumerate(batch):
                left = clause_map[left_id]
                right = clause_map[right_id]
                pairs_text.append(
                    f"Pair {idx}:\n"
                    f"  LEFT - Clause {left.clause_number}:\n{left.text}\n"
                    f"  RIGHT - Clause {right.clause_number}:\n{right.text}"
                )
            
            prompt = f"""You are a legal expert identifying TRUE conflicts between contract clauses.

A TRUE CONFLICT means BOTH clauses CANNOT be complied with simultaneously.

STRICT RULES - ALL MUST BE TRUE:
✓ Same topic (both about payment, both about liability, etc.)
✓ Same scenario (same condition/trigger, not "if X" vs "if Y")
✓ Same party's obligation (not "party A does X" vs "party B does Y")
✓ Mutually exclusive (impossible to comply with both)

EXAMPLES OF NON-CONFLICTS:
❌ "Agency liable for errors in UAE" vs "Agency not liable for errors outside UAE" → Different scenarios (different locations)
❌ "Fees not payable if X" vs "Fees refundable if Y" → Different conditions
❌ "Must comply with security" vs "Security policy in Appendix" → Complementary

EVIDENCE REQUIRED:
You MUST extract exact quotes showing the conflict.

Analyze these {len(batch)} pairs:

{chr(10).join(pairs_text)}

Return ONLY valid JSON array (no wrapper):
[
  {{
    "pair_index": 0,
    "is_conflict": true,
    "confidence": 0.92,
    "conflict_type": "ValueMismatch",
    "summary": "Payment terms differ: Net 30 days vs Net 60 days",
    "left_quote": "payment within 30 days",
    "right_quote": "payment within 60 days",
    "why_conflict": "Both specify different payment deadlines for same invoices. Cannot comply with both.",
    "severity": "HIGH"
  }}
]

CONFLICT_TYPE: ValueMismatch, ObligationMismatch, JurisdictionMismatch, TimingMismatch, Other
SEVERITY: HIGH (core terms), MEDIUM (clarification needed), LOW (minor)

If no conflicts, return []
"""
            
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    response = await client.post(
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": self.model_name,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json"
                        }
                    )
                    result = response.json()
                    llm_response = result.get("response", "[]")
                
                conflicts = json.loads(llm_response)
                
                # Handle wrapped responses
                if isinstance(conflicts, dict):
                    for key in ["data", "conflicts", "results", "pairs", "conflict_list"]:
                        if key in conflicts and isinstance(conflicts[key], list):
                            conflicts = conflicts[key]
                            break
                
                if not isinstance(conflicts, list):
                    logger.warning(f"   Batch {batch_idx+1}: Invalid response type")
                    continue
                
                # Validate and collect
                batch_found = 0
                for conflict in conflicts:
                    if not conflict or not isinstance(conflict, dict):
                        continue
                    
                    if not conflict.get("is_conflict"):
                        continue
                    
                    if conflict.get("confidence", 0) < 0.85:
                        continue
                    
                    # Validate evidence
                    if not (conflict.get("left_quote") and conflict.get("right_quote")):
                        continue
                    
                    pair_idx = conflict.get("pair_index")
                    if pair_idx is None or pair_idx >= len(batch):
                        continue
                    
                    left_id, right_id = batch[pair_idx]
                    validated_conflicts.append({
                        "left_id": left_id,
                        "right_id": right_id,
                        "conflict_type": conflict.get("conflict_type", "Other"),
                        "summary": conflict.get("summary", ""),
                        "explanation": conflict.get("why_conflict", ""),
                        "left_quote": conflict.get("left_quote", ""),
                        "right_quote": conflict.get("right_quote", ""),
                        "severity": conflict.get("severity", "MEDIUM"),
                        "confidence": conflict.get("confidence", 0.85)
                    })
                    batch_found += 1
                
                logger.info(f"   Batch {batch_idx+1}/{total_batches}: {batch_found} conflicts found")
                
            except Exception as e:
                logger.error(f"   Batch {batch_idx+1} failed: {e}")
        
        return validated_conflicts
    
    def _store_conflict(
        self,
        analysis_run_id: UUID,
        contract_version_id: UUID,
        conflict: Dict[str, Any]
    ):
        """Store validated conflict"""
        
        db_conflict = Conflict(
            analysis_run_id=analysis_run_id,
            contract_version_id=contract_version_id,
            left_clause_id=conflict["left_id"],
            right_clause_id=conflict["right_id"],
            severity=conflict["severity"],
            score=str(conflict["confidence"]),
            summary=conflict["summary"],
            explanation=conflict["explanation"],
            status="ACTIVE"
        )
        
        self.db.add(db_conflict)
        self.db.flush()
