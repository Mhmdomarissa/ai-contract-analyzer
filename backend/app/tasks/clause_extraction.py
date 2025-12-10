from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.clause import Clause
from app.models.conflict import AnalysisRun
from app.models.contract import ContractVersion
from app.services import document_parser
from app.services.llm_service import LLMService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_clause_extraction(run_id: UUID) -> None:
    """Enqueue the Celery task for the provided analysis run."""
    extract_clauses_for_run.delay(str(run_id))


@celery_app.task(name="app.tasks.extract_clauses_for_run")
def extract_clauses_for_run(run_id: str) -> None:
    """Celery entry point that performs clause extraction for an analysis run."""
    asyncio.run(_run_clause_extraction(UUID(run_id)))


async def _run_clause_extraction(run_id: UUID) -> None:
    session = SessionLocal()
    try:
        run: AnalysisRun | None = (
            session.query(AnalysisRun)
            .options(
                selectinload(AnalysisRun.contract_version).selectinload(ContractVersion.file)
            )
            .filter(AnalysisRun.id == run_id)
            .one_or_none()
        )
        if not run:
            logger.error("Analysis run %s not found; skipping clause extraction", run_id)
            return

        contract_version = run.contract_version
        if not contract_version or not contract_version.file:
            logger.error("Analysis run %s missing contract version or file", run_id)
            _mark_run_failed(session, run_id, "Missing contract version/file")
            return

        logger.info(
            "Starting clause extraction for contract version %s (run %s)",
            contract_version.id,
            run_id,
        )
        run.status = "RUNNING"
        session.commit()

        file_path = contract_version.file.storage_path
        text = document_parser.parse_document(file_path)
        if not text:
            raise ValueError("Unable to extract text from document for clause extraction")

        llm = LLMService(base_url=settings.OLLAMA_URL)
        clauses_payload = await llm.extract_clauses(text)

        session.query(Clause).filter(Clause.contract_version_id == contract_version.id).delete(
            synchronize_session=False
        )

        for index, clause_data in enumerate(clauses_payload):
            # Extract metadata if present
            metadata = clause_data.get('metadata', {})
            
            # Determine if this is a special clause type
            clause_type = metadata.get('type', 'standard')
            
            # Build heading from category and metadata
            heading = clause_data.get('category', '')
            if metadata.get('has_table'):
                heading += ' [Contains Table]'
            if metadata.get('schedule_type'):
                heading = f"{metadata['schedule_type']} - {heading}"
            
            clause = Clause(
                contract_version_id=contract_version.id,
                text=clause_data.get('text', ''),
                clause_number=clause_data.get('clause_number', str(index + 1)),
                heading=heading,
                language=clause_data.get('language'),
                order_index=index,
            )
            session.add(clause)

        run.status = "COMPLETED"
        run.finished_at = datetime.utcnow()
        run.error_message = None
        session.commit()
        logger.info(
            "Clause extraction finished for contract version %s (run %s)",
            contract_version.id,
            run_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Clause extraction failed for run %s", run_id)
        session.rollback()
        _mark_run_failed(session, run_id, str(exc))
    finally:
        session.close()


def _mark_run_failed(session: Session, run_id: UUID, error_message: str) -> None:
    run = session.query(AnalysisRun).filter(AnalysisRun.id == run_id).one_or_none()
    if not run:
        logger.error("Unable to mark run %s as failed; record not found", run_id)
        return

    run.status = "FAILED"
    run.error_message = error_message[:2000]
    run.finished_at = datetime.utcnow()
    session.commit()
