"""Heading-aware section splitting that keeps source order and page anchors."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.document_parser import normalize_text


@dataclass(frozen=True)
class ParsedSection:
    ordinal: int
    heading: str
    normalized_heading: str
    content: str
    page_number: int


class SectionLimitError(ValueError):
    """Raised before an adversarially structured document can create too many sections."""


MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+){0,4}[.)]?)\s+(.+?)\s*$")
ALL_CAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9 /&,:;()\-]{3,100}$")


def normalize_heading(heading: str) -> str:
    value = re.sub(r"^\d+(?:\.\d+){0,4}[.)]?\s*", "", heading.strip().lower())
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _heading_from_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    markdown = MARKDOWN_HEADING.match(stripped)
    if markdown:
        return markdown.group(1).strip()
    numbered = NUMBERED_HEADING.match(stripped)
    if numbered:
        heading = numbered.group(1).strip()
        # Do not turn a wrapped clause such as "30 days." into a section heading.
        # The MVP accepts conventional, title-cased numbered headings only.
        if (
            len(heading) <= 120
            and heading[0].isupper()
            and not heading.endswith((".", "!", "?"))
        ):
            return heading
    if ALL_CAPS_HEADING.match(stripped) and len(stripped.split()) <= 12:
        return stripped.title()
    return None


def split_into_sections(text: str, max_sections: int | None = None) -> list[ParsedSection]:
    """Split a document using headings, with a whole-document fallback for weak structure."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[ParsedSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    current_page = 1
    section_page = 1
    found_heading = False

    def append_section(section: ParsedSection) -> None:
        if max_sections is not None and len(sections) >= max_sections:
            raise SectionLimitError(f"Document exceeds the {max_sections} section safety limit.")
        sections.append(section)

    def flush_current_section() -> None:
        nonlocal current_heading, current_lines, section_page
        content = normalize_text("\n".join(current_lines)) if current_lines else ""
        if current_heading and content:
            append_section(
                ParsedSection(
                    ordinal=len(sections) + 1,
                    heading=current_heading,
                    normalized_heading=normalize_heading(current_heading),
                    content=content,
                    page_number=section_page,
                )
            )

    def flush_preamble() -> None:
        content = normalize_text("\n".join(current_lines)) if current_lines else ""
        if content:
            append_section(
                ParsedSection(
                    ordinal=len(sections) + 1,
                    heading="Introduction",
                    normalized_heading="introduction",
                    content=content,
                    page_number=section_page,
                )
            )

    for line in raw_lines:
        if "\f" in line:
            # Preserve text around page breaks but advance source anchor for future sections.
            fragments = line.split("\f")
            for index, fragment in enumerate(fragments):
                if fragment:
                    current_lines.append(fragment)
                if index < len(fragments) - 1:
                    current_page += 1
            continue
        heading = _heading_from_line(line)
        if heading:
            if current_heading:
                flush_current_section()
            elif found_heading:
                flush_current_section()
            else:
                flush_preamble()
            found_heading = True
            current_heading = heading
            current_lines = []
            section_page = current_page
        else:
            current_lines.append(line)
    if current_heading:
        flush_current_section()

    if sections:
        return sections

    fallback = normalize_text(text)
    return [
        ParsedSection(
            ordinal=1,
            heading="Document",
            normalized_heading="document",
            content=fallback,
            page_number=1,
        )
    ]
