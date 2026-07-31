from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import ChangeType
from app.services.assessment import (
    AssessmentPayload,
    AssessmentResult,
    OllamaAssessmentProvider,
    SafeAssessmentService,
)

RUNTIME_ROOT = Path("test-runtime")


def build_settings(runtime_dir: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{runtime_dir / 'unused.db'}",
        upload_dir=runtime_dir / "uploads",
        max_upload_bytes=5_242_880,
        max_extracted_chars=500_000,
        max_sections_per_version=250,
        max_changed_sections=100,
        max_assessment_calls=10,
        llm_provider="heuristic",
        ollama_base_url="http://localhost:11434",
        ollama_model="gemma3",
        openai_api_key=None,
        openai_model="unused",
        llm_timeout_seconds=1.0,
    )


def _runtime_dir() -> Path:
    path = RUNTIME_ROOT / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_document_version_comparison_review_and_evaluation_flow() -> None:
    runtime_dir = _runtime_dir()
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=build_settings(runtime_dir),
        create_schema_for_tests=True,
    )
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200

        document = client.post(
            "/api/v1/documents",
            json={
                "title": "Vendor Terms",
                "version_label": "v1",
                "content": "1. Payment Terms\nInvoices are due in 30 days.\n\n2. Support\nEmail support is included.",
            },
        )
        assert document.status_code == 201
        document_body = document.json()
        baseline_id = document_body["versions"][0]["id"]

        version = client.post(
            f"/api/v1/documents/{document_body['id']}/versions",
            json={
                "version_label": "v2",
                "content": "1. Payment Terms\nInvoices are due in 15 days with a late fee.\n\n2. Privacy\nWe share personal data with analytics providers.",
            },
        )
        assert version.status_code == 201

        comparison = client.post(
            "/api/v1/comparisons",
            json={
                "baseline_version_id": baseline_id,
                "candidate_version_id": version.json()["id"],
            },
        )
        assert comparison.status_code == 201
        comparison_body = comparison.json()
        assert len(comparison_body["changes"]) == 3
        assert all(change["assessment"]["validation_status"] == "validated" for change in comparison_body["changes"])

        payment_change = next(
            change for change in comparison_body["changes"] if change["new_heading"] == "Payment Terms"
        )
        review = client.patch(
            f"/api/v1/changes/{payment_change['id']}/review",
            json={"status": "reviewed", "note": "Confirmed against vendor redline."},
        )
        assert review.status_code == 200
        assert review.json()["status"] == "reviewed"

        report_after_review = client.get(f"/api/v1/comparisons/{comparison_body['id']}")
        reviewed_change = next(
            change for change in report_after_review.json()["changes"] if change["id"] == payment_change["id"]
        )
        assert reviewed_change["latest_review"]["status"] == "reviewed"
        assert reviewed_change["old_page_number"] == 1
        assert reviewed_change["new_page_number"] == 1

        filtered = client.get(f"/api/v1/comparisons/{comparison_body['id']}?severity=high")
        assert filtered.status_code == 200
        assert all(change["assessment"]["severity"] == "high" for change in filtered.json()["changes"])

        evaluation = client.post("/api/v1/evaluations/run")
        assert evaluation.status_code == 200
        assert evaluation.json()["metrics"]["case_count"] == 16


def test_browser_demo_assets_are_served() -> None:
    runtime_dir = _runtime_dir()
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=build_settings(runtime_dir),
        create_schema_for_tests=True,
    )
    with TestClient(app) as client:
        home = client.get("/")
        script = client.get("/static/app.js")

    assert home.status_code == 200
    assert "DocuDiff" in home.text
    assert script.status_code == 200
    assert "Creating document versions" in script.text


def test_app_selects_ollama_provider_without_requiring_an_api_key() -> None:
    runtime_dir = _runtime_dir()
    settings = replace(build_settings(runtime_dir), llm_provider="ollama")
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=settings,
        create_schema_for_tests=True,
    )

    assert isinstance(app.state.assessment_service.provider, OllamaAssessmentProvider)
    with TestClient(app) as client:
        health = client.get("/health")
    assert health.json()["configured_assessment_provider"] == "ollama"
    assert health.json()["assessment_provider"] == "ollama"


def test_health_reports_when_a_missing_openai_key_uses_the_heuristic_adapter() -> None:
    runtime_dir = _runtime_dir()
    settings = replace(build_settings(runtime_dir), llm_provider="openai", openai_api_key=None)
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=settings,
        create_schema_for_tests=True,
    )

    with TestClient(app) as client:
        health = client.get("/health")

    assert health.json()["configured_assessment_provider"] == "openai"
    assert health.json()["assessment_provider"] == "heuristic"


def test_cross_document_comparisons_are_rejected() -> None:
    runtime_dir = _runtime_dir()
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=build_settings(runtime_dir),
        create_schema_for_tests=True,
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/documents",
            json={"title": "One", "content": "1. A\nBaseline", "version_label": "v1"},
        ).json()
        second = client.post(
            "/api/v1/documents",
            json={"title": "Two", "content": "1. A\nCandidate", "version_label": "v1"},
        ).json()
        response = client.post(
            "/api/v1/comparisons",
            json={
                "baseline_version_id": first["versions"][0]["id"],
                "candidate_version_id": second["versions"][0]["id"],
            },
        )
        assert response.status_code == 422
        assert "same document" in response.json()["detail"]


