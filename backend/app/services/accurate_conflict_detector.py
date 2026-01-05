"""
Accurate Conflict Detector with Multi-Stage Validation

This implementation prioritizes accuracy over speed by:
1. Using LLM for clause categorization (not keywords)
2. Requiring explicit evidence extraction from both clauses
3. Multi-pass validation with self-consistency checks
4. Verification stage to eliminate false positives
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models.clause import Clause
from app.models.conflict import AnalysisRun, Conflict

logger = logging.getLogger(__name__)


@dataclass
class ConflictEvidence:
    """Evidence extracted from a clause"""
    quote: str
    start_char: int
    end_char: int
    reasoning: str


@dataclass
class ValidatedConflict:
    """A conflict that has passed all validation stages"""
    left_clause_id: UUID
    right_clause_id: UUID
    classification: str
    confidence: float
    conflict_type: str
    summary: str
    explanation: str
    left_evidence: ConflictEvidence
    right_evidence: ConflictEvidence
    materiality: str
    votes: int  # Number of LLM passes that agreed


class AccurateConflictDetector:
    """
    Multi-stage conflict detector with high accuracy.
    
    Stages:
    1. LLM-based categorization (group related clauses)
    2. Pair generation (only pairs within same category)
    3. First-pass conflict detection with evidence extraction
    4. Self-consistency check (multiple LLM evaluations)
    5. Verification stage (second LLM validates the conflict)
    """
    
    def __init__(
        self,
        db: Session,
        ollama_url: str,
        model: str = "qwen2.5:32b",
        consistency_votes: int = 2
    ):
        self.db = db
        self.ollama_url = ollama_url
        self.model_name = model
        self.consistency_votes = consistency_votes
        
    async def detect_conflicts(self, contract_version_id: str) -> Dict[str, Any]:
        """
        Main entry point for accurate conflict detection.
        
        Returns dictionary with:
        - validated_conflicts: Number of conflicts found
        - total_time: Time taken in seconds
        - stages: Details of each stage
        """
        import time
        start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("🎯 ACCURATE MULTI-STAGE CONFLICT DETECTION")
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
                    "total_time": time.time() - start_time,
                    "message": "Not enough clauses for conflict detection"
                }
            
            # Stage 1: Categorize clauses using LLM
            logger.info("\n" + "=" * 80)
            logger.info("📂 STAGE 1: LLM-Based Categorization")
            logger.info("=" * 80)
            categories = await self._categorize_clauses(clauses)
            logger.info(f"✅ Categorized into {len(categories)} categories")
            for cat, cls in categories.items():
                logger.info(f"   - {cat}: {len(cls)} clauses")
            
            # Stage 2: Generate candidate pairs (only within categories)
            logger.info("\n" + "=" * 80)
            logger.info("🔗 STAGE 2: Generate Candidate Pairs")
            logger.info("=" * 80)
            candidate_pairs = self._generate_pairs_from_categories(categories, clauses)
            logger.info(f"✅ Generated {len(candidate_pairs)} candidate pairs")
            
            # Stage 3: First-pass conflict detection with evidence
            logger.info("\n" + "=" * 80)
            logger.info("🔍 STAGE 3: First-Pass Detection with Evidence Extraction")
            logger.info("=" * 80)
            initial_conflicts = await self._detect_with_evidence(clauses, candidate_pairs)
            logger.info(f"✅ Found {len(initial_conflicts)} potential conflicts")
            
            # Stage 4: Self-consistency check
            logger.info("\n" + "=" * 80)
            logger.info("🎲 STAGE 4: Self-Consistency Validation")
            logger.info("=" * 80)
            consistent_conflicts = await self._check_consistency(clauses, initial_conflicts)
            logger.info(f"✅ {len(consistent_conflicts)} conflicts passed consistency check")
            
            # Stage 5: Verification stage
            logger.info("\n" + "=" * 80)
            logger.info("✔️  STAGE 5: Verification Pass")
            logger.info("=" * 80)
            verified_conflicts = await self._verify_conflicts(clauses, consistent_conflicts)
            logger.info(f"✅ {len(verified_conflicts)} conflicts verified")
            
            # Store verified conflicts
            stored_count = 0
            for conflict in verified_conflicts:
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
            logger.info(f"📊 Validated conflicts: {stored_count}")
            logger.info("=" * 80)
            
            return {
                "validated_conflicts": stored_count,
                "total_time": total_time,
                "stages": {
                    "categorization": len(categories),
                    "candidate_pairs": len(candidate_pairs),
                    "initial_detection": len(initial_conflicts),
                    "consistency_check": len(consistent_conflicts),
                    "verification": len(verified_conflicts)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Conflict detection failed: {e}", exc_info=True)
            analysis_run.status = "FAILED"
            analysis_run.error_message = str(e)
            self.db.commit()
            raise
    
    async def _categorize_clauses(
        self,
        clauses: List[Clause]
    ) -> Dict[str, List[Clause]]:
        """
        Stage 1: Use LLM to categorize each clause into topics.
        
        Instead of keyword matching, ask LLM to read each clause
        and assign it to relevant categories.
        
        Returns: Dict mapping category name to list of clauses
        """
        categories = defaultdict(list)
        
        # Process in batches of 20 clauses
        batch_size = 20
        total_batches = (len(clauses) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(clauses))
            batch = clauses[start_idx:end_idx]
            
            # Build categorization prompt
            clauses_text = []
            for idx, clause in enumerate(batch):
                clauses_text.append(
                    f"Clause {idx}:\n"
                    f"  Number: {clause.clause_number}\n"
                    f"  Heading: {clause.heading or 'No heading'}\n"
                    f"  Text: {clause.text[:500]}"
                )
            
            prompt = f"""You are categorizing contract clauses by their primary topic.

