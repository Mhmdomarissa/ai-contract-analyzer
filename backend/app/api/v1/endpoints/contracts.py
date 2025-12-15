from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.api.v1.dependencies import get_db
from app.core.config import settings
from app.schemas.clause import ClauseExtractionJobRead, ClauseRead
from app.schemas.conflict import AnalysisRunRead, ConflictRead
from app.schemas.contract import (
    ContractCreate,
    ContractFileCreate,
    ContractRead,
    ContractVersionRead,
)
from app.models.contract import ContractVersion
from app.models.clause import Clause
from app.models.conflict import Conflict, AnalysisRun
from app.services import contracts as contract_service
from app.services import document_parser
from app.services.document_parser import (
    DocumentParsingError,
    FileSizeError,
    FileTypeError,
    EncryptedFileError,
    EmptyContentError
)
from app.tasks.clause_extraction import enqueue_clause_extraction
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", response_model=ContractRead, status_code=201)
async def upload_contract(
    file: UploadFile = File(...),
    title: str = Form(...),
    db: Session = Depends(get_db)
) -> ContractRead:
    """
    Upload and parse a contract document.
    
    Validates file size, type, and encryption before processing.
    Extracts text content and creates contract record in database.
    """
    # 1. Pre-upload validation
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required"
        )
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in document_parser.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. "
                   f"Supported types: {', '.join(sorted(document_parser.SUPPORTED_EXTENSIONS))}"
        )
    
    # 2. Save the file locally
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    finally:
        file.file.close()
    
    file_size = file_path.stat().st_size
    
    # 3. Validate file size early (before DB creation)
    file_size_mb = file_size / (1024 * 1024)
    if file_size_mb > document_parser.MAX_FILE_SIZE_MB:
        # Clean up the file
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed "
                   f"({document_parser.MAX_FILE_SIZE_MB}MB)"
        )
    
    # 4. Create Contract in DB
    contract_in = ContractCreate(
        title=title,
        file=ContractFileCreate(
            storage_path=str(file_path),
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size_bytes=file_size
        )
    )
    
    try:
        contract = contract_service.create_contract_with_file_and_version(db, contract_in)
        db.commit()
        db.refresh(contract)
    except Exception as e:
        logger.error(f"Failed to create contract in database: {e}")
        # Clean up the file
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create contract record: {str(e)}"
        )
    
    # 5. Parse Document with comprehensive error handling
    parsed_text = None
    parsing_error = None
    
    try:
        logger.info(f"Parsing document: {file.filename} ({file_size_mb:.1f}MB)")
        parsed_text = document_parser.parse_document(str(file_path))
        logger.info(f"✅ Successfully extracted {len(parsed_text)} characters")
        
        # Save parsed text to the version
        latest_version = db.query(ContractVersion).filter(
            ContractVersion.contract_id == contract.id,
            ContractVersion.is_current == True
        ).first()
        
        if latest_version and parsed_text:
            latest_version.parsed_text = parsed_text
            db.commit()
            db.refresh(latest_version)
            
    except EncryptedFileError as e:
        parsing_error = str(e)
        logger.error(f"Encrypted file uploaded: {e}")
        # Rollback the contract creation
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
        
    except FileSizeError as e:
        parsing_error = str(e)
        logger.error(f"File size error: {e}")
        # Rollback the contract creation
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e)
        )
        
    except FileTypeError as e:
        parsing_error = str(e)
        logger.error(f"File type error: {e}")
        # Rollback the contract creation
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
        
    except EmptyContentError as e:
        parsing_error = str(e)
        logger.error(f"Empty content error: {e}")
        # Rollback the contract creation
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
        
    except DocumentParsingError as e:
        parsing_error = str(e)
        logger.error(f"Document parsing error: {e}")
        # Keep contract record but mark as failed
        logger.warning("Contract record kept but parsing failed")
        
    except Exception as e:
        parsing_error = str(e)
        logger.error(f"Unexpected error parsing document: {e}", exc_info=True)
        # Keep contract record but mark as failed
        logger.warning("Contract record kept but parsing failed with unexpected error")
        
    # 6. Return the contract (even if parsing failed, for audit purposes)
    enriched_contract, latest_version = contract_service.get_contract_with_latest_version(db, contract.id)
    if not enriched_contract:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load saved contract"
        )

    contract_payload = ContractRead.model_validate(enriched_contract, from_attributes=True)
    if latest_version:
        contract_payload.latest_version = ContractVersionRead.model_validate(
            latest_version, from_attributes=True
        )

    return contract_payload


