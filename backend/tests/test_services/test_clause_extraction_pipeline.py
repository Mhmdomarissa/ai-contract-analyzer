import json
import re

import pytest

from app.services import document_parser
from app.services.llm_service import LLMService


@pytest.mark.asyncio
async def test_clause_extraction_handles_large_pdf(monkeypatch):
    fixture_path = "tests/fixtures/madinat-badr-lease.pdf"
    text = document_parser.parse_document(fixture_path)

    # Sanity check that the document is the expected large sample.
    assert len(text) > 100_000

    pattern = re.compile(r"^\s*(\d{1,3}(?:\.\d+)*)[\).\-]?\s+(.+)$", re.MULTILINE)

    async def fake_call_llm(self, prompt: str) -> str:  # type: ignore[override]
        chunk = prompt.split("Text:", 1)[-1]
        matches = pattern.findall(chunk)
        clauses = []
        for label, body in matches:
            body_clean = body.strip()
            clauses.append(
                {
                    "id": "",  # overwritten by extract_clauses
                    "clause_number": label,
                    "text": f"{label} {body_clean}".strip(),
                    "category": "Mock",
                }
            )
        if not clauses:
            # ensure each chunk emits at least one clause so numbering keeps advancing
            snippet = " ".join(chunk.strip().split())[:200]
            clauses.append(
                {
                    "id": "",
                    "clause_number": None,
                    "text": snippet,
                    "category": "Mock",
                }
            )
        return json.dumps({"clauses": clauses})

    monkeypatch.setattr(LLMService, "_call_llm", fake_call_llm)

    service = LLMService(base_url="http://test")
    clauses = await service.extract_clauses(text)

    assert len(clauses) > 40
    assert all("text" in clause for clause in clauses)
    assert clauses[0]["id"] == "1"
    assert clauses[1]["id"] == "2"