def test_text_file_upload_and_unsupported_extension_handling() -> None:
    runtime_dir = _runtime_dir()
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=build_settings(runtime_dir),
        create_schema_for_tests=True,
    )
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/documents/upload",
            data={"title": "Uploaded Terms", "version_label": "v1"},
            files={"file": ("terms.txt", b"1. Scope\nThe service is available.", "text/plain")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["versions"][0]["original_filename"] == "terms.txt"

        uploaded_version = client.post(
            f"/api/v1/documents/{uploaded.json()['id']}/versions/upload",
            data={"version_label": "v2"},
            files={"file": ("terms-v2.txt", b"1. Scope\nThe service is available for 15 days.", "text/plain")},
        )
        assert uploaded_version.status_code == 201
        assert uploaded_version.json()["original_filename"] == "terms-v2.txt"

        unsupported = client.post(
            "/api/v1/documents/upload",
            data={"title": "Unsupported", "version_label": "v1"},
            files={"file": ("terms.exe", b"not a document", "application/octet-stream")},
        )
        assert unsupported.status_code == 422
        assert "Unsupported file type" in unsupported.json()["detail"]


def test_section_and_raw_request_body_limits_are_enforced() -> None:
    runtime_dir = _runtime_dir()
    settings = replace(
        build_settings(runtime_dir),
        max_sections_per_version=2,
        max_upload_bytes=128,
    )
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=settings,
        create_schema_for_tests=True,
    )
    with TestClient(app) as client:
        too_many_sections = client.post(
            "/api/v1/documents",
            json={
                "title": "Structured Terms",
                "version_label": "v1",
                "content": "1. Scope\nOne.\n\n2. Payment\nTwo.\n\n3. Privacy\nThree.",
            },
        )
        assert too_many_sections.status_code == 422
        assert "section safety limit" in too_many_sections.json()["detail"]

        oversized = client.post(
            "/api/v1/documents",
            json={"title": "Too large", "content": "x" * 70_000},
        )
        assert oversized.status_code == 413
        assert "Request body exceeds" in oversized.json()["detail"]


class CountingRemoteProvider:
    requires_assessment_budget = True

    def __init__(self) -> None:
        self.calls = 0

    def assess(
        self, change_type: ChangeType, heading: str, old_text: str | None, new_text: str | None
    ) -> AssessmentResult:
        self.calls += 1
        return AssessmentResult(
            payload=AssessmentPayload(
                category="other",
                severity="low",
                summary=f"Remote assessment for {heading}.",
                rationale="This verifies that the remote-call safety budget is enforced.",
                needs_human_review=False,
            ),
            provider="counting_remote",
            validation_status="validated",
        )


class UnavailableModelProvider:
    requires_assessment_budget = True

    def __init__(self) -> None:
        self.calls = 0

    def assess(
        self, change_type: ChangeType, heading: str, old_text: str | None, new_text: str | None
    ) -> AssessmentResult:
        self.calls += 1
        raise RuntimeError("local model is unavailable")


def test_remote_assessment_calls_are_bounded_per_comparison() -> None:
    runtime_dir = _runtime_dir()
    settings = replace(build_settings(runtime_dir), max_assessment_calls=1)
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=settings,
        create_schema_for_tests=True,
    )
    provider = CountingRemoteProvider()
    app.state.assessment_service = SafeAssessmentService(provider)

    with TestClient(app) as client:
        document = client.post(
            "/api/v1/documents",
            json={
                "title": "Budgeted Terms",
                "version_label": "v1",
                "content": "1. Payment\n30 days.\n\n2. Privacy\nNo sharing.",
            },
        ).json()
        candidate = client.post(
            f"/api/v1/documents/{document['id']}/versions",
            json={
                "version_label": "v2",
                "content": "1. Payment\n15 days.\n\n2. Privacy\nAnalytics sharing allowed.",
            },
        ).json()
        comparison = client.post(
            "/api/v1/comparisons",
            json={
                "baseline_version_id": document["versions"][0]["id"],
                "candidate_version_id": candidate["id"],
            },
        )

    assert comparison.status_code == 201
    assert provider.calls == 1
    providers = {change["assessment"]["provider"] for change in comparison.json()["changes"]}
    assert "counting_remote" in providers
    assert "heuristic:budget_fallback" in providers


def test_unavailable_model_is_tried_once_then_the_comparison_falls_back() -> None:
    runtime_dir = _runtime_dir()
    app = create_app(
        f"sqlite:///{runtime_dir / 'docudiff.db'}",
        settings=build_settings(runtime_dir),
        create_schema_for_tests=True,
    )
    provider = UnavailableModelProvider()
    app.state.assessment_service = SafeAssessmentService(provider)

    with TestClient(app) as client:
        document = client.post(
            "/api/v1/documents",
            json={
                "title": "Unavailable Model Terms",
                "version_label": "v1",
                "content": "1. Payment\n30 days.\n\n2. Privacy\nNo sharing.",
            },
        ).json()
        candidate = client.post(
            f"/api/v1/documents/{document['id']}/versions",
            json={
                "version_label": "v2",
                "content": "1. Payment\n15 days.\n\n2. Privacy\nAnalytics sharing allowed.",
            },
        ).json()
        comparison = client.post(
            "/api/v1/comparisons",
            json={
                "baseline_version_id": document["versions"][0]["id"],
                "candidate_version_id": candidate["id"],
            },
        )

    assert comparison.status_code == 201
    assert provider.calls == 1
    assert {change["assessment"]["provider"] for change in comparison.json()["changes"]} == {
        "heuristic:fallback"
    }
