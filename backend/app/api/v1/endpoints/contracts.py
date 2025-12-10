from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

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
    # 1. Save the file locally
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()
        
    file_size = file_path.stat().st_size
    
    # 2. Create Contract in DB
    contract_in = ContractCreate(
        title=title,
        file=ContractFileCreate(
            storage_path=str(file_path),
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size_bytes=file_size
        )
    )
    
    contract = contract_service.create_contract_with_file_and_version(db, contract_in)
    db.commit()
    db.refresh(contract)
    
    # 3. Parse Document and save to version
    parsed_text = None
    try:
        parsed_text = document_parser.parse_document(str(file_path))
        logger.info(f"Extracted text length: {len(parsed_text) if parsed_text else 0}")
        
        # Save parsed text to the version
        latest_version = db.query(ContractVersion).filter(
            ContractVersion.contract_id == contract.id,
            ContractVersion.is_current == True
        ).first()
        
        if latest_version and parsed_text:
            latest_version.parsed_text = parsed_text
            db.commit()
            db.refresh(latest_version)
    except Exception as e:
        logger.error(f"Failed to parse document: {e}")
        # We don't fail the upload, but we log it.
        
    enriched_contract, latest_version = contract_service.get_contract_with_latest_version(db, contract.id)
    if not enriched_contract:
        raise HTTPException(status_code=500, detail="Unable to load saved contract")

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


@router.post("/{contract_id}/detect-conflicts", response_model=list[ConflictRead])
async def detect_conflicts(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        raise HTTPException(status_code=404, detail="No contract version found")

    clauses = contract_service.list_clauses_for_version(db, latest_version.id)
    if not clauses:
        raise HTTPException(status_code=400, detail="No clauses found. Run extraction first.")
        
    # Convert to dict format expected by LLM service
    clauses_data = [{"id": str(c.id), "text": c.text, "clause_number": c.clause_number} for c in clauses]
    
    # LLM Detect
    llm = LLMService(base_url=settings.OLLAMA_URL)
    logger.info("Step 2: Identifying conflicts...")
    conflicts_data = await llm.identify_conflicts(clauses_data)
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
    for conf in conflicts_data:
        clause_id_1 = conf.get("clause_id_1")
        clause_id_2 = conf.get("clause_id_2")

        clause_1 = clause_lookup.get(str(clause_id_1))
        clause_2 = clause_lookup.get(str(clause_id_2))

        if not clause_1 or not clause_2:
            logger.warning(
                "Skipping conflict because referenced clauses were not found: %s, %s",
                clause_id_1,
                clause_id_2,
            )
            continue

        def _label(clause: Clause) -> str:
            if clause.clause_number:
                return clause.clause_number
            return f"#{clause.order_index}"

        summary = (
            f"Conflict between Clause {_label(clause_1)} "
            f"and Clause {_label(clause_2)}"
        )

        conflict = Conflict(
            analysis_run_id=run.id,
            contract_version_id=latest_version.id,
            severity=conf.get("severity", "UNKNOWN"),
            explanation=None, # Step 3 will fill this
            summary=summary,
            left_clause_id=clause_1.id,
            right_clause_id=clause_2.id,
        )
        db.add(conflict)
        saved_conflicts.append(conflict)
        
    db.commit()
    for c in saved_conflicts:
        db.refresh(c)
        
    return saved_conflicts


@router.post("/{contract_id}/generate-explanations", response_model=list[ConflictRead])
async def generate_explanations(
    contract_id: UUID,
    db: Session = Depends(get_db)
):
    contract, latest_version = contract_service.get_contract_with_latest_version(db, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if not latest_version:
        raise HTTPException(status_code=404, detail="No contract version found")

    clauses = contract_service.list_clauses_for_version(db, latest_version.id)
    clauses_data = [{"id": str(c.id), "text": c.text, "clause_number": c.clause_number} for c in clauses]
    
    # Get conflicts
    conflicts = db.query(Conflict).filter(
        Conflict.contract_version_id == latest_version.id,
        Conflict.explanation == None
    ).all()
    
    if not conflicts:
        # Maybe they already have explanations? Return all.
        return db.query(Conflict).filter(Conflict.contract_version_id == latest_version.id).all()
    
    conflicts_for_llm = []
    for c in conflicts:
        if not c.left_clause_id or not c.right_clause_id:
            logger.warning("Conflict %s missing clause references; skipping explanation.", c.id)
            continue
        conflicts_for_llm.append({
            "clause_id_1": str(c.left_clause_id),
            "clause_id_2": str(c.right_clause_id),
            "db_id": c.id,
        })
            
    if not conflicts_for_llm:
        return db.query(Conflict).filter(Conflict.contract_version_id == latest_version.id).all()

    # LLM Explain
    llm = LLMService(base_url=settings.OLLAMA_URL)
    logger.info("Step 3: Generating explanations...")
    
    explanations = await llm.generate_explanations(conflicts_for_llm, clauses_data)
    
    # Update Conflicts
    for expl in explanations:
        # We need to match the explanation back to the conflict.
        # The LLM returns clause_id_1 and clause_id_2.
        # We can match against conflicts_for_llm
        
        c1 = expl.get("clause_id_1")
        c2 = expl.get("clause_id_2")
        
        # Find matching conflict in our list
        match = next((c for c in conflicts_for_llm if c["clause_id_1"] == c1 and c["clause_id_2"] == c2), None)
        
        if match:
            db_id = match["db_id"]
            conflict = db.query(Conflict).filter(Conflict.id == db_id).first()
            if conflict:
                conflict.explanation = expl.get("explanation", "No explanation generated.")
                conflict.severity = expl.get("severity", conflict.severity)
                
    db.commit()
    
    return db.query(Conflict).filter(Conflict.contract_version_id == latest_version.id).all()
