from __future__ import annotations

import asyncio
import logging
import re
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


def separate_bilingual_text(text: str) -> tuple[str, str | None, bool]:
    """
    Separate bilingual text into English and Arabic.
    
    Args:
        text: Text that may contain both English and Arabic
        
    Returns:
        Tuple of (english_text, arabic_text, is_bilingual)
        - english_text: English portion (or original text if not bilingual)
        - arabic_text: Arabic portion (None if not bilingual)
        - is_bilingual: True if both languages detected
    """
    if not text:
        return text, None, False
    
    # Check if text contains Arabic characters (Unicode range \u0600-\u06FF)
    has_arabic = any('\u0600' <= char <= '\u06FF' for char in text)
    has_english = any(char.isascii() and char.isalpha() for char in text)
    
    if not has_arabic or not has_english:
        # Not bilingual - return original text
        return text, None, False
    
    # Try to separate by common patterns
    # Pattern 1: Lines with Arabic only vs lines with English only
    lines = text.split('\n')
    english_lines = []
    arabic_lines = []
    mixed_lines = []
    
    for line in lines:
        line_has_arabic = any('\u0600' <= char <= '\u06FF' for char in line)
        line_has_english = any(char.isascii() and char.isalpha() for char in line)
        
        if line_has_arabic and line_has_english:
            # Mixed line - try to separate by words
            words = line.split()
            eng_words = []
            arb_words = []
            
            for word in words:
                if any('\u0600' <= char <= '\u06FF' for char in word):
                    arb_words.append(word)
                else:
                    eng_words.append(word)
            
            if eng_words:
                english_lines.append(' '.join(eng_words))
            if arb_words:
                arabic_lines.append(' '.join(arb_words))
        elif line_has_arabic:
            arabic_lines.append(line)
        elif line_has_english:
            english_lines.append(line)
        else:
            # Empty or special characters - keep in both
            if line.strip():
                english_lines.append(line)
                arabic_lines.append(line)
    
    # Build separated texts
    english_text = '\n'.join(english_lines).strip() if english_lines else text
    arabic_text = '\n'.join(arabic_lines).strip() if arabic_lines else None
    
    # If separation didn't work well, use heuristics
    if not arabic_text or len(arabic_text) < len(text) * 0.1:
        # Try alternative: split by common bilingual patterns
        # Look for patterns like "English text\nArabic text" or side-by-side
        
        # Pattern: Check if text has clear separation (e.g., table format)
        # For now, if we can't cleanly separate, keep original in text field
        # and extract Arabic separately
        arabic_chars_only = ''.join([char for char in text if '\u0600' <= char <= '\u06FF' or char.isspace()])
        arabic_text_clean = ' '.join(arabic_chars_only.split()).strip()
        
        if len(arabic_text_clean) > 10:  # Minimum Arabic content
            arabic_text = arabic_text_clean
        else:
            arabic_text = None
    
    is_bilingual = arabic_text is not None and len(arabic_text) > 0
    
    # If separation failed, keep original in text and mark as not bilingual
    if not is_bilingual:
        return text, None, False
    
    return english_text, arabic_text, True


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
        
        # Parse document using PyMuPDF extractor with table extraction
        from app.services.parsers.pdf_parser import AdvancedPdfParser
        from app.services.parsers.docx_parser import AdvancedDocxParser
        import os
        
        extracted_tables = []
        file_ext = os.path.splitext(file_path)[1].lower() if file_path else ''
        
        if file_ext == '.pdf':
            # Use document_parser which uses PyMuPDF
            # But also extract tables separately
            try:
                # First, use document_parser for text (with PyMuPDF)
                text = document_parser.parse_document(file_path)
                
                # Then extract tables separately for linking
                parser = AdvancedPdfParser(
                    use_ocr=True,
                    layout_recognition=True,
                    extract_tables=True
                )
                # Parse again just for tables (fast, doesn't duplicate text extraction)
                parser.parse(file_path=file_path)
                extracted_tables = parser.get_extracted_tables()
                logger.info(f"Extracted {len(extracted_tables)} tables from PDF")
            except Exception as e:
                logger.warning(f"Table extraction failed: {e}, using standard parser")
                text = document_parser.parse_document(file_path)
        elif file_ext in ['.docx', '.doc']:
            try:
                parser = AdvancedDocxParser(extract_tables=True)
                text = parser.parse(file_path=file_path)
                extracted_tables = parser.get_extracted_tables()
                logger.info(f"Extracted {len(extracted_tables)} tables from DOCX")
            except Exception as e:
                logger.warning(f"Table extraction failed: {e}, using standard parser")
                text = document_parser.parse_document(file_path)
        else:
            text = document_parser.parse_document(file_path)
        
        if not text:
            raise ValueError("Unable to extract text from document for clause extraction")

        llm = LLMService(base_url=settings.OLLAMA_URL)
        
        # Enable validation for production quality
        # Set to False for faster extraction during development
        enable_validation = settings.ENABLE_CLAUSE_VALIDATION if hasattr(settings, 'ENABLE_CLAUSE_VALIDATION') else True
        
        logger.info(f"Extracting clauses (validation: {enable_validation})...")
        clauses_payload = await llm.extract_clauses(
            text, 
            enable_validation=enable_validation
        )
        
        logger.info(f"Extracted {len(clauses_payload)} clauses")
        
        # Note: Legal-BERT validation removed - not providing useful filtering
        # DocFormer and regex extraction are trusted directly
        
        # Link tables to clauses
        if extracted_tables:
            from app.services.table_extractor import TableExtractor
            table_extractor = TableExtractor()
            
            logger.info(f"Linking {len(extracted_tables)} extracted tables to {len(clauses_payload)} clauses")
            total_linked = 0
            
            for clause in clauses_payload:
                clause_text = clause.get('text', '')
                clause_number = clause.get('clause_number', 'unknown')
                linked_tables = table_extractor.find_tables_in_text(clause_text, extracted_tables)
                
                if linked_tables:
                    # Add table references to metadata
                    if 'metadata' not in clause:
                        clause['metadata'] = {}
                    
                    clause['metadata']['linked_tables'] = [
                        {
                            'table_id': table.get('table_id'),
                            'method': table.get('method'),
                            'headers': table.get('headers', []),
                            'row_count': table.get('row_count', 0),
                            'column_count': table.get('column_count', 0),
                            'formatted_text': table.get('formatted_text', '')[:500]  # First 500 chars for preview
                        }
                        for table in linked_tables
                    ]
                    clause['metadata']['has_table'] = True
                    total_linked += len(linked_tables)
                    logger.info(f"Linked {len(linked_tables)} table(s) to clause {clause_number}")
            
            logger.info(f"Total: {total_linked} table-clause links created")
        else:
            logger.info("No tables extracted, skipping table linking")

        session.query(Clause).filter(Clause.contract_version_id == contract_version.id).delete(
            synchronize_session=False
        )

        for index, clause_data in enumerate(clauses_payload):
            # Extract metadata if present
            metadata = clause_data.get('metadata', {})
            validation = clause_data.get('validation', {})
            
            # Determine if this is a special clause type
            clause_type = metadata.get('type', 'standard')
            
            # Build heading from category and metadata
            heading = clause_data.get('category', '')
            if metadata.get('has_table'):
                heading += ' [Contains Table]'
            if metadata.get('schedule_type'):
                heading = f"{metadata['schedule_type']} - {heading}"
            
            # Add validation quality indicator
            if validation and 'quality_score' in validation:
                quality_score = validation['quality_score']
                if quality_score >= 0.8:
                    quality_indicator = '✓'
                elif quality_score >= 0.5:
                    quality_indicator = '~'
                else:
                    quality_indicator = '!'
                heading = f"{quality_indicator} {heading}"
            
            # Truncate clause_number to 50 characters (database constraint)
            clause_number = clause_data.get('clause_number', str(index + 1))
            if clause_number and len(clause_number) > 50:
                clause_number = clause_number[:47] + '...'  # Truncate to 47 + '...' = 50
            
            # Separate bilingual content if present
            original_text = clause_data.get('text', '')
            english_text, arabic_text, is_bilingual = separate_bilingual_text(original_text)
            
            # For backward compatibility: text field contains both languages for LLM
            # But we also store separated versions
            clause = Clause(
                contract_version_id=contract_version.id,
                text=original_text,  # Keep original with both languages for LLM compatibility
                arabic_text=arabic_text,  # Separated Arabic text
                is_bilingual=is_bilingual,
                clause_number=clause_number,
                heading=heading,
                language=clause_data.get('language') or ('bilingual' if is_bilingual else 'en'),
                order_index=index,
            )
            session.add(clause)
        
        # Log extraction statistics
        if enable_validation:
            avg_quality = sum(
                c.get('validation', {}).get('quality_score', 0) 
                for c in clauses_payload
            ) / max(len(clauses_payload), 1)
            logger.info(f"Average clause quality: {avg_quality:.2f}")
            
            issues_count = sum(
                len(c.get('validation', {}).get('issues', []))
                for c in clauses_payload
            )
            if issues_count > 0:
                logger.warning(f"Found {issues_count} validation issues across clauses")

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
