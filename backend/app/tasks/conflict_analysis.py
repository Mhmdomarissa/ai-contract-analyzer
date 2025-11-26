from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.analyze_contract_conflicts")
def analyze_contract_conflicts(contract_id: int) -> dict:
    """Stub Celery task."""
    return {"contract_id": contract_id, "status": "pending"}

