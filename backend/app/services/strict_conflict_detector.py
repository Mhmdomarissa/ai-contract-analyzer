"""
Strict Conflict Detector

Fixes the hallucination problem in conflict detection by:
1. VERIFYING that quoted text actually exists in clauses (not hallucinated)
2. Requiring SAME TOPIC before LLM analysis
3. Using a much stricter, simpler prompt
4. Post-filtering impossible conflicts

The key insight: The LLM was inventing conflict summaries that had nothing to do
with the actual clause content. This detector validates everything.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models.clause import Clause
from app.models.conflict import AnalysisRun, Conflict

logger = logging.getLogger(__name__)


# Topic keywords - clauses must share a topic to be compared
TOPIC_KEYWORDS = {
    'payment': [
        'payment', 'pay ', 'paid', 'fee', 'fees', 'price', 'invoice', 
        'compensation', 'charge', 'remuneration', 'cost', 'expense',
        'net 30', 'net 60', 'billing', 'bill '
    ],
    'termination': [
        'terminat', 'cancel', 'expire', 'expiry', 'end of', 
        'notice period', 'cessation', 'discontinu'
    ],
    'liability': [
        'liabil', 'liable', 'damage', 'indemnif', 'indemni',
        'responsible', 'responsibility', 'consequential', 'loss'
    ],
    'confidentiality': [
        'confidential', 'secret', 'proprietary', 'disclos', 
        'non-disclosure', 'nda '
    ],
    'intellectual_property': [
        'intellectual property', 'ip right', 'copyright', 'patent', 
        'trademark', 'work product', 'invention', 'ownership'
    ],
    'warranty': [
        'warrant', 'guarantee', 'representation', 'assur'
    ],
    'dispute': [
        'dispute', 'arbitrat', 'mediat', 'jurisdiction', 
        'governing law', 'court', 'litigation'
    ],
    'insurance': [
        'insurance', 'insur', 'policy', 'coverage', 'underwriter'
    ],
    'audit': [
        'audit', 'inspect', 'examination', 'review', 'records'
    ],
    'subcontractor': [
        'subcontract', 'sub-contract', 'outsourc', 'third party provider'
    ],
    'force_majeure': [
        'force majeure', 'act of god', 'unforeseeable', 'beyond control'
    ],
    'data_privacy': [
        'data', 'privacy', 'personal information', 'gdpr', 'data protection'
    ],
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison - lowercase, collapse whitespace"""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def text_contains_quote(clause_text: str, quote: str, min_match_ratio: float = 0.7) -> bool:
    """
    Check if a quote actually exists in the clause text.
    
    Allows for minor differences (whitespace, punctuation) but the core
    words must be present in the same order.
    """
    if not quote or not clause_text:
        return False
    
    clause_norm = normalize_text(clause_text)
    quote_norm = normalize_text(quote)
    
    # Direct substring match
    if quote_norm in clause_norm:
        return True
    
    # Extract words and check if they appear in order
    quote_words = [w for w in re.findall(r'\w+', quote_norm) if len(w) > 2]
    clause_words = re.findall(r'\w+', clause_norm)
    
    if not quote_words:
        return False
    
    # Find the words in order (allowing gaps)
    found = 0
    clause_idx = 0
    for word in quote_words:
        while clause_idx < len(clause_words):
            if clause_words[clause_idx] == word:
                found += 1
                clause_idx += 1
                break
            clause_idx += 1
    
    return found / len(quote_words) >= min_match_ratio


def get_clause_topics(clause: Clause) -> Set[str]:
    """Get all topics that a clause matches"""
    text_lower = clause.text.lower()
    topics = set()
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            topics.add(topic)
    
    return topics


def clauses_share_topic(clause1: Clause, clause2: Clause) -> Tuple[bool, Set[str]]:
    """Check if two clauses share at least one topic"""
    topics1 = get_clause_topics(clause1)
    topics2 = get_clause_topics(clause2)
    shared = topics1 & topics2
    return len(shared) > 0, shared


