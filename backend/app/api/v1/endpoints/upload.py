"""Contract upload and processing endpoint with SSE progress updates."""
import os
import tempfile
import asyncio
import logging
from typing import AsyncGenerator
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.db.session import get_db
from app.crud import contract as contract_crud
from app.schemas.contract import ContractCreate, ContractUpdate
from app.schemas.upload import ProgressEvent, UploadResponse
from app.services.parsers import ParserFactory
from app.services.clause_extractor import ClauseExtractor
from app.services.party_identifier import PartyIdentifier
from app.models.contract import ContractStatus
from app.models.contract_version import ContractVersion
from app.models.party import Party
from app.models.clause import Clause
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize services
parser_factory = ParserFactory()
clause_extractor = ClauseExtractor()
party_identifier = PartyIdentifier()


async def send_progress(message: str, stage: str, progress: int = 0, data: dict = None):
    """Helper to format SSE progress events."""
    event = ProgressEvent(
        stage=stage,
        message=message,
        progress=progress,
        timestamp=datetime.utcnow().isoformat(),
        data=data or {}
    )
    return f"data: {event.json()}\n\n"


async def process_contract_with_progress(
    file: UploadFile,
    db: Session
) -> AsyncGenerator[str, None]:
    """
    Process contract upload with real-time progress updates via SSE.
    
    Steps:
    1. Receive upload
    2. Parse file
    3. Normalize text
    4. Extract clauses
    5. Remove TOC
    6. Identify parties
    7. Save to database
    """
    contract_id = None
    
    try:
        # ==================== STAGE 1: UPLOAD RECEIVED ====================
        yield await send_progress(
            "Upload received, validating file...",
            "UPLOAD_RECEIVED",
            5
        )
        
        # Validate file
        if not file.filename:
            raise ValueError("No filename provided")
        
        # Get file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        supported_types = ['.pdf', '.docx', '.doc', '.txt']
        
        if file_ext not in supported_types:
            raise ValueError(f"Unsupported file type: {file_ext}. Supported: {', '.join(supported_types)}")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Check file size (max 50MB)
        max_size = 50 * 1024 * 1024
        if file_size > max_size:
            raise ValueError(f"File too large: {file_size / 1024 / 1024:.2f}MB (max: 50MB)")
        
        yield await send_progress(
            f"File validated: {file.filename} ({file_size / 1024:.2f}KB)",
            "UPLOAD_VALIDATED",
            10,
            {"filename": file.filename, "size": file_size, "type": file_ext}
        )
        
        # ==================== STAGE 2: CREATE CONTRACT RECORD ====================
        yield await send_progress(
            "Creating contract record...",
            "DB_CREATE_STARTED",
            15
        )
        
        contract_create = ContractCreate(
            filename=file.filename,
            original_filename=file.filename,
            file_type=file_ext.replace('.', ''),
            file_size=file_size,
            status=ContractStatus.PARSING
        )
        
        db_contract = contract_crud.create_contract(db, contract_create)
        contract_id = db_contract.id
        
        yield await send_progress(
            f"Contract record created: {contract_id}",
            "DB_CREATE_COMPLETED",
            20,
            {"contract_id": str(contract_id)}
        )
        
        # ==================== STAGE 3: PARSE FILE ====================
        yield await send_progress(
            f"Parsing {file_ext} file...",
            "PARSING_STARTED",
            25
        )
        
        # Save file temporarily for parsing
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        try:
            parser = parser_factory.get_parser(tmp_file_path)
            if not parser:
                raise ValueError(f"No parser found for file type: {file_ext}")
            
            parse_result = parser.parse(tmp_file_path)
            raw_text = parse_result.text
        finally:
            # Clean up temp file
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
        
        if not raw_text or len(raw_text.strip()) < 100:
            raise ValueError("Extracted text too short or empty. File may be scanned/protected.")
        
        yield await send_progress(
            f"File parsed successfully ({len(raw_text)} characters)",
            "PARSING_COMPLETED",
            35,
            {"text_length": len(raw_text)}
        )
        
        # ==================== STAGE 4: EXTRACT CLAUSES ====================
        yield await send_progress(
            "Extracting and structuring clauses...",
            "CLAUSE_EXTRACTION_STARTED",
            40
        )
        
        # Normalize and process text
        clean_text = clause_extractor.normalize_text(raw_text)
        capitalized_text = clause_extractor.capitalize_titles(clean_text)
        
        # Extract clauses
        clauses = clause_extractor.split_into_clauses(capitalized_text)
        
        # Remove unnumbered clauses
        real_clauses = [c for c in clauses if not c["clause number"].startswith("UNNUMBERED")]
        
        yield await send_progress(
            f"Extracted {len(real_clauses)} clauses",
            "CLAUSE_EXTRACTION_PROGRESS",
            50,
            {"clause_count": len(real_clauses)}
        )
        
        # ==================== STAGE 5: REMOVE TOC ====================
        yield await send_progress(
            "Removing Table of Contents entries...",
            "TOC_REMOVAL_STARTED",
            55
        )
        
        filtered_clauses = clause_extractor.remove_toc_entries(real_clauses)
        removed_count = len(real_clauses) - len(filtered_clauses)
        
        yield await send_progress(
            f"Removed {removed_count} TOC entries, {len(filtered_clauses)} clauses remaining",
            "TOC_REMOVAL_COMPLETED",
            60,
            {"removed": removed_count, "remaining": len(filtered_clauses)}
        )
        
        # ==================== STAGE 6: IDENTIFY PARTIES ====================
        yield await send_progress(
            "Identifying contract parties using AI...",
            "PARTY_IDENTIFICATION_STARTED",
            65
        )
        
        parties = party_identifier.identify_parties(clean_text)
        
        yield await send_progress(
            f"Identified {len(parties)} parties: {', '.join(parties)}",
            "PARTY_IDENTIFICATION_COMPLETED",
            75,
            {"parties": parties}
        )
        
        # ==================== STAGE 7: SAVE TO DATABASE ====================
        yield await send_progress(
            "Saving to database...",
            "DB_SAVE_STARTED",
            80
        )
        
        # Create contract version
        version = ContractVersion(
            contract_id=db_contract.id,
            version_number=1,
            raw_text=raw_text,
            parsed_text=clean_text
        )
        db.add(version)
        db.flush()
        
        # Save parties
        for party_name in parties:
            party = Party(
                contract_id=db_contract.id,
                name=party_name
            )
            db.add(party)
        
        yield await send_progress(
            f"Saved {len(parties)} parties",
            "DB_SAVE_PROGRESS",
            85,
            {"saved": "parties"}
        )
        
        # Save clauses
        for order_idx, clause_data in enumerate(filtered_clauses):
            clause = Clause(
                contract_id=db_contract.id,
                version_id=version.id,
                clause_number=clause_data["clause number"],
                content=clause_data["Clause content"],
                parent_clause_id=None,  # Main clause
                order_index=order_idx,
                uuid_from_extractor=clause_data.get("uuid")
            )
            db.add(clause)
            db.flush()
            
            # Save sub-clauses
            if "sub_clauses" in clause_data:
                for sub_idx, sub_data in enumerate(clause_data["sub_clauses"]):
                    sub_clause = Clause(
                        contract_id=db_contract.id,
                        version_id=version.id,
                        clause_number=sub_data["clause number"],
                        content=sub_data["Clause content"],
                        parent_clause_id=clause.id,
                        order_index=sub_idx,
                        uuid_from_extractor=sub_data.get("uuid")
                    )
                    db.add(sub_clause)
        
        yield await send_progress(
            f"Saved {len(filtered_clauses)} clauses",
            "DB_SAVE_PROGRESS",
            90,
            {"saved": "clauses"}
        )
        
        # Update contract status
        contract_update = ContractUpdate(status=ContractStatus.COMPLETED)
        contract_crud.update_contract(db, db_contract.id, contract_update)
        
        db.commit()
        
        yield await send_progress(
            f"Processing complete! Contract saved with ID: {contract_id}",
            "PROCESSING_COMPLETED",
            100,
            {
                "contract_id": str(contract_id),
                "clause_count": len(filtered_clauses),
                "party_count": len(parties)
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing contract: {str(e)}", exc_info=True)
        
        # Update contract status to failed if we have contract_id
        if contract_id:
            try:
                contract_update = ContractUpdate(
                    status=ContractStatus.FAILED,
                    error_message=str(e)
                )
                contract_crud.update_contract(db, contract_id, contract_update)
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update contract status: {db_error}")
        
        # Send error event
        error_event = ProgressEvent(
            stage="ERROR",
            message=f"Processing failed: {str(e)}",
            progress=0,
            timestamp=datetime.utcnow().isoformat(),
            data={"error": str(e), "contract_id": str(contract_id) if contract_id else None}
        )
        yield f"data: {error_event.json()}\n\n"


@router.post("/upload", response_class=StreamingResponse)
async def upload_contract(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload and process a contract file with real-time progress updates.
    
    Returns Server-Sent Events (SSE) stream with progress updates.
    
    Supported file types: PDF, DOCX, DOC, TXT
    Max file size: 50MB
    
    Progress stages:
    - UPLOAD_RECEIVED
    - UPLOAD_VALIDATED
    - DB_CREATE_STARTED/COMPLETED
    - PARSING_STARTED/COMPLETED
    - CLAUSE_EXTRACTION_STARTED/PROGRESS/COMPLETED
    - TOC_REMOVAL_STARTED/COMPLETED
    - PARTY_IDENTIFICATION_STARTED/COMPLETED
    - DB_SAVE_STARTED/PROGRESS/COMPLETED
    - PROCESSING_COMPLETED
    - ERROR (if something goes wrong)
    """
    return StreamingResponse(
        process_contract_with_progress(file, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@router.get("/{contract_id}/clauses")
async def get_contract_clauses(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get all clauses for a contract (for Testing Lab integration).
    
    Returns clauses in hierarchical structure with main clauses and sub-clauses.
    """
    # Get contract
    contract = contract_crud.get_contract(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Get clauses (main clauses only, ordered)
    main_clauses = (
        db.query(Clause)
        .filter(Clause.contract_id == contract_id, Clause.parent_clause_id == None)
        .order_by(Clause.order_index)
        .all()
    )
    
    result = []
    for main_clause in main_clauses:
        # Get sub-clauses
        sub_clauses = (
            db.query(Clause)
            .filter(Clause.parent_clause_id == main_clause.id)
            .order_by(Clause.order_index)
            .all()
        )
        
        clause_data = {
            "id": str(main_clause.id),
            "clause_number": main_clause.clause_number,
            "content": main_clause.content,
            "order_index": main_clause.order_index,
            "sub_clauses": [
                {
                    "id": str(sc.id),
                    "clause_number": sc.clause_number,
                    "content": sc.content,
                    "order_index": sc.order_index
                }
                for sc in sub_clauses
            ]
        }
        result.append(clause_data)
    
    return {
        "contract_id": str(contract_id),
        "filename": contract.filename,
        "clause_count": len(main_clauses),
        "clauses": result
    }


@router.get("")
async def list_contracts(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all contracts."""
    contracts = contract_crud.get_contracts(db, skip=skip, limit=limit)
    
    return {
        "contracts": [
            {
                "id": str(c.id),
                "filename": c.filename,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "file_type": c.file_type,
                "file_size": c.file_size
            }
            for c in contracts
        ],
        "total": len(contracts)
    }


@router.get("/{contract_id}")
async def get_contract_details(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    """Get contract details including parties and clause count."""
    contract = contract_crud.get_contract_with_details(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Count clauses
    clause_count = db.query(Clause).filter(
        Clause.contract_id == contract_id,
        Clause.parent_clause_id == None
    ).count()
    
    # Get parties
    parties = db.query(Party).filter(Party.contract_id == contract_id).all()
    
    return {
        "id": str(contract.id),
        "filename": contract.filename,
        "original_filename": contract.original_filename,
        "status": contract.status,
        "file_type": contract.file_type,
        "file_size": contract.file_size,
        "created_at": contract.created_at.isoformat() if contract.created_at else None,
        "clause_count": clause_count,
        "parties": [{"id": str(p.id), "name": p.name} for p in parties],
        "error_message": contract.error_message
    }


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a contract and all related data."""
    success = contract_crud.delete_contract(db, contract_id)
    if not success:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    return {"message": "Contract deleted successfully", "contract_id": str(contract_id)}
