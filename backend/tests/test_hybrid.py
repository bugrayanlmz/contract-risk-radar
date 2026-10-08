from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.analysis.evidence import normalize_text, verify_quote
from app.analysis.pipeline import analyze_text
from app.config import Settings
from app.jobs.tasks import run_analysis
from app.models import AiFinding as StoredAiFinding
from app.models import AnalysisResult, Document
from app.providers.base import ProviderError
from app.schemas.extraction import AiFinding, AiFindingBatch
from tests.helpers import TEXT, FakeProvider, facts
from tests.test_api_worker import fixture_pdf, register, upload


def finding(**changes):
    values = dict(
        title="Required inspection",
        related_category=None,
        quote="Monthly rent is USD 1000.00.",
        explanation="This is an additional practical burden.",
        model_score=3,
        rationale="The obligation has a bounded impact.",
        uncertainties=[],
    )
    return {**values, **changes}


async def test_separate_scores_evidence_deduplication_and_dates():
    output = (
        await analyze_text(
            TEXT,
            uuid4(),
            FakeProvider(
                ai_findings=[
                    finding(),
                    finding(quote="Monthly  rent is USD 1000.00."),
                    finding(title="A different issue", model_score=5),
                    finding(title="Unsupported issue", quote="Invented text", model_score=5),
                ]
            ),
        )
    ).response
    assert output.overall_score == 4 and output.ai_overall_score == 5
    assert len(output.ai_findings) == 3
    assert output.ai_findings[-1].score is None and output.ai_findings[-1].model_score == 5
    assert output.ai_findings[-1].warnings
    assert output.ai_review_status == "completed" and output.ai_rubric_version == "1.0"
    assert len(output.important_dates) == 3


async def test_unverified_ai_never_implies_low_risk():
    output = (
        await analyze_text(
            TEXT, uuid4(), FakeProvider(clauses=[], ai_findings=[finding(quote="Not in document")])
        )
    ).response
    assert output.ai_overall_score is None and output.overall_score is None


async def test_german_original_evidence_and_canonical_values():
    text = "Der Mietvertrag beginnt am 01.02.2027 und endet am 31.01.2028.\nDie Miete beträgt 1.500,00 EUR.\n„Die Nutzung von Überwachungskameras ist vorgeschrieben.“"
    contract = facts(
        language="german",
        start_date="2027-02-01",
        end_date="2028-01-31",
        monthly_rent={"amount": "1500.00", "currency": "EUR"},
        deposit_amount=None,
        evidence=dict(
            start_date=text.splitlines()[0],
            end_date=text.splitlines()[0],
            monthly_rent=text.splitlines()[1],
            deposit_amount=None,
        ),
    )
    output = (
        await analyze_text(
            text,
            uuid4(),
            FakeProvider(
                contract,
                clauses=[],
                ai_findings=[
                    finding(
                        quote='"Die Nutzung von Überwachungskameras ist vorgeschrieben."',
                        title="Required cameras",
                    )
                ],
            ),
        )
    ).response
    assert output.facts.language == "german" and output.facts.monthly_rent.amount == 1500
    assert output.ai_findings[0].quote_verified
    assert output.important_dates[0].date.isoformat() == "2027-02-01"
    assert normalize_text("„Mieter“ und ‚Straße‘") == "\"Mieter\" und 'Straße'"
    assert not verify_quote("Strasse", "Straße")
    assert not verify_quote("mieter", "Mieter")


@pytest.mark.parametrize("language", ["other", "unknown"])
async def test_unsupported_language(language):
    with pytest.raises(Exception, match="Only English or German"):
        await analyze_text(TEXT, uuid4(), FakeProvider(facts(language=language)))


async def test_ai_failure_aborts_publication(client, factory, monkeypatch):
    await register(client)

    async def enqueue(session, document):
        return 1

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue)
    document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
    async with factory() as session:
        run_id = (await session.get(Document, document_id)).run_id
    with pytest.raises(ProviderError):
        await run_analysis(document_id, run_id, 1, factory, FakeProvider(fail_ai=True))
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisResult)) == 0
    assert (await client.get(f"/api/documents/{document_id}")).json()["status"] == "failed"


