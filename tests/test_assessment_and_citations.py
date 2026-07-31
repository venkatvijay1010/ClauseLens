import io
import json
import zipfile
from unittest.mock import patch
from urllib.error import URLError

from app.models import ChangeType, Severity
from app.services.assessment import (
    HeuristicAssessmentProvider,
    OllamaAssessmentProvider,
    SafeAssessmentService,
)
from app.services.citation import change_evidence_is_valid
from app.services.document_parser import DocumentExtractionError, _validate_docx_archive


class FailingProvider:
    def assess(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_heuristic_flags_payment_change_for_review() -> None:
    result = HeuristicAssessmentProvider().assess(
        ChangeType.MODIFIED,
        "Payment Terms",
        "Invoices are due in 30 days.",
        "Invoices are due in 15 days and include a late fee.",
    )

    assert result.payload.severity == Severity.HIGH
    assert result.payload.needs_human_review is True
    assert result.validation_status == "validated"


def test_provider_failure_keeps_a_safe_fallback_assessment() -> None:
    service = SafeAssessmentService(FailingProvider())

    result = service.assess(ChangeType.ADDED, "Privacy", None, "We share personal data.")

    assert result.provider == "heuristic:fallback"
    assert result.validation_status == "fallback_after_provider_error"


def test_ollama_provider_sends_schema_constrained_non_streaming_request() -> None:
    provider = OllamaAssessmentProvider("http://localhost:11434", "gemma3", timeout_seconds=4)
    assert OllamaAssessmentProvider("http://localhost:11434/api", "gemma3", 4).endpoint == (
        "http://localhost:11434/api/chat"
    )
    structured_content = json.dumps(
        {
            "category": "payment",
            "severity": "high",
            "summary": "Payment timing was shortened from 30 to 15 days.",
            "rationale": "The revised excerpt materially accelerates the invoice due date.",
            "needs_human_review": True,
        }
    )
    with patch(
        "app.services.assessment.urlopen",
        return_value=FakeHttpResponse({"message": {"content": structured_content}}),
    ) as mocked_urlopen:
        result = provider.assess(
            ChangeType.MODIFIED,
            "Payment Terms",
            "Invoices are due in 30 days.",
            "Invoices are due in 15 days.",
        )

    request = mocked_urlopen.call_args.args[0]
    request_body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://localhost:11434/api/chat"
    assert mocked_urlopen.call_args.kwargs["timeout"] == 4
    assert request_body["model"] == "gemma3"
    assert request_body["stream"] is False
    assert request_body["options"]["temperature"] == 0
    assert request_body["format"]["type"] == "object"
    assert result.provider == "ollama"
    assert result.payload.severity == Severity.HIGH


def test_ollama_provider_failure_uses_the_heuristic_fallback() -> None:
    service = SafeAssessmentService(
        OllamaAssessmentProvider("http://localhost:11434", "gemma3", timeout_seconds=1)
    )
    with patch("app.services.assessment.urlopen", side_effect=URLError("not running")):
        result = service.assess(ChangeType.ADDED, "Privacy", None, "We share personal data.")

    assert service.uses_bounded_model_provider is True
    assert result.provider == "heuristic:fallback"
    assert result.validation_status == "fallback_after_provider_error"


def test_invalid_ollama_structured_output_uses_the_heuristic_fallback() -> None:
    service = SafeAssessmentService(
        OllamaAssessmentProvider("http://localhost:11434", "gemma3", timeout_seconds=1)
    )
    with patch(
        "app.services.assessment.urlopen",
        return_value=FakeHttpResponse({"message": {"content": '{"category":"unknown"}'}}),
    ):
        result = service.assess(ChangeType.ADDED, "Privacy", None, "We share personal data.")

    assert result.provider == "heuristic:fallback"
    assert result.validation_status == "fallback_after_provider_error"


def test_citation_validation_rejects_unverifiable_excerpt() -> None:
    assert change_evidence_is_valid("Invoices are due in 30 days.", "Invoices are due in 30 days.", None, None)
    assert not change_evidence_is_valid("Invoices are due in 30 days.", "Invented evidence", None, None)


def test_docx_archive_expansion_is_limited_before_document_parsing() -> None:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * 2_000)

    try:
        _validate_docx_archive(content.getvalue(), max_extracted_chars=100)
    except DocumentExtractionError as exc:
        assert "expansion limit" in str(exc)
    else:
        raise AssertionError("Expected compressed DOCX expansion to be rejected.")
