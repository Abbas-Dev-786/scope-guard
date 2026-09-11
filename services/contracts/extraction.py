from __future__ import annotations

import hashlib
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from xml.etree import ElementTree

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 100
MAX_CHARS = 250_000
MAX_DOCX_EXPANDED_BYTES = 50 * 1024 * 1024
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


class ExtractionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ExtractedChunk:
    index: int
    text: str
    start_offset: int
    end_offset: int
    page_number: int | None = None
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    mime_type: str
    sha256: str
    size_bytes: int
    text: str
    chunks: tuple[ExtractedChunk, ...]
    page_count: int | None
    extractor_version: str = "scopeguard-extractor-1"


def _check_limits(content: bytes, declared_size: int | None) -> None:
    if declared_size is not None and declared_size != len(content):
        raise ExtractionError("size_mismatch", "Uploaded size does not match the declared size")
    if len(content) > MAX_BYTES:
        raise ExtractionError("size_limit", "Documents are limited to 10 MiB")


def _chunk_text(text: str, *, page_count: int | None = None) -> tuple[ExtractedChunk, ...]:
    if not text.strip():
        raise ExtractionError("no_extractable_text", "The document contains no extractable text")
    if len(text) > MAX_CHARS:
        raise ExtractionError("character_limit", "Extracted text is limited to 250,000 characters")
    chunks: list[ExtractedChunk] = []
    cursor = 0
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
    for index, paragraph in enumerate(paragraphs):
        start = text.find(paragraph, cursor)
        if start < 0:
            start = cursor
        end = start + len(paragraph)
        chunks.append(
            ExtractedChunk(
                index=index,
                text=paragraph,
                start_offset=start,
                end_offset=end,
                page_number=min(index + 1, page_count) if page_count else None,
            )
        )
        cursor = end
    return tuple(chunks)


def _extract_pdf(content: bytes) -> tuple[str, int]:
    if not content.startswith(b"%PDF-"):
        raise ExtractionError("magic_mismatch", "The PDF signature is invalid")
    if b"/Encrypt" in content[:2_000_000]:
        raise ExtractionError("encrypted_pdf", "Encrypted PDFs require a decrypted re-upload")
    page_count = len(re.findall(rb"/Type\s*/Page\b", content))
    if page_count > MAX_PAGES:
        raise ExtractionError("page_limit", "Documents are limited to 100 pages")
    values: list[str] = []
    for match in re.finditer(rb"\((.*?)\)\s*T[Jj]", content, flags=re.DOTALL):
        raw = match.group(1).replace(rb"\\(", b"(").replace(rb"\\)", b")").replace(rb"\\n", b"\n")
        values.append(raw.decode("utf-8", errors="replace"))
    text = "\n\n".join(values)
    if not text.strip():
        raise ExtractionError("scanned_pdf", "Scanned-only PDFs require manual handling; OCR is not enabled")
    return text, max(page_count, 1)


def _extract_docx(content: bytes) -> tuple[str, int]:
    if not content.startswith(b"PK"):
        raise ExtractionError("magic_mismatch", "The DOCX archive signature is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            expanded = sum(info.file_size for info in archive.infolist())
            if expanded > MAX_DOCX_EXPANDED_BYTES:
                raise ExtractionError("expansion_limit", "DOCX expanded content exceeds 50 MiB")
            try:
                xml = archive.read("word/document.xml")
            except KeyError as exc:
                raise ExtractionError("corrupt_document", "DOCX document.xml is missing") from exc
    except zipfile.BadZipFile as exc:
        raise ExtractionError("corrupt_document", "The DOCX archive is corrupt") from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ExtractionError("corrupt_document", "The DOCX XML is invalid") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        value = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if value.strip():
            paragraphs.append(value.strip())
    page_count = 1 + sum(1 for node in root.iter(f"{namespace}br") if node.attrib.get(f"{namespace}type") == "page")
    if page_count > MAX_PAGES:
        raise ExtractionError("page_limit", "Documents are limited to 100 pages")
    return "\n\n".join(paragraphs), page_count


def extract_document(content: bytes, *, mime_type: str, declared_size: int | None = None) -> ExtractionResult:
    _check_limits(content, declared_size)
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ExtractionError("unsupported_type", "Unsupported document type; only PDF, DOCX, TXT, and Markdown files are supported")
    if mime_type in {"text/plain", "text/markdown"}:
        if b"\x00" in content:
            raise ExtractionError("binary_text", "Text files must not contain binary content")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExtractionError("invalid_encoding", "Text files must use UTF-8") from exc
        page_count = None
    elif mime_type == "application/pdf":
        text, page_count = _extract_pdf(content)
    else:
        text, page_count = _extract_docx(content)
    chunks = _chunk_text(text, page_count=page_count)
    return ExtractionResult(
        mime_type=mime_type,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        text=text,
        chunks=chunks,
        page_count=page_count,
    )


def extract_document_bounded(
    content: bytes,
    *,
    mime_type: str,
    declared_size: int | None = None,
    timeout_seconds: float = 120.0,
) -> ExtractionResult:
    """Run extraction behind a bounded worker so malformed input cannot block a request forever."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="contract-extract")
    future = executor.submit(extract_document, content, mime_type=mime_type, declared_size=declared_size)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise ExtractionError("timeout", "Document extraction exceeded its time limit") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