async def test_ai_findings_round_trip(client, factory, monkeypatch):
    await register(client)

    async def enqueue(session, document):
        return 1

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue)
    document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
    async with factory() as session:
        run_id = (await session.get(Document, document_id)).run_id
    await run_analysis(
        document_id,
        run_id,
        1,
        factory,
        FakeProvider(ai_findings=[finding(), finding(title="Unverified", quote="Missing text")]),
    )
    output = (await client.get(f"/api/documents/{document_id}/results")).json()
    assert output["ai_overall_score"] == 3 and output["ai_findings"][1]["score"] is None
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(StoredAiFinding)) == 2
        # Existing analyses have no additional review: the reader preserves that distinction.
        row = await session.scalar(select(AnalysisResult))
        row.ai_review_status, row.ai_overall_score, row.ai_rubric_version = "not_run", None, None
        await session.commit()
    assert (await client.get(f"/api/documents/{document_id}/results")).json()[
        "ai_review_status"
    ] == "not_run"


@pytest.mark.parametrize(
    "environment,enabled,allowed",
    [("development", False, False), ("production", True, False), ("development", True, True)],
)
async def test_real_upload_capabilities_and_consent(
    client, pdf_bytes, monkeypatch, environment, enabled, allowed
):
    settings = Settings(
        environment=environment,
        allow_real_documents=enabled,
        jwt_secret="test-only-secret-that-is-at-least-32-characters",
    )
    monkeypatch.setattr("app.api.documents.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    async def enqueue(session, document):
        return 1

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue)
    await register(client)
    capabilities = (await client.get("/api/capabilities")).json()
    assert capabilities == {
        "supported_languages": ["english", "german"],
        "real_documents_allowed": allowed,
    }
    response = await client.post(
        "/api/documents",
        files={"file": ("lease.pdf", pdf_bytes)},
        data={"document_kind": "real", "analysis_consent_confirmed": "false"},
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/documents",
        files={"file": ("lease.pdf", pdf_bytes)},
        data={"document_kind": "real", "analysis_consent_confirmed": "true"},
    )
    assert response.status_code == (202 if allowed else 403)
    if allowed:
        assert response.json()["document_kind"] == "real"


@pytest.mark.parametrize("score", [0, 6, True, 3.5, "3"])
def test_ai_score_requires_bounded_integer(score):
    with pytest.raises(ValidationError):
        AiFinding.model_validate(finding(model_score=score))


def test_ai_batch_bounded_and_unknown_category_rejected():
    assert AiFindingBatch(findings=[]).findings == []
    with pytest.raises(ValidationError):
        AiFindingBatch.model_validate({"findings": [finding()] * 21})
    with pytest.raises(ValidationError):
        AiFinding.model_validate(finding(related_category="INVENTED"))


def test_provider_schema_preserves_title_property():
    from app.providers.http import provider_schema

    schema = provider_schema(AiFindingBatch)
    finding_schema = schema["$defs"]["AiFinding"]
    assert "title" in finding_schema["properties"]
    assert "title" in finding_schema["required"]
    assert "maxLength" not in finding_schema["properties"]["title"]


@pytest.mark.parametrize("provider_name", ["claude", "gemini"])
async def test_native_ai_schema_and_english_titles(provider_name):
    import json

    import httpx

    from app.providers.http import ClaudeProvider, GeminiProvider

    payload = AiFindingBatch.model_validate(
        {"findings": [finding(quote="Der Mieter muss zahlen.")]}
    ).model_dump_json()

    def handler(request):
        body = json.loads(request.content)
        if provider_name == "claude":
            schema = body["output_config"]["format"]["schema"]
            result = {"stop_reason": "end_turn", "content": [{"type": "text", "text": payload}]}
        else:
            schema = body["generationConfig"]["responseJsonSchema"]
            result = {
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": payload}]}}]
            }
        assert "title" in schema["$defs"]["AiFinding"]["properties"]
        assert "tools" not in body
        return httpx.Response(200, json=result)

    provider_type = ClaudeProvider if provider_name == "claude" else GeminiProvider
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await provider_type("test-model", "test-key", client).extract(
            "Der Mieter muss zahlen.", "Review additional conditions", AiFindingBatch
        )
    assert response.data.findings[0].title == "Required inspection"
    assert response.data.findings[0].quote == "Der Mieter muss zahlen."