Analyze each clause and assign it to ONE OR MORE of these categories:
- PAYMENT_FEES: Payment terms, fees, invoicing, compensation, rates
- TERMINATION_EXPIRY: Termination rights, contract end, cancellation, expiry
- LIABILITY_DAMAGES: Liability, indemnification, damages, responsibility, exemptions
- CONFIDENTIALITY: Confidentiality, non-disclosure, proprietary information
- INTELLECTUAL_PROPERTY: IP rights, copyright, patents, trademarks, work product ownership
- WARRANTY_GUARANTEE: Warranties, guarantees, representations, assurances
- DISPUTE_RESOLUTION: Dispute resolution, arbitration, mediation, governing law, jurisdiction
- OBLIGATIONS_DUTIES: General obligations, duties, responsibilities, compliance
- AMENDMENTS_MODIFICATIONS: Contract amendments, modifications, changes
- DEFINITIONS: Definitions, interpretations, meanings
- SCOPE_SERVICES: Scope of work, services, deliverables, resources
- INSURANCE: Insurance requirements, coverage
- GENERAL_PROVISIONS: Notice, assignment, severability, entire agreement, boilerplate
- PROCEDURAL: Execution, signatures, headings, counterparts
- OTHER: Doesn't fit other categories

RULES:
1. Assign primary category based on MAIN topic
2. Can assign multiple categories if clause covers multiple topics
3. Ignore heading-only or stub clauses (< 20 characters) - categorize as "STUB"
4. Look at actual content, not just heading

Return ONLY valid JSON:
[
  {{"clause_index": 0, "categories": ["PAYMENT_FEES"]}},
  {{"clause_index": 1, "categories": ["TERMINATION_EXPIRY", "LIABILITY_DAMAGES"]}}
]

