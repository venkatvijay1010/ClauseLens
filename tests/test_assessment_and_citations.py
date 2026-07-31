import io
import zipfile

from app.models import ChangeType, Severity
from app.services.assessment import HeuristicAssessmentProvider, SafeAssessmentService
from app.services.citation import change_evidence_is_valid
from app.services.document_parser import DocumentExtractionError, _validate_docx_archive


class FailingProvider:
    def assess(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")


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
