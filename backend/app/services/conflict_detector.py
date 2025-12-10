import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.clause import Clause
from app.models.conflict import AnalysisRun, Conflict
from app.models.contract import ContractVersion

logger = logging.getLogger(__name__)


def save_analysis_results(
    db: Session,
    contract_version_id: UUID,
    analysis_data: dict,
    model_name: str = "qwen2.5:32b"
) -> None:
    """
    Save the results of the LLM analysis (clauses and conflicts) to the database.
    """
    try:
        # 1. Create Analysis Run
        run = AnalysisRun(
            contract_version_id=contract_version_id,
            type="CONFLICT_DETECTION",
            model_name=model_name,
            status="COMPLETED",
            finished_at=datetime.now()
        )
        db.add(run)
        db.flush()  # Get ID

        # 2. Save Clauses
        # Map temporary IDs from LLM to real UUIDs
        temp_id_map = {}
        
        clauses_data = analysis_data.get("clauses", [])
        for i, clause_data in enumerate(clauses_data):
            clause = Clause(
                contract_version_id=contract_version_id,
                text=clause_data.get("text", ""),
                # category=clause_data.get("category", "General"), # Removed as it's not in model
                clause_number=str(i + 1),
                order_index=i
            )
            db.add(clause)
            db.flush()
            temp_id = clause_data.get("id")
            if temp_id:
                temp_id_map[temp_id] = clause.id

        # 3. Save Conflicts
        conflicts_data = analysis_data.get("conflicts", [])
        for conflict_data in conflicts_data:
            c1_temp_id = conflict_data.get("clause_id_1")
            c2_temp_id = conflict_data.get("clause_id_2")
            
            c1_id = temp_id_map.get(c1_temp_id)
            c2_id = temp_id_map.get(c2_temp_id)
            
            if c1_id and c2_id:
                conflict = Conflict(
                    analysis_run_id=run.id,
                    contract_version_id=contract_version_id,
                    left_clause_id=c1_id,
                    right_clause_id=c2_id,
                    explanation=conflict_data.get("explanation", ""),
                    severity=conflict_data.get("severity", "MEDIUM").upper(),
                    # category="LOGICAL" # Removed as it's not in model
                )
                db.add(conflict)
            else:
                logger.warning(f"Could not map clause IDs for conflict: {c1_temp_id}, {c2_temp_id}")

        db.commit()
        logger.info(f"Saved analysis results for version {contract_version_id}")

    except Exception as e:
        logger.error(f"Error saving analysis results: {e}")
        db.rollback()
        raise


