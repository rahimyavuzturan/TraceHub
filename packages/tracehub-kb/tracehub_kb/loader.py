"""Load and validate knowledge base markdown documents.

A document is a YAML frontmatter block delimited by ``---`` followed by the
markdown body. Validation errors carry the offending line number so the author
can jump straight to it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from tracehub_kb.schema import (
    DIRECTORY_BY_TYPE,
    FRONTMATTER_BY_TYPE,
    SLUG_PATTERN,
    BaseFrontmatter,
    DocumentType,
)

FRONTMATTER_DELIMITER = "---"
# Excluded from validation: raw, unreviewed AzDO Wiki output (T1.6).
IGNORED_DIRECTORIES = frozenset({"imported"})


@dataclass(frozen=True)
class DocumentError:
    """A single problem found in a document."""

    path: Path
    message: str
    line: int | None = None

    def format(self, *, root: Path | None = None) -> str:
        location = self.path.relative_to(root) if root else self.path
        where = f"{location}:{self.line}" if self.line else str(location)
        return f"{where} - {self.message}"


@dataclass(frozen=True)
class Document:
    """A validated knowledge base document."""

    path: Path
    slug: str
    frontmatter: BaseFrontmatter
    body: str
    content_hash: str

    @property
    def doc_type(self) -> DocumentType:
        return self.frontmatter.type

    @property
    def title(self) -> str:
        return self.frontmatter.title

    @property
    def search_aliases(self) -> list[str]:
        """Title plus aliases - what a user might type to find this document."""
        return [self.frontmatter.title.casefold(), *self.frontmatter.aliases]


@dataclass
class LoadResult:
    """Outcome of loading a directory tree."""

    documents: list[Document] = field(default_factory=list)
    errors: list[DocumentError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class DocumentParseError(Exception):
    """Raised when a single document cannot be parsed or validated."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


def split_frontmatter(text: str) -> tuple[str, str, int]:
    """Split raw file content into (frontmatter, body, body_start_line).

    Returns the 1-based line number where the body begins, which lets chunking
    report real file positions later.
    """
    text = text.lstrip("\ufeff")
    if not text.lstrip().startswith(FRONTMATTER_DELIMITER):
        raise DocumentParseError("Doküman '---' ile başlayan frontmatter bloğu içermeli.", line=1)

    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip())
    closing: int | None = None
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            closing = index
            break

    if closing is None:
        raise DocumentParseError(
            "Frontmatter bloğu kapatılmamış. İkinci bir '---' satırı ekleyin.",
            line=len(lines),
        )

    frontmatter = "\n".join(lines[start + 1 : closing])
    body = "\n".join(lines[closing + 1 :]).strip()
    return frontmatter, body, closing + 2


