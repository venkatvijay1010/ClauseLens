"""Evidence validation independent from an LLM's explanation."""

from __future__ import annotations


def citation_is_valid(source_text: str | None, excerpt: str | None) -> bool:
    """A displayed excerpt must map back to stored source text after whitespace normalization."""
    if not excerpt:
        return source_text is None
    if not source_text:
        return False
    source_compact = " ".join(source_text.split())
    excerpt_compact = " ".join(excerpt.replace("…", "").split())
    return bool(excerpt_compact) and excerpt_compact in source_compact


def change_evidence_is_valid(
    old_text: str | None, old_excerpt: str | None, new_text: str | None, new_excerpt: str | None
) -> bool:
    return citation_is_valid(old_text, old_excerpt) and citation_is_valid(new_text, new_excerpt)