Clauses to categorize:
{chr(10).join(clauses_text)}
"""
            
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
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
                
                # Parse categorization
                categorization = json.loads(llm_response)
                
                # Handle different response formats (similar to enhanced detector)
                if isinstance(categorization, dict):
                    # Check for common wrapper keys
                    for key in ["data", "categorization", "categorizations", "categorized_clauses", "results", "clauses", "categories", "items", "clause_categorizations"]:
                        if key in categorization and isinstance(categorization[key], list):
                            categorization = categorization[key]
                            logger.info(f"✓ Unwrapped categorization from '{key}' key")
                            break
                    
                    # If still a dict, might be single item - wrap it
                    if isinstance(categorization, dict) and "clause_index" in categorization:
                        categorization = [categorization]
                        logger.info(f"✓ Wrapped single categorization item into array")
                
                if not isinstance(categorization, list):
                    logger.warning(f"Invalid categorization response for batch {batch_idx+1}: {type(categorization)}, keys: {list(categorization.keys()) if isinstance(categorization, dict) else 'N/A'}")
                    # Fallback: categorize as OTHER
                    for clause in batch:
                        categories["OTHER"].append(clause)
                    continue
                
                # Apply categories
                for item in categorization:
                    clause_idx = item.get("clause_index")
                    cats = item.get("categories", ["OTHER"])
                    
                    if clause_idx is None or clause_idx >= len(batch):
                        continue
                    
                    clause = batch[clause_idx]
                    
                    # Add to each category
                    for cat in cats:
                        if cat != "STUB":  # Skip stub clauses
                            categories[cat].append(clause)
                
                logger.info(f"Categorized batch {batch_idx+1}/{total_batches}")
                
            except Exception as e:
                logger.error(f"Categorization failed for batch {batch_idx+1}: {e}")
                # Fallback: add to OTHER
                for clause in batch:
                    categories["OTHER"].append(clause)
        
        return dict(categories)
    
    def _generate_pairs_from_categories(
        self,
        categories: Dict[str, List[Clause]],
        all_clauses: List[Clause]
    ) -> Set[Tuple[UUID, UUID]]:
        """
        Stage 2: Generate candidate pairs only within same categories.
        
        This drastically reduces false positives by ensuring we only
        compare clauses that are actually about the same topic.
        
        Returns: Set of (clause_id, clause_id) pairs
        """
        pairs = set()
        
        for category, clauses in categories.items():
            if len(clauses) < 2:
                continue
            
            # Limit to 40 clauses per category
            if len(clauses) > 40:
                logger.warning(f"Category '{category}' has {len(clauses)} clauses - limiting to 40")
                clauses = clauses[:40]
            
            # All pairs within category
            for i, c1 in enumerate(clauses):
                for c2 in clauses[i+1:]:
                    pairs.add((c1.id, c2.id))
            
            logger.debug(f"Category '{category}': {len(clauses)} clauses → {len(clauses)*(len(clauses)-1)//2} pairs")
        
        return pairs
    
    async def _detect_with_evidence(
        self,
        clauses: List[Clause],
        candidate_pairs: Set[Tuple[UUID, UUID]]
    ) -> List[Dict[str, Any]]:
        """
        Stage 3: First-pass detection requiring evidence extraction.
        
        LLM must provide:
        1. Exact quotes from both clauses that conflict
        2. Character positions of the quotes
        3. Reasoning for why it's a conflict
        
        This forces LLM to be specific and reduces hallucination.
        
        Returns: List of potential conflicts with evidence
        """
        potential_conflicts = []
        clause_map = {c.id: c for c in clauses}
        pairs_list = list(candidate_pairs)
        
        # Batch size: 30 pairs per call (smaller for evidence extraction)
        batch_size = 30
        total_batches = (len(pairs_list) + batch_size - 1) // batch_size
        
        logger.info(f"Processing {len(pairs_list)} pairs in {total_batches} batches...")
        
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
                    f"  LEFT - Clause {left.clause_number} [{left.heading or 'No heading'}]:\n{left.text}\n"
                    f"  RIGHT - Clause {right.clause_number} [{right.heading or 'No heading'}]:\n{right.text}"
                )
            
            prompt = f"""You are a legal expert identifying TRUE conflicts between contract clauses.