def parse_document(path: Path, *, text: str | None = None) -> Document:
    """Parse and validate one document. Raises ``DocumentParseError`` on failure."""
    # utf-8-sig: Windows editors (and PowerShell) happily write a BOM, which
    # would otherwise hide the opening '---'.
    raw = text if text is not None else path.read_text(encoding="utf-8-sig")
    frontmatter_text, body, _ = split_frontmatter(raw)

    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise DocumentParseError(
            f"Frontmatter geçerli YAML değil: {exc}", line=_yaml_error_line(exc)
        ) from exc

    if not isinstance(data, dict):
        raise DocumentParseError("Frontmatter bir anahtar-değer bloğu olmalı.", line=2)

    doc_type = _resolve_type(data, frontmatter_text)
    model = FRONTMATTER_BY_TYPE[doc_type]

    try:
        frontmatter = model.model_validate(data)
    except ValidationError as exc:
        raise _validation_error(exc, frontmatter_text) from exc

    if not body:
        raise DocumentParseError("Doküman gövdesi boş. Frontmatter tek başına yeterli değil.")

    slug = path.stem.casefold()
    if not SLUG_PATTERN.match(slug):
        raise DocumentParseError(
            f"Dosya adı '{path.name}' küçük harf, rakam ve tire/alt tire içermeli "
            "(örn. 'mobil-sube-web.md')."
        )

    expected_dir = DIRECTORY_BY_TYPE[doc_type]
    if path.parent.name != expected_dir:
        raise DocumentParseError(
            f"'{doc_type.value}' tipindeki doküman '{expected_dir}/' klasöründe olmalı, "
            f"'{path.parent.name}/' içinde bulundu.",
            line=_line_of_key(frontmatter_text, "type"),
        )

    return Document(
        path=path,
        slug=slug,
        frontmatter=frontmatter,
        body=body,
        content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def iter_document_paths(root: Path) -> Iterator[Path]:
    """Yield every markdown file that should be validated, in stable order."""
    for path in sorted(root.rglob("*.md")):
        if IGNORED_DIRECTORIES & set(path.relative_to(root).parts[:-1]):
            continue
        yield path


def load_directory(root: Path) -> LoadResult:
    """Load every document under ``root``, collecting errors instead of raising.

    Duplicate slugs are reported as errors: the slug is the stable identifier
    used by ``depends_on`` references and by the ingest pipeline.
    """
    result = LoadResult()
    if not root.exists():
        result.errors.append(
            DocumentError(path=root, message=f"Bilgi tabanı klasörü bulunamadı: {root}")
        )
        return result

    seen: dict[str, Path] = {}
    for path in iter_document_paths(root):
        try:
            document = parse_document(path)
        except DocumentParseError as exc:
            result.errors.append(DocumentError(path=path, message=exc.message, line=exc.line))
            continue
        except OSError as exc:
            result.errors.append(DocumentError(path=path, message=f"Dosya okunamadı: {exc}"))
            continue

        previous = seen.get(document.slug)
        if previous is not None:
            result.errors.append(
                DocumentError(
                    path=path,
                    message=(
                        f"'{document.slug}' kimliği zaten kullanılıyor: "
                        f"{previous.relative_to(root)}"
                    ),
                )
            )
            continue

        seen[document.slug] = path
        result.documents.append(document)

    return result


def _resolve_type(data: dict[str, Any], frontmatter_text: str) -> DocumentType:
    raw_type = data.get("type")
    if raw_type is None:
        raise DocumentParseError(
            "'type' alanı zorunlu. Geçerli değerler: " + ", ".join(t.value for t in DocumentType),
            line=2,
        )
    try:
        return DocumentType(str(raw_type))
    except ValueError as exc:
        raise DocumentParseError(
            f"'{raw_type}' geçerli bir doküman tipi değil. Geçerli değerler: "
            + ", ".join(t.value for t in DocumentType),
            line=_line_of_key(frontmatter_text, "type"),
        ) from exc


def _validation_error(exc: ValidationError, frontmatter_text: str) -> DocumentParseError:
    """Turn a pydantic error into a single Turkish message with a line number."""
    problems: list[str] = []
    first_line: int | None = None

    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "frontmatter"
        problems.append(f"{location}: {_translate(error)}")
        if first_line is None and error["loc"]:
            first_line = _line_of_key(frontmatter_text, str(error["loc"][0]))

    return DocumentParseError("Frontmatter hatalı -> " + "; ".join(problems), line=first_line)


def _translate(error: Any) -> str:
    """Map the common pydantic error types to Turkish."""
    error_type = error.get("type", "")
    if error_type == "missing":
        return "zorunlu alan eksik"
    if error_type == "extra_forbidden":
        return "tanımlı olmayan alan (yazım hatası olabilir)"
    if error_type == "string_too_short":
        return "boş bırakılamaz"
    if error_type in {"too_short", "list_type"}:
        return "en az bir öğe içermeli"
    return str(error.get("msg", "geçersiz değer"))


def _line_of_key(frontmatter_text: str, key: str) -> int | None:
    """Find the 1-based file line of a top-level frontmatter key."""
    for offset, line in enumerate(frontmatter_text.splitlines()):
        if line.startswith(f"{key}:"):
            return offset + 2  # +1 for the opening '---', +1 for 1-based lines
    return None


def _yaml_error_line(exc: yaml.YAMLError) -> int | None:
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return None
    line: int = mark.line
    return line + 2
