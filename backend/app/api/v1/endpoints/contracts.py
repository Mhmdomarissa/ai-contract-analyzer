from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
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



@router.post("/{contract_id}/detect-conflicts", response_model=AnalysisRunRead, status_code=202)
async def request_conflict_detection(
    contract_id: UUID,
    strategy: str = Query(default="fast_accurate", description="Detection strategy: fast_accurate (recommended, 5-10min) or accurate (thorough, 20-40min)"),
    db: Session = Depends(get_db)
):
    """
    Start asynchronous conflict detection. Returns immediately with a run_id to poll for status.
    
    Detection strategies:
    - fast_accurate (default): 2-stage validation, 5-10 minutes, best balance
    - accurate: 5-stage validation, 20-40 minutes, very thorough
    
    Use GET /{contract_id}/detect-conflicts/{run_id} to check status.
    """
    logger.info(f"🚀 Request conflict detection for contract_id: {contract_id}, strategy: {strategy}")
    
    # Get contract and version
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        raise HTTPException(status_code=404, detail="No contract version found")
    
    # Check if there's already a pending/running detection
    run = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.contract_version_id == latest_version.id,
            AnalysisRun.type == "CONFLICT_DETECTION",
            AnalysisRun.status.in_(["PENDING", "RUNNING"]),
        )
        .first()
    )
    
    if not run:
        # Create new analysis run
        run = contract_service.create_analysis_run_for_version(
            db,
            contract_version_id=latest_version.id,
            run_type="CONFLICT_DETECTION",
            model_name="qwen2.5:32b",
        )
        db.commit()
        db.refresh(run)
        
        # Enqueue the Celery task
        from app.tasks.conflict_analysis import analyze_contract_conflicts
        analyze_contract_conflicts.delay(str(run.id), strategy)
        logger.info(f"📤 Queued conflict detection task for run_id={run.id}")
    else:
        logger.info(f"♻️ Returning existing run_id={run.id}")
        db.refresh(run)
    
    return AnalysisRunRead.model_validate(run, from_attributes=True)


@router.get("/{contract_id}/detect-conflicts/{run_id}", response_model=dict)
async def get_conflict_detection_status(
    contract_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Check the status of a conflict detection job.
    
    Returns:
    - status: PENDING, RUNNING, COMPLETED, or FAILED
    - conflicts: list of detected conflicts (when COMPLETED)
    - error_message: error details (when FAILED)
    """
    run = (
        db.query(AnalysisRun)
        .join(ContractVersion, AnalysisRun.contract_version_id == ContractVersion.id)
        .filter(
            AnalysisRun.id == run_id,
            ContractVersion.contract_id == contract_id,
            AnalysisRun.type == "CONFLICT_DETECTION",
        )
        .first()
    )
    
    if not run:
        raise HTTPException(status_code=404, detail="Conflict detection job not found")
    
    response = {
        "run_id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    
    if run.status == "FAILED":
        response["error_message"] = run.error_message
    
    if run.status == "COMPLETED":
        # Fetch conflicts
        from app.models.conflict import Conflict
        from sqlalchemy.orm import joinedload
        
        conflicts = db.query(Conflict).filter(
            Conflict.contract_version_id == run.contract_version_id,
            Conflict.score >= 0.85
        ).options(
            joinedload(Conflict.left_clause),
            joinedload(Conflict.right_clause)
        ).all()
        
        response["conflicts"] = [ConflictRead.model_validate(c, from_attributes=True) for c in conflicts]
        response["conflicts_count"] = len(conflicts)
    
    return response