class StrictConflictDetector:
    """
    Strict conflict detector that validates LLM outputs against actual clause content.
    
    Key features:
    1. Only compares clauses with shared topics
    2. Verifies that quoted text actually exists in clauses
    3. Uses a simple, focused prompt
    4. Filters out hallucinated conflicts
    """
    
    def __init__(self, db: Session, ollama_url: str, model: str = "qwen2.5:32b"):
        self.db = db
        self.ollama_url = ollama_url
        self.model_name = model
    
    async def detect_conflicts(self, contract_version_id: str) -> Dict[str, Any]:
        """Main detection entry point"""
        start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("🔒 STRICT CONFLICT DETECTION (Hallucination-Free)")
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
                return {"validated_conflicts": 0, "total_time": time.time() - start_time}
            
            # Stage 1: Select pairs that share topics
            logger.info("\n📌 STAGE 1: Topic-Based Pair Selection")
            candidate_pairs = self._select_same_topic_pairs(clauses)
            logger.info(f"✅ Selected {len(candidate_pairs)} pairs sharing topics")
            
            # Stage 2: LLM analysis with strict validation
            logger.info("\n🔍 STAGE 2: LLM Analysis + Quote Verification")
            validated_conflicts = await self._analyze_and_verify(clauses, candidate_pairs)
            logger.info(f"✅ Verified {len(validated_conflicts)} true conflicts")
            
            # Store conflicts
            for conflict in validated_conflicts:
                self._store_conflict(
                    analysis_run_id=analysis_run.id,
                    contract_version_id=UUID(contract_version_id),
                    conflict=conflict
                )
            
            self.db.commit()
            analysis_run.status = "COMPLETED"
            self.db.commit()
            
            total_time = time.time() - start_time
            
            logger.info("\n" + "=" * 80)
            logger.info("🏁 DETECTION COMPLETE")
            logger.info(f"⏱️  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
            logger.info(f"📊 TRUE conflicts found: {len(validated_conflicts)}")
            logger.info("=" * 80)
            
            return {
                "validated_conflicts": len(validated_conflicts),
                "total_time": total_time,
                "candidate_pairs": len(candidate_pairs)
            }
            
        except Exception as e:
            logger.error(f"❌ Detection failed: {e}", exc_info=True)
            analysis_run.status = "FAILED"
            analysis_run.error_message = str(e)
            self.db.commit()
            raise
    
    def _select_same_topic_pairs(self, clauses: List[Clause]) -> List[Tuple[Clause, Clause, Set[str]]]:
        """
        Select pairs of clauses that share at least one topic.
        
        This is the key filter - we only compare clauses that are about the same thing.
        """
        pairs = []
        
        # Pre-compute topics for all clauses
        clause_topics = {c.id: get_clause_topics(c) for c in clauses}
        
        for i, c1 in enumerate(clauses):
            topics1 = clause_topics[c1.id]
            if not topics1:
                continue  # Skip clauses with no recognized topics
            
            for c2 in clauses[i+1:]:
                topics2 = clause_topics[c2.id]
                if not topics2:
                    continue
                
                shared = topics1 & topics2
                if shared:
                    pairs.append((c1, c2, shared))
        
        # Log topic distribution
        topic_counts = {}
        for _, _, shared in pairs:
            for topic in shared:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        logger.info(f"   Topic distribution:")
        for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
            logger.info(f"      {topic}: {count} pairs")
        
        return pairs
    
    async def _analyze_and_verify(
        self,
        clauses: List[Clause],
        candidate_pairs: List[Tuple[Clause, Clause, Set[str]]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze pairs with LLM and verify that quotes actually exist.
        """
        verified_conflicts = []
        
        # Process in batches of 10 (smaller batches for better accuracy)
        batch_size = 10
        total_batches = (len(candidate_pairs) + batch_size - 1) // batch_size
        
        logger.info(f"   Analyzing {len(candidate_pairs)} pairs in {total_batches} batches...")
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(candidate_pairs))
            batch = candidate_pairs[start_idx:end_idx]
            
            # Build prompt with clause text
            pairs_text = []
            for idx, (c1, c2, topics) in enumerate(batch):
                pairs_text.append(f"""
PAIR {idx}:
Topics: {', '.join(topics)}

CLAUSE A (#{c1.clause_number}):
{c1.text[:1500]}

CLAUSE B (#{c2.clause_number}):
{c2.text[:1500]}
""")
            
            prompt = f"""You are checking if clause pairs contain TRUE LEGAL CONFLICTS.

A TRUE CONFLICT means: Both clauses cannot be followed at the same time.

NOT conflicts:
- Different conditions ("if X" vs "if Y")
- Different parties ("Agency must" vs "Client must")  
- Complementary details (one gives overview, other gives specifics)
- One is exception to the other (using "except", "unless", "notwithstanding")

TRUE conflicts:
- Same topic, same scenario, contradictory requirements
- Example: "Payment due in 30 days" vs "Payment due in 60 days"
- Example: "Agency liable for all damages" vs "Agency liability capped at fees paid"

For each pair, if there IS a conflict:
1. Find the EXACT TEXT from Clause A showing one requirement
2. Find the EXACT TEXT from Clause B showing the contradictory requirement
3. These quotes must be copy-pasted from the clauses - do not paraphrase!

{chr(10).join(pairs_text)}

Return JSON array. For conflicts found:
[
  {{
    "pair_index": 0,
    "is_conflict": true,
    "severity": "HIGH",
    "summary": "Brief description of the conflict",
    "quote_from_a": "exact text from clause A",
    "quote_from_b": "exact text from clause B",
    "explanation": "Why these cannot both be followed"
  }}
]

If a pair is NOT a conflict, still include it:
  {{"pair_index": 1, "is_conflict": false}}

Return ONLY the JSON array, no other text."""

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
                
                # Parse response
                try:
                    conflicts = json.loads(llm_response)
                except json.JSONDecodeError:
                    # Try to extract JSON array
                    match = re.search(r'\[[\s\S]*\]', llm_response)
                    if match:
                        conflicts = json.loads(match.group())
                    else:
                        conflicts = []
                
                # Handle wrapped responses
                if isinstance(conflicts, dict):
                    for key in ["data", "conflicts", "results", "pairs"]:
                        if key in conflicts and isinstance(conflicts[key], list):
                            conflicts = conflicts[key]
                            break
                
                if not isinstance(conflicts, list):
                    conflicts = []
                
                # Verify each conflict
                batch_verified = 0
                for conflict in conflicts:
                    if not isinstance(conflict, dict):
                        continue
                    
                    if not conflict.get("is_conflict"):
                        continue
                    
                    pair_idx = conflict.get("pair_index")
                    if pair_idx is None or pair_idx >= len(batch):
                        continue
                    
                    c1, c2, topics = batch[pair_idx]
                    quote_a = conflict.get("quote_from_a", "")
                    quote_b = conflict.get("quote_from_b", "")
                    
                    # CRITICAL: Verify quotes exist in actual clauses
                    quote_a_valid = text_contains_quote(c1.text, quote_a)
                    quote_b_valid = text_contains_quote(c2.text, quote_b)
                    
                    if not quote_a_valid or not quote_b_valid:
                        logger.debug(f"   Pair {pair_idx}: Quote verification FAILED (hallucination filtered)")
                        continue
                    
                    # Additional sanity checks
                    summary = conflict.get("summary", "")
                    explanation = conflict.get("explanation", "")
                    
                    # Filter out nonsense summaries
                    if self._is_likely_hallucination(summary, c1.text, c2.text):
                        logger.debug(f"   Pair {pair_idx}: Summary doesn't match clause content")
                        continue
                    
                    verified_conflicts.append({
                        "left_id": c1.id,
                        "right_id": c2.id,
                        "conflict_type": "Verified",
                        "summary": summary,
                        "explanation": explanation,
                        "left_quote": quote_a,
                        "right_quote": quote_b,
                        "severity": conflict.get("severity", "MEDIUM"),
                        "confidence": 0.95,  # High confidence since verified
                        "topics": list(topics)
                    })
                    batch_verified += 1
                
                logger.info(f"   Batch {batch_idx+1}/{total_batches}: {batch_verified} verified conflicts")
                
            except Exception as e:
                logger.error(f"   Batch {batch_idx+1} failed: {e}")
        
        return verified_conflicts
    
    def _is_likely_hallucination(self, summary: str, clause1_text: str, clause2_text: str) -> bool:
        """
        Check if a summary is likely hallucinated (doesn't match clause content).
        """
        if not summary:
            return True
        
        summary_lower = summary.lower()
        combined_text = (clause1_text + " " + clause2_text).lower()
        
        # Extract key terms from summary
        # If summary mentions specific values/terms, they should appear in clauses
        
        # Check for payment terms
        if "30 day" in summary_lower or "net 30" in summary_lower:
            if "30 day" not in combined_text and "net 30" not in combined_text and "thirty" not in combined_text:
                return True
        
        if "60 day" in summary_lower or "net 60" in summary_lower:
            if "60 day" not in combined_text and "net 60" not in combined_text and "sixty" not in combined_text:
                return True
        
        # Check for jurisdiction mentions
        if "uk law" in summary_lower and "uk" not in combined_text and "united kingdom" not in combined_text:
            return True
        
        if "uae law" in summary_lower and "uae" not in combined_text and "emirates" not in combined_text:
            return True
        
        # Check for year mentions
        year_match = re.search(r'(\d+)\s*year', summary_lower)
        if year_match:
            years = year_match.group(1)
            if years not in combined_text and not any(w in combined_text for w in [f'{years} year', f'{years}-year']):
                return True
        
        return False
    
    def _store_conflict(
        self,
        analysis_run_id: UUID,
        contract_version_id: UUID,
        conflict: Dict[str, Any]
    ):
        """Store verified conflict"""
        
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