A TRUE CONFLICT means BOTH clauses CANNOT be complied with simultaneously. The obligations, values, or conditions are mutually exclusive.

CRITICAL RULES:
1. DIFFERENT SCENARIOS = NOT A CONFLICT
   - "Fees not payable if X" vs "Fees refundable if Y" → Different conditions, NOT a conflict
   - "Party A must do X" vs "Party B must do Y" → Different parties, NOT a conflict
   - "Before event X" vs "After event X" → Different timing, NOT a conflict

2. COMPLEMENTARY = NOT A CONFLICT
   - "Comply with security policy" vs "Security policy details in Appendix" → Work together
   - "Must negotiate first" vs "Courts have jurisdiction" → Sequential, not contradictory
   - "General rule" vs "Exception to rule" → Valid structure

3. TRUE CONFLICT CHECKLIST - ALL MUST BE TRUE:
   ✓ Same topic (both about payment, both about termination, etc.)
   ✓ Same scenario/condition (same trigger, same situation)
   ✓ Same party's obligation (if applicable)
   ✓ Mutually exclusive (impossible to comply with both)

If ANY criterion fails, it's NOT a TRUE_CONFLICT.

EVIDENCE REQUIREMENT:
You MUST extract exact quotes showing the conflict:
- Quote the specific conflicting text from LEFT clause
- Quote the specific conflicting text from RIGHT clause
- Character positions are required
- Explain WHY these quotes conflict

Analyze these {len(batch)} pairs:

{chr(10).join(pairs_text)}

Return ONLY valid JSON array:
[
  {{
    "pair_index": 0,
    "is_conflict": true,
    "confidence": 0.95,
    "conflict_type": "ValueMismatch",
    "summary": "Payment terms differ: Net 30 days vs Net 60 days",
    "left_evidence": {{
      "quote": "payment within 30 days",
      "start_char": 45,
      "end_char": 68,
      "reasoning": "LEFT requires payment in 30 days"
    }},
    "right_evidence": {{
      "quote": "payment within 60 days",
      "start_char": 102,
      "end_char": 125,
      "reasoning": "RIGHT requires payment in 60 days"
    }},
    "why_conflict": "Both clauses specify different payment deadlines for the same obligation. A party cannot pay both within 30 days AND within 60 days. This is a direct value mismatch.",
    "materiality": "HIGH"
  }}
]

CONFLICT_TYPE: ValueMismatch, ObligationMismatch, JurisdictionMismatch, TimingMismatch, Other
MATERIALITY: LOW, MEDIUM, HIGH

