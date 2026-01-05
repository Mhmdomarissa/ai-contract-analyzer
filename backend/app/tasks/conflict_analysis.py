import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery_app
from app.db.session import SessionLocal
from app.core.config import settings
from app.models.conflict import AnalysisRun
from app.services import contracts as contract_service

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.analyze_contract_conflicts", bind=True)
def analyze_contract_conflicts(self, run_id: str, strategy: str = "fast_accurate") -> dict:
    """
    Celery task for asynchronous conflict detection.
    
    Args:
        run_id: UUID of the AnalysisRun
        strategy: Detection strategy (fast_accurate or accurate)
    
    Returns:
        dict with results summary
    """
    db = SessionLocal()
    try:
        logger.info(f"🚀 Starting conflict detection task for run_id={run_id}, strategy={strategy}")
        
        # Get the analysis run
        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if not run:
            logger.error(f"AnalysisRun {run_id} not found")
            return {"error": "AnalysisRun not found"}
        
        # Update status to RUNNING
        run.status = "RUNNING"
        db.commit()
        
        # Get the contract version
        contract_version_id = str(run.contract_version_id)
        
        # Get clauses
        clauses = contract_service.list_clauses_for_version(db, run.contract_version_id)
        if not clauses:
            logger.error(f"No clauses found for version {contract_version_id}")
            run.status = "FAILED"
            run.error_message = "No clauses found. Run extraction first."
            db.commit()
            return {"error": "No clauses found"}
        
        logger.info(f"📊 Processing {len(clauses)} clauses with strategy: {strategy}")
        
        # Choose and run detector
        if strategy == "accurate":
            from app.services.accurate_conflict_detector import AccurateConflictDetector
            
            detector = AccurateConflictDetector(
                db=db,
                ollama_url=settings.OLLAMA_URL,
                model="qwen2.5:32b",
                consistency_votes=2
            )
        elif strategy == "strict":
            # Strict detector with hallucination filtering
            from app.services.strict_conflict_detector import StrictConflictDetector
            
            detector = StrictConflictDetector(
                db=db,
                ollama_url=settings.OLLAMA_URL,
                model="qwen2.5:32b"
            )
        else:  # Default to STRICT (was fast_accurate but had hallucination issues)
            from app.services.strict_conflict_detector import StrictConflictDetector
            
            detector = StrictConflictDetector(
                db=db,
                ollama_url=settings.OLLAMA_URL,
                model="qwen2.5:32b"
            )
        
        # Run detection - this is synchronous within the Celery task
        # We need to call it synchronously since Celery workers aren't async
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(detector.detect_conflicts(contract_version_id))
        loop.close()
        
        logger.info(f"✅ Conflict detection complete:")
        logger.info(f"   Strategy: {result.get('strategy', 'unknown')}")
        conflicts_count = result.get('conflicts_detected', result.get('validated_conflicts', 0))
        logger.info(f"   Conflicts detected: {conflicts_count}")
        
        duration = result.get('duration_seconds', result.get('total_time', 0))
        if duration:
            logger.info(f"   Duration: {duration:.1f}s ({duration/60:.1f} minutes)")
        
        # Update run status
        from datetime import datetime
        run.status = "COMPLETED"
        run.finished_at = datetime.utcnow()
        db.commit()
        
        return {
            "run_id": run_id,
            "status": "completed",
            "conflicts_detected": conflicts_count,
            "duration_seconds": duration,
            "strategy": strategy
        }
        
    except Exception as e:
        logger.error(f"❌ Error in conflict detection task: {e}", exc_info=True)
        
        # Update run status to failed
        if 'run' in locals():
            run.status = "FAILED"
            run.error_message = str(e)
            db.commit()
        
        return {"error": str(e), "run_id": run_id}
        
    finally:
        db.close()