@router.post("/{contract_id}/extract-clauses", response_model=AnalysisRunRead, status_code=202)
async def request_clause_extraction(
    contract_id: UUID,
    db: Session = Depends(get_db),
):
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        raise HTTPException(status_code=404, detail="No contract version found")

    run = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.contract_version_id == latest_version.id,
            AnalysisRun.type == "CLAUSE_EXTRACTION",
            AnalysisRun.status.in_(["PENDING", "RUNNING"]),
        )
        .first()
    )

    if not run:
        run = contract_service.create_analysis_run_for_version(
            db,
            contract_version_id=latest_version.id,
            run_type="CLAUSE_EXTRACTION",
            model_name="qwen2.5:32b",
        )
        db.commit()
        db.refresh(run)
        enqueue_clause_extraction(run.id)
    else:
        db.refresh(run)

    return AnalysisRunRead.model_validate(run, from_attributes=True)


@router.get("/{contract_id}/extract-clauses/{run_id}", response_model=ClauseExtractionJobRead)
async def get_clause_extraction_status(
    contract_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run = (
        db.query(AnalysisRun)
        .join(ContractVersion, AnalysisRun.contract_version_id == ContractVersion.id)
        .filter(
            AnalysisRun.id == run_id,
            ContractVersion.contract_id == contract_id,
            AnalysisRun.type == "CLAUSE_EXTRACTION",
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Clause extraction job not found")

    job = ClauseExtractionJobRead(
        run=AnalysisRunRead.model_validate(run, from_attributes=True),
        clauses=None,
    )
    
    # Return clauses even if still running, so frontend can show incremental progress
    if run.status in ["RUNNING", "COMPLETED"]:
        clauses = contract_service.list_clauses_for_version(db, run.contract_version_id)
        if clauses:
            job.clauses = [ClauseRead.model_validate(c, from_attributes=True) for c in clauses]
    
    return job


@router.get("/{contract_id}/clauses", response_model=list[ClauseRead])
async def list_clauses(
    contract_id: UUID,
    db: Session = Depends(get_db),
):
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        return []
    return contract_service.list_clauses_for_version(db, latest_version.id)


@router.get("/{contract_id}/conflicts", response_model=list[ConflictRead])
async def list_conflicts(
    contract_id: UUID,
    db: Session = Depends(get_db),
) -> list[ConflictRead]:
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        raise HTTPException(status_code=404, detail="No contract version found")

    conflicts = db.query(Conflict).filter(
        Conflict.contract_version_id == latest_version.id
    ).options(
        joinedload(Conflict.left_clause),
        joinedload(Conflict.right_clause)
    ).all()
    
    return [ConflictRead.model_validate(c, from_attributes=True) for c in conflicts]


@router.post("/{contract_id}/detect-conflicts", response_model=list[ConflictRead])
async def detect_conflicts(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    import sys
    print(f"=== DETECT CONFLICTS ENDPOINT CALLED === contract_id: {contract_id}", file=sys.stderr, flush=True)
    logger.info(f"Detect conflicts endpoint called for contract_id: {contract_id}")
    logger.info(f"Request received at: {__import__('datetime').datetime.now()}")
    
    # Check if analysis is already in progress - prevent duplicate calls
    try:
        contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
        if contract and latest_version:
            clauses = contract_service.list_clauses_for_version(db, latest_version.id)
            if clauses:
                # Check if any clause is currently being analyzed
                running_count = sum(1 for c in clauses if c.analysis_status == 'running')
                if running_count > 0:
                    logger.warning(f"Analysis already in progress for contract {contract_id}: {running_count} clauses running")
                    print(f"WARNING: Analysis already in progress, returning existing conflicts", file=sys.stderr, flush=True)
                    # Return existing conflicts instead of starting new analysis
                    existing_conflicts = db.query(Conflict).filter(
                        Conflict.contract_version_id == latest_version.id
                    ).all()
                    return existing_conflicts
    except Exception as e:
        logger.warning(f"Error checking for existing analysis: {e}, continuing with new analysis")
    
    try:
        contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
        logger.info(f"Contract lookup: contract={contract is not None}, version={latest_version is not None}")
        print(f"DEBUG: Contract lookup: contract={contract is not None}, version={latest_version is not None}", file=sys.stderr, flush=True)
    except Exception as e:
        logger.error(f"Error getting contract: {e}", exc_info=True)
        print(f"ERROR: Error getting contract: {e}", file=sys.stderr, flush=True)
        raise
    
    if not contract:
        logger.error(f"Contract not found: {contract_id}")
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        logger.error(f"No contract version found for contract: {contract_id}")
        raise HTTPException(status_code=404, detail="No contract version found")

    try:
        clauses = contract_service.list_clauses_for_version(db, latest_version.id)
        logger.info(f"Retrieved {len(clauses) if clauses else 0} clauses from database")
        print(f"DEBUG: Retrieved {len(clauses) if clauses else 0} clauses from database", file=sys.stderr, flush=True)
    except Exception as e:
        logger.error(f"Error retrieving clauses: {e}", exc_info=True)
        print(f"ERROR: Error retrieving clauses: {e}", file=sys.stderr, flush=True)
        raise
    
    if not clauses:
        logger.warning(f"No clauses found for contract version: {latest_version.id}")
        raise HTTPException(status_code=400, detail="No clauses found. Run extraction first.")
        
    logger.info(f"Found {len(clauses)} clauses to analyze for conflicts")
    print(f"DEBUG: Found {len(clauses)} clauses", file=sys.stderr, flush=True)
    
    # Initialize LLM service
    try:
        llm = LLMService(base_url=settings.OLLAMA_URL)
        logger.info(f"Initialized LLMService for conflict detection")
        print(f"DEBUG: Created LLMService instance", file=sys.stderr, flush=True)
    except Exception as e:
        logger.error(f"Error creating LLMService: {e}", exc_info=True)
        print(f"ERROR: Error creating LLMService: {e}", file=sys.stderr, flush=True)
        raise
    
    # Prepare clauses data for conflict detection
    # Send full clause text with all context for comprehensive analysis
    try:
        clauses_data = [
            {
                "id": str(c.id),
                "text": c.text,  # Full text - never truncated
                "clause_number": c.clause_number or f"#{c.order_index}",
                "heading": c.heading
            }
            for c in clauses
        ]
        logger.info(f"Prepared {len(clauses_data)} clauses for conflict detection")
        logger.info(f"Total text length: {sum(len(c.get('text', '')) for c in clauses_data)} characters")
        print(f"DEBUG: Prepared {len(clauses_data)} clauses for conflict detection", file=sys.stderr, flush=True)
    except Exception as e:
        logger.error(f"Error preparing clauses for conflict detection: {e}", exc_info=True)
        print(f"ERROR: Error preparing clauses for conflict detection: {e}", file=sys.stderr, flush=True)
        raise
    
    # Analyze all clauses together for conflicts
    # The LLM will understand the entire contract context (parties, contract type, jurisdiction, etc.)
    # and then identify conflicts between clauses
    logger.info("=" * 80)
    logger.info("Starting comprehensive conflict analysis...")
    logger.info("LLM is analyzing all clauses contextually to understand the contract and identify conflicts")
    logger.info("=" * 80)
    
    # Update a special status to indicate we're in contextual analysis phase
    # We'll use the contract's metadata or a special clause to track this
    # For now, just log it - the UI will poll and see all clauses are done, then conflicts appear
    
    # Call LLM to identify conflicts - it will understand the full context and check all clauses
    conflicts_data = await llm.identify_conflicts(clauses_data)
    logger.info(f"Conflict analysis completed: Found {len(conflicts_data) if conflicts_data else 0} conflicts between clauses")
    # Debug: log raw LLM response to help diagnose mapping issues
    try:
        logger.info("LLM identify_conflicts returned %s items", len(conflicts_data) if conflicts_data is not None else 0)
        if conflicts_data:
            # Log a small sample to avoid huge logs
            logger.info("LLM identify_conflicts sample[0]: %s", conflicts_data[0])
    except Exception:
        logger.exception("Failed to log LLM identify_conflicts response")

    # Temporary stdout print for debugging (ensures logs appear in container output)
    try:
        print("LLM_IDENTIFY_CONFlicts_RESULT_COUNT:", len(conflicts_data) if conflicts_data is not None else 0)
        if conflicts_data:
            print("LLM_IDENTIFY_CONFlicts_SAMPLE:", conflicts_data[0])
    except Exception as e:
        print("Failed to print LLM identify_conflicts result:", e)
    
    # Create Analysis Run if not exists (or new one)
    run = AnalysisRun(
        contract_version_id=latest_version.id,
        type="CONFLICT_DETECTION",
        model_name="qwen2.5:32b",
        status="COMPLETED"
    )
    db.add(run)
    db.flush()
    
    # Save Conflicts
    clause_lookup = {str(c.id): c for c in clauses}
    saved_conflicts = []
    logger.info(f"Processing {len(conflicts_data)} conflicts from LLM")
    for idx, conf in enumerate(conflicts_data):
        clause_id_1 = conf.get("clause_id_1")
        clause_id_2 = conf.get("clause_id_2")
        
        logger.info(f"Processing conflict {idx + 1}: clause_id_1={clause_id_1}, clause_id_2={clause_id_2}")

        clause_1 = clause_lookup.get(str(clause_id_1))
        clause_2 = clause_lookup.get(str(clause_id_2))

        if not clause_1 or not clause_2:
            logger.warning(
                "Skipping conflict because referenced clauses were not found: %s, %s",
                clause_id_1,
                clause_id_2,
            )
            continue
        
        # Skip conflicts where both clauses are the same
        if clause_1.id == clause_2.id:
            logger.warning(
                "Skipping conflict between same clause: %s",
                clause_id_1,
            )
            continue
        
        # Skip conflicts involving Gap clauses
        if clause_1.clause_number == 'Gap' or clause_2.clause_number == 'Gap':
            logger.warning(
                "Skipping conflict involving Gap clause: %s, %s",
                clause_1.clause_number,
                clause_2.clause_number,
            )
            continue

        def _label(clause: Clause) -> str:
            if clause.clause_number:
                return clause.clause_number
            return f"#{clause.order_index}"

        # Use LLM's detailed description, or fallback to basic summary
        llm_description = conf.get("description", "")
        if llm_description:
            summary = llm_description
        else:
            summary = (
                f"Conflict between Clause {_label(clause_1)} "
                f"and Clause {_label(clause_2)}"
            )

        conflict = Conflict(
            analysis_run_id=run.id,
            contract_version_id=latest_version.id,
            severity=conf.get("severity", "UNKNOWN"),
            explanation=conf.get("suggested_resolution") or "",  # Store suggested resolution in explanation field
            summary=summary,
            left_clause_id=clause_1.id,
            right_clause_id=clause_2.id,
        )
        db.add(conflict)
        saved_conflicts.append(conflict)
        logger.info(f"✓ Saved conflict {idx + 1}: {_label(clause_1)} vs {_label(clause_2)}")
        
    logger.info(f"Committing {len(saved_conflicts)} conflicts to database")
    db.commit()
    logger.info(f"✓ Successfully saved {len(saved_conflicts)} conflicts")
    
    # Reload conflicts with clause relationships for response
    conflict_ids = [c.id for c in saved_conflicts]
    conflicts_with_clauses = db.query(Conflict).filter(
        Conflict.id.in_(conflict_ids)
    ).options(
        joinedload(Conflict.left_clause),
        joinedload(Conflict.right_clause)
    ).all()
    
    return conflicts_with_clauses