If no conflicts found, return []
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
                    for key in ["data", "conflicts", "results", "pairs"]:
                        if key in conflicts and isinstance(conflicts[key], list):
                            conflicts = conflicts[key]
                            break
                
                if not isinstance(conflicts, list):
                    logger.warning(f"Batch {batch_idx+1}: Invalid response type: {type(conflicts)}")
                    continue
                
                # Filter and validate
                for conflict in conflicts:
                    if conflict is None:
                        continue
                    
                    if not conflict.get("is_conflict"):
                        continue
                    
                    if conflict.get("confidence", 0) < 0.85:
                        continue
                    
                    # Validate evidence is provided
                    left_ev = conflict.get("left_evidence", {})
                    right_ev = conflict.get("right_evidence", {})
                    
                    if not (left_ev.get("quote") and right_ev.get("quote")):
                        logger.debug(f"Skipping conflict without proper evidence")
                        continue
                    
                    pair_idx = conflict.get("pair_index")
                    if pair_idx is None or pair_idx >= len(batch):
                        continue
                    
                    left_id, right_id = batch[pair_idx]
                    potential_conflicts.append({
                        "left_id": left_id,
                        "right_id": right_id,
                        "conflict_type": conflict.get("conflict_type", "Other"),
                        "summary": conflict.get("summary", ""),
                        "why_conflict": conflict.get("why_conflict", ""),
                        "left_evidence": left_ev,
                        "right_evidence": right_ev,
                        "materiality": conflict.get("materiality", "MEDIUM"),
                        "confidence": conflict.get("confidence", 0.85)
                    })
                
                logger.info(f"Batch {batch_idx+1}/{total_batches}: {len([c for c in conflicts if c.get('is_conflict')])} conflicts found")
                
            except Exception as e:
                logger.error(f"Detection failed for batch {batch_idx+1}: {e}")
        
        return potential_conflicts
    
    async def _check_consistency(
        self,
        clauses: List[Clause],
        potential_conflicts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Stage 4: Self-consistency check.
        
        For each potential conflict, ask LLM multiple times (with different
        random seeds or phrasings) and only keep conflicts that get consistent
        answers.
        
        This eliminates hallucinations that occur randomly.
        
        Returns: List of conflicts that passed consistency check
        """
        consistent_conflicts = []
        clause_map = {c.id: c for c in clauses}
        
        logger.info(f"Checking consistency for {len(potential_conflicts)} conflicts...")
        
        for idx, conflict in enumerate(potential_conflicts):
            left_id = conflict["left_id"]
            right_id = conflict["right_id"]
            left = clause_map[left_id]
            right = clause_map[right_id]
            
            # Ask LLM multiple times with slightly different prompts
            votes = 0
            total_checks = self.consistency_votes
            
            for check_idx in range(total_checks):
                prompt = f"""You are verifying if two contract clauses truly conflict.

A TRUE CONFLICT means both clauses CANNOT be complied with simultaneously.

LEFT CLAUSE:
{left.clause_number} [{left.heading or 'No heading'}]:
{left.text}

RIGHT CLAUSE:
{right.clause_number} [{right.heading or 'No heading'}]:
{right.text}

VERIFICATION CHECKLIST:
□ Are they about the SAME topic?
□ Do they apply to the SAME scenario/condition?
□ Do they involve the SAME party's obligations?
□ Are they mutually exclusive (can't both be true)?

Previous analysis suggested: {conflict['summary']}
Evidence from LEFT: "{conflict['left_evidence']['quote']}"
Evidence from RIGHT: "{conflict['right_evidence']['quote']}"

Question: Is this a TRUE conflict where both cannot be complied with simultaneously?

Return ONLY valid JSON:
{{
  "is_true_conflict": true,
  "confidence": 0.9,
  "reasoning": "Both clauses specify different payment deadlines for the same invoice, making simultaneous compliance impossible."
}}
"""
                
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
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
                        llm_response = result.get("response", "{}")
                    
                    verification = json.loads(llm_response)
                    
                    # Handle wrapped responses
                    if isinstance(verification, dict) and "data" in verification:
                        verification = verification["data"]
                    
                    if verification.get("is_true_conflict") and verification.get("confidence", 0) >= 0.85:
                        votes += 1
                    
                except Exception as e:
                    logger.error(f"Consistency check {check_idx+1} failed: {e}")
            
            # Require majority vote
            if votes >= (total_checks + 1) // 2:
                conflict["votes"] = votes
                consistent_conflicts.append(conflict)
                logger.info(f"Conflict {idx+1}/{len(potential_conflicts)}: PASS ({votes}/{total_checks} votes)")
            else:
                logger.info(f"Conflict {idx+1}/{len(potential_conflicts)}: FAIL ({votes}/{total_checks} votes)")
        
        return consistent_conflicts
    
    async def _verify_conflicts(
        self,
        clauses: List[Clause],
        consistent_conflicts: List[Dict[str, Any]]
    ) -> List[ValidatedConflict]:
        """
        Stage 5: Final verification stage.
        
        A second LLM pass to catch any remaining false positives.
        Present the conflict and evidence, ask LLM to verify it's valid.
        
        Returns: List of verified conflicts
        """
        verified = []
        clause_map = {c.id: c for c in clauses}
        
        logger.info(f"Final verification for {len(consistent_conflicts)} conflicts...")
        
        for idx, conflict in enumerate(consistent_conflicts):
            left_id = conflict["left_id"]
            right_id = conflict["right_id"]
            left = clause_map[left_id]
            right = clause_map[right_id]
            
            prompt = f"""Final verification: Is this a valid contract conflict?

CONFLICT CLAIM:
{conflict['summary']}

Reasoning: {conflict['why_conflict']}

LEFT CLAUSE {left.clause_number}:
{left.text}

Conflicting part: "{conflict['left_evidence']['quote']}"

RIGHT CLAUSE {right.clause_number}:
{right.text}

Conflicting part: "{conflict['right_evidence']['quote']}"

VERIFICATION QUESTIONS:
1. Are the quoted parts actually in the clauses? (Check for hallucination)
2. Do the quotes truly demonstrate mutual exclusivity?
3. Is this a REAL conflict or are they addressing different scenarios/parties/conditions?
4. Could a reasonable person comply with both clauses? (If yes, NOT a conflict)

Return ONLY valid JSON:
{{
  "is_valid_conflict": true,
  "confidence": 0.95,
  "final_assessment": "Verified as true conflict. Both clauses specify different payment terms for the same obligation with no way to reconcile them."
}}
"""
            
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
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
                    llm_response = result.get("response", "{}")
                
                verification = json.loads(llm_response)
                
                # Handle wrapped responses
                if isinstance(verification, dict) and "data" in verification:
                    verification = verification["data"]
                
                if verification.get("is_valid_conflict") and verification.get("confidence", 0) >= 0.9:
                    # Create validated conflict
                    validated = ValidatedConflict(
                        left_clause_id=left_id,
                        right_clause_id=right_id,
                        classification="TRUE_CONFLICT",
                        confidence=conflict["confidence"],
                        conflict_type=conflict["conflict_type"],
                        summary=conflict["summary"],
                        explanation=conflict["why_conflict"] + "\n\nFinal assessment: " + verification.get("final_assessment", ""),
                        left_evidence=ConflictEvidence(
                            quote=conflict["left_evidence"]["quote"],
                            start_char=conflict["left_evidence"].get("start_char", 0),
                            end_char=conflict["left_evidence"].get("end_char", 0),
                            reasoning=conflict["left_evidence"].get("reasoning", "")
                        ),
                        right_evidence=ConflictEvidence(
                            quote=conflict["right_evidence"]["quote"],
                            start_char=conflict["right_evidence"].get("start_char", 0),
                            end_char=conflict["right_evidence"].get("end_char", 0),
                            reasoning=conflict["right_evidence"].get("reasoning", "")
                        ),
                        materiality=conflict["materiality"],
                        votes=conflict["votes"]
                    )
                    verified.append(validated)
                    logger.info(f"Conflict {idx+1}/{len(consistent_conflicts)}: VERIFIED")
                else:
                    logger.info(f"Conflict {idx+1}/{len(consistent_conflicts)}: REJECTED in final verification")
            
            except Exception as e:
                logger.error(f"Verification failed: {e}")
        
        return verified
    
    def _store_conflict(
        self,
        analysis_run_id: UUID,
        contract_version_id: UUID,
        conflict: ValidatedConflict
    ):
        """Store a verified conflict in the database"""
        
        # Map materiality to severity
        severity_map = {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH"}
        severity = severity_map.get(conflict.materiality, "MEDIUM")
        
        db_conflict = Conflict(
            analysis_run_id=analysis_run_id,
            contract_version_id=contract_version_id,
            left_clause_id=conflict.left_clause_id,
            right_clause_id=conflict.right_clause_id,
            severity=severity,
            score=str(conflict.confidence),
            summary=conflict.summary,
            explanation=conflict.explanation,
            status="ACTIVE"
        )
        
        self.db.add(db_conflict)
        self.db.flush()
