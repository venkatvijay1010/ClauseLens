"""Deterministic, one-to-one section alignment and diff candidate generation."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol

from app.models import ChangeType

SAFE_SEQUENCE_MATCHER_LIMIT = 8_000
MAX_FUZZY_ALIGNMENT_SECTIONS = 100


class SectionLike(Protocol):
    id: str
    ordinal: int
    heading: str
    normalized_heading: str
    content: str


@dataclass(frozen=True)
class DiffCandidate:
    change_type: ChangeType
    baseline: SectionLike | None
    candidate: SectionLike | None
    similarity: float

    @property
    def heading(self) -> str:
        return (self.candidate or self.baseline).heading  # type: ignore[union-attr]


def text_similarity(left: str, right: str) -> float:
    """Provide a display score without allowing pathological long-text matching work."""
    normalized_left = _comparison_text(left)
    normalized_right = _comparison_text(right)
    if normalized_left == normalized_right:
        return 1.0
    if max(len(normalized_left), len(normalized_right)) <= SAFE_SEQUENCE_MATCHER_LIMIT:
        return SequenceMatcher(None, normalized_left, normalized_right).ratio()
    prefix = _common_prefix_length(normalized_left, normalized_right)
    suffix = _common_suffix_length(normalized_left[prefix:], normalized_right[prefix:])
    return min(1.0, (prefix + suffix) / max(len(normalized_left), len(normalized_right), 1))


def heading_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _best_fuzzy_match(source: SectionLike, candidates: list[SectionLike]) -> SectionLike | None:
    scored = [(heading_similarity(source.normalized_heading, candidate.normalized_heading), candidate) for candidate in candidates]
    if not scored:
        return None
    score, candidate = max(scored, key=lambda pair: pair[0])
    return candidate if score >= 0.82 else None


def _comparison_text(text: str) -> str:
    return " ".join(text.split())


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        length += 1
    return length


def _common_suffix_length(left: str, right: str) -> int:
    length = 0
    max_length = min(len(left), len(right))
    while length < max_length and left[-(length + 1)] == right[-(length + 1)]:
        length += 1
    return length


def build_diff(baseline_sections: list[SectionLike], candidate_sections: list[SectionLike]) -> list[DiffCandidate]:
    """Match exact headings first, fuzzy headings once, then emit only meaningful candidates."""
    candidate_indices_by_heading: dict[str, deque[int]] = defaultdict(deque)
    for index, candidate in enumerate(candidate_sections):
        candidate_indices_by_heading[candidate.normalized_heading].append(index)

    remaining_baseline: list[SectionLike] = []
    matched_candidate_indices: set[int] = set()
    matches: list[tuple[SectionLike, SectionLike]] = []

    # Exact normalized headings are indexed, deterministic, and preferred over fuzzy similarity.
    for baseline in baseline_sections:
        candidate_indexes = candidate_indices_by_heading.get(baseline.normalized_heading)
        if candidate_indexes:
            candidate_index = candidate_indexes.popleft()
            matched_candidate_indices.add(candidate_index)
            matches.append((baseline, candidate_sections[candidate_index]))
        else:
            remaining_baseline.append(baseline)

    remaining_candidate = [
        candidate
        for index, candidate in enumerate(candidate_sections)
        if index not in matched_candidate_indices
    ]

    # Fuzzy heading alignment is intentionally conservative. Skip it for large unmatched sets
    # rather than allowing an O(n²) request to consume the API worker.
    if (
        len(remaining_baseline) <= MAX_FUZZY_ALIGNMENT_SECTIONS
        and len(remaining_candidate) <= MAX_FUZZY_ALIGNMENT_SECTIONS
    ):
        for baseline in list(remaining_baseline):
            fuzzy = _best_fuzzy_match(baseline, remaining_candidate)
            if fuzzy:
                matches.append((baseline, fuzzy))
                remaining_baseline.remove(baseline)
                remaining_candidate.remove(fuzzy)

    candidates: list[DiffCandidate] = []
    for baseline, candidate in matches:
        headings_match = baseline.normalized_heading == candidate.normalized_heading
        content_matches = _comparison_text(baseline.content) == _comparison_text(candidate.content)
        similarity = text_similarity(baseline.content, candidate.content)
        if headings_match and content_matches:
            if baseline.ordinal != candidate.ordinal:
                candidates.append(DiffCandidate(ChangeType.MOVED, baseline, candidate, similarity))
            continue
        candidates.append(DiffCandidate(ChangeType.MODIFIED, baseline, candidate, similarity))

    candidates.extend(
        DiffCandidate(ChangeType.REMOVED, baseline, None, 0.0) for baseline in remaining_baseline
    )
    candidates.extend(
        DiffCandidate(ChangeType.ADDED, None, candidate, 0.0) for candidate in remaining_candidate
    )
    return sorted(
        candidates,
        key=lambda item: min(
            item.baseline.ordinal if item.baseline else 10_000,
            item.candidate.ordinal if item.candidate else 10_000,
        ),
    )


def excerpt(text: str | None, limit: int = 450) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1].rstrip()}…"


def _context_excerpt(text: str | None, changed_start: int, changed_end: int, limit: int) -> str | None:
    if not text:
        return None
    compact = _comparison_text(text)
    if len(compact) <= limit:
        return compact
    center = max(changed_start, min((changed_start + changed_end) // 2, len(compact) - 1))
    start = max(0, min(center - limit // 2, len(compact) - limit))
    end = min(len(compact), start + limit)
    value = compact[start:end]
    if start:
        value = f"…{value}"
    if end < len(compact):
        value = f"{value}…"
    return value


def evidence_excerpts(old_text: str | None, new_text: str | None, limit: int = 450) -> tuple[str | None, str | None]:
    """Return bounded, contiguous source excerpts centered on the changed region.

    The compacted excerpts remain verifiable against source text after whitespace normalization.
    """
    if not old_text or not new_text:
        return excerpt(old_text, limit), excerpt(new_text, limit)
    old_compact = _comparison_text(old_text)
    new_compact = _comparison_text(new_text)
    prefix = _common_prefix_length(old_compact, new_compact)
    old_tail = old_compact[prefix:]
    new_tail = new_compact[prefix:]
    suffix = _common_suffix_length(old_tail, new_tail)
    old_end = len(old_compact) - suffix
    new_end = len(new_compact) - suffix
    return (
        _context_excerpt(old_text, prefix, old_end, limit),
        _context_excerpt(new_text, prefix, new_end, limit),
    )
