from app.models import ChangeType
from app.services.citation import change_evidence_is_valid
from app.services.diff_engine import build_diff, evidence_excerpts
from app.services.sectioning import split_into_sections


def test_heading_aware_diff_detects_modified_added_and_removed_sections() -> None:
    baseline = split_into_sections(
        """1. Payment Terms
Invoices are due in 30 days.

2. Support
Support is available by email."""
    )
    candidate = split_into_sections(
        """1. Payment Terms
Invoices are due in 15 days.

2. Privacy
We process personal data for analytics."""
    )

    changes = build_diff(baseline, candidate)
    actual = {(change.heading, change.change_type) for change in changes}

    assert ("Payment Terms", ChangeType.MODIFIED) in actual
    assert ("Support", ChangeType.REMOVED) in actual
    assert ("Privacy", ChangeType.ADDED) in actual


def test_moved_unchanged_section_is_not_reported_as_added_and_removed() -> None:
    baseline = split_into_sections(
        """1. Scope
The scope is unchanged.

2. Payment
Invoices are due in 30 days."""
    )
    candidate = split_into_sections(
        """1. Payment
Invoices are due in 30 days.

2. Scope
The scope is unchanged."""
    )

    changes = build_diff(baseline, candidate)
    actual = {(change.heading, change.change_type) for change in changes}

    assert ("Scope", ChangeType.MOVED) in actual
    assert ("Payment", ChangeType.MOVED) in actual


def test_headingless_text_uses_document_fallback() -> None:
    sections = split_into_sections("A short document without formal headings.")

    assert len(sections) == 1
    assert sections[0].heading == "Document"


def test_preamble_is_preserved_and_compared_as_introduction() -> None:
    baseline = split_into_sections(
        """Vendor Terms
Invoices are due in 30 days.

1. Scope
The service is included."""
    )
    candidate = split_into_sections(
        """Vendor Terms
Invoices are due in 15 days.

1. Scope
The service is included."""
    )

    changes = build_diff(baseline, candidate)

    assert [(change.heading, change.change_type) for change in changes] == [
        ("Introduction", ChangeType.MODIFIED)
    ]


def test_fuzzy_matched_heading_rename_is_a_real_change() -> None:
    baseline = split_into_sections("1. Payment Terms\nInvoices are due in 30 days.")
    candidate = split_into_sections("1. Payment Term\nInvoices are due in 30 days.")

    changes = build_diff(baseline, candidate)

    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.MODIFIED
    assert changes[0].baseline.heading == "Payment Terms"
    assert changes[0].candidate.heading == "Payment Term"


def test_long_late_change_remains_detected_and_evidence_contains_changed_values() -> None:
    unchanged = "Unchanged clause text. " * 900
    old_text = f"1. Payment Terms\n{unchanged}Invoices are due in 30 days."
    new_text = f"1. Payment Terms\n{unchanged}Invoices are due in 15 days."

    changes = build_diff(split_into_sections(old_text), split_into_sections(new_text))
    change = changes[0]
    old_excerpt, new_excerpt = evidence_excerpts(change.baseline.content, change.candidate.content)

    assert change.change_type == ChangeType.MODIFIED
    assert "30 days" in old_excerpt
    assert "15 days" in new_excerpt
    assert old_excerpt != new_excerpt
    assert change_evidence_is_valid(change.baseline.content, old_excerpt, change.candidate.content, new_excerpt)


def test_numeric_clause_content_is_not_misparsed_as_a_heading() -> None:
    baseline = split_into_sections("1. Payment\n30 days.\n\n2. Privacy\nNo sharing.")
    candidate = split_into_sections("1. Payment\n15 days.\n\n2. Privacy\nAnalytics sharing allowed.")

    changes = build_diff(baseline, candidate)

    assert {(change.heading, change.change_type) for change in changes} == {
        ("Payment", ChangeType.MODIFIED),
        ("Privacy", ChangeType.MODIFIED),
    }


def test_large_unmatched_sets_skip_fuzzy_heading_alignment() -> None:
    baseline = split_into_sections(
        "\n\n".join(f"{index}. Important Clause {index} Old\nBaseline text." for index in range(1, 102))
    )
    candidate = split_into_sections(
        "\n\n".join(f"{index}. Important Clause {index} New\nCandidate text." for index in range(1, 102))
    )

    changes = build_diff(baseline, candidate)

    assert len(changes) == 202
    assert {change.change_type for change in changes} == {ChangeType.ADDED, ChangeType.REMOVED}
