"""Safe extraction for the deliberately small ClauseLens file-format surface."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


class DocumentExtractionError(ValueError):
    """Raised when a document cannot be safely extracted in the MVP."""


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_count: int


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_PDF_PAGES = 500
MAX_DOCX_ARCHIVE_MEMBERS = 500
DOCX_EXPANSION_MULTIPLIER = 16


def normalize_text(text: str) -> str:
    """Normalize layout noise while retaining legal/semantic punctuation and values."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join only line-break hyphenation such as "termina-\ntion". Original raw text is still stored.
    normalized = re.sub(r"(?<=\w)-\n(?=\w)", "", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _validate_text(text: str, max_extracted_chars: int) -> str:
    normalized = normalize_text(text)
    if not normalized:
        raise DocumentExtractionError(
            "No text could be extracted. Scanned or image-only PDFs are not supported in v1."
        )
    if len(normalized) > max_extracted_chars:
        raise DocumentExtractionError(
            f"Extracted text exceeds the {max_extracted_chars:,}-character safety limit."
        )
    return normalized


def _validate_docx_archive(content: bytes, max_extracted_chars: int) -> None:
    """Reject zip bombs before python-docx loads the archive into document structures."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            expanded_size = sum(member.file_size for member in members)
    except zipfile.BadZipFile as exc:
        raise DocumentExtractionError("Could not read this DOCX file.") from exc

    max_expanded_bytes = max_extracted_chars * DOCX_EXPANSION_MULTIPLIER
    if len(members) > MAX_DOCX_ARCHIVE_MEMBERS or expanded_size > max_expanded_bytes:
        raise DocumentExtractionError(
            "DOCX archive exceeds the safe expansion limit for this v1 service."
        )


def extract_document(filename: str, content: bytes, max_extracted_chars: int) -> ExtractedDocument:
    """Extract supported uploaded files without trusting their filename as a path."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentExtractionError(f"Unsupported file type '{extension or 'unknown'}'. Use: {supported}.")

    if extension in {".txt", ".md"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Text files must be UTF-8 encoded.") from exc
        return ExtractedDocument(text=_validate_text(text, max_extracted_chars), page_count=1)

    if extension == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise DocumentExtractionError("Encrypted PDFs are not supported in v1.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise DocumentExtractionError(
                    f"PDF has more than the {MAX_PDF_PAGES}-page safety limit."
                )
            pages: list[str] = []
            extracted_length = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                extracted_length += len(page_text)
                if extracted_length > max_extracted_chars:
                    raise DocumentExtractionError(
                        f"Extracted text exceeds the {max_extracted_chars:,}-character safety limit."
                    )
                pages.append(page_text)
        except DocumentExtractionError:
            raise
        except Exception as exc:  # pypdf exposes multiple parser exception classes
            raise DocumentExtractionError("Could not read this PDF. It may be malformed or unsupported.") from exc
        return ExtractedDocument(
            text=_validate_text("\n\f\n".join(pages), max_extracted_chars), page_count=len(pages)
        )

    try:
        from docx import Document

        _validate_docx_archive(content, max_extracted_chars)
        document = Document(io.BytesIO(content))
        paragraphs: list[str] = []
        extracted_length = 0
        for paragraph in document.paragraphs:
            extracted_length += len(paragraph.text)
            if extracted_length > max_extracted_chars:
                raise DocumentExtractionError(
                    f"Extracted text exceeds the {max_extracted_chars:,}-character safety limit."
                )
            paragraphs.append(paragraph.text)
    except Exception as exc:
        if isinstance(exc, DocumentExtractionError):
            raise
        raise DocumentExtractionError("Could not read this DOCX file.") from exc
    return ExtractedDocument(text=_validate_text("\n".join(paragraphs), max_extracted_chars), page_count=1)
