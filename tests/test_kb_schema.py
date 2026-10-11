"""T1.1 - knowledge base schema and loader."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from tracehub_core.config import REPO_ROOT
from tracehub_kb import (
    CaseFrontmatter,
    Confidence,
    DocumentParseError,
    DocumentType,
    ServiceFrontmatter,
    load_directory,
    parse_document,
    split_frontmatter,
)
from tracehub_kb.loader import DIRECTORY_BY_TYPE
from tracehub_kb.schema import Deployment, normalise_environment

KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"


def write(tmp_path: Path, doc_type: DocumentType, name: str, content: str) -> Path:
    directory = tmp_path / DIRECTORY_BY_TYPE[doc_type]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(dedent(content).lstrip(), encoding="utf-8")
    return path


SERVICE_DOC = """
    ---
    type: service
    title: "Mobil Şube Web"
    aliases: ["mobil şube", "msube"]
    updated: 2026-09-30
    confidence: high
    deployments:
      - environment: dmz-preprod
        cluster: dmz-cluster
        namespace: dmz-mobile-prep
        workload: msube-web
    observability:
      elastic_indices: ["msube-web-*"]
      correlation_field: "traceId"
    ---

    # Mobil Şube Web

    Mobil isteklerini karşılayan web katmanı.
"""


# --- Frontmatter splitting ---------------------------------------------------


def test_split_frontmatter_returns_body_and_start_line() -> None:
    frontmatter, body, body_line = split_frontmatter(
        dedent(
            """
            ---
            type: glossary
            ---

            # Başlık

            Gövde.
            """
        ).lstrip()
    )

    assert "type: glossary" in frontmatter
    assert body.startswith("# Başlık")
    assert body_line == 4


def test_missing_frontmatter_is_reported_at_line_one() -> None:
    with pytest.raises(DocumentParseError) as exc_info:
        split_frontmatter("# Sadece markdown\n")

    assert exc_info.value.line == 1
    assert "frontmatter" in exc_info.value.message


def test_unclosed_frontmatter_is_detected() -> None:
    with pytest.raises(DocumentParseError, match="kapatılmamış"):
        split_frontmatter("---\ntype: glossary\ntitle: x\n")


def test_utf8_bom_is_tolerated(tmp_path: Path) -> None:
    """Windows editors and PowerShell write a BOM; it must not hide the '---'."""
    directory = tmp_path / "service_catalog"
    directory.mkdir(parents=True)
    path = directory / "msube-web.md"
    path.write_text(dedent(SERVICE_DOC).lstrip(), encoding="utf-8-sig")

    document = parse_document(path)

    assert document.title == "Mobil Şube Web"


# --- Validation errors -------------------------------------------------------


def test_missing_required_field_reports_turkish_message(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        DocumentType.GLOSSARY,
        "eksik.md",
        """
        ---
        type: glossary
        updated: 2026-09-30
        ---

        Gövde.
        """,
    )

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(path)

    assert "title" in exc_info.value.message
    assert "zorunlu alan eksik" in exc_info.value.message


def test_unknown_field_is_rejected_with_a_line_number(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        DocumentType.GLOSSARY,
        "yazim-hatasi.md",
        """
        ---
        type: glossary
        title: "Sözlük"
        updated: 2026-09-30
        titel: "yazım hatası"
        ---

        Gövde.
        """,
    )

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(path)

    assert "tanımlı olmayan alan" in exc_info.value.message
    assert exc_info.value.line == 5, "hatalı alanın satırı gösterilmeli"


def test_invalid_yaml_reports_a_line_number(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        DocumentType.GLOSSARY,
        "bozuk.md",
        """
        ---
        type: glossary
        title: "Sözlük
        updated: 2026-09-30
        ---

        Gövde.
        """,
    )

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(path)

    assert "YAML" in exc_info.value.message
    assert exc_info.value.line is not None


def test_unknown_document_type_lists_valid_values(tmp_path: Path) -> None:
    directory = tmp_path / "glossary"
    directory.mkdir(parents=True)
    path = directory / "tip.md"
    path.write_text(
        dedent(
            """
            ---
            type: wiki
            title: "Yanlış tip"
            updated: 2026-09-30
            ---

            Gövde.
            """
        ).lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(path)

    assert "service" in exc_info.value.message
    assert "runbook" in exc_info.value.message


def test_empty_body_is_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        DocumentType.GLOSSARY,
        "bos.md",
        """
        ---
        type: glossary
        title: "Sözlük"
        updated: 2026-09-30
        ---
        """,
    )

    with pytest.raises(DocumentParseError, match="gövdesi boş"):
        parse_document(path)


def test_document_must_live_in_its_type_directory(tmp_path: Path) -> None:
    directory = tmp_path / "cases"
    directory.mkdir(parents=True)
    path = directory / "yanlis-klasor.md"
    path.write_text(dedent(SERVICE_DOC).lstrip(), encoding="utf-8")

    with pytest.raises(DocumentParseError) as exc_info:
        parse_document(path)

    assert "service_catalog/" in exc_info.value.message


def test_filename_must_be_a_slug(tmp_path: Path) -> None:
    path = write(tmp_path, DocumentType.SERVICE, "Mobil Sube.md", SERVICE_DOC)

    with pytest.raises(DocumentParseError, match="küçük harf"):
        parse_document(path)


# --- Successful parsing ------------------------------------------------------


def test_service_document_is_parsed(tmp_path: Path) -> None:
    path = write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)

    document = parse_document(path)

    assert isinstance(document.frontmatter, ServiceFrontmatter)
    assert document.slug == "msube-web"
    assert document.doc_type is DocumentType.SERVICE
    assert document.frontmatter.updated == date(2026, 9, 30)
    assert document.frontmatter.confidence is Confidence.HIGH
    assert document.frontmatter.observability.correlation_field == "traceId"
    assert document.body.startswith("# Mobil Şube Web")


def test_aliases_are_lowercased_and_deduplicated(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        DocumentType.GLOSSARY,
        "takma-adlar.md",
        """
        ---
        type: glossary
        title: "Sözlük"
        aliases: ["MSUBE", "msube", " Mobil Şube "]
        updated: 2026-09-30
        ---

        Gövde.
        """,
    )

    document = parse_document(path)

    assert document.frontmatter.aliases == ["msube", "mobil şube"]


def test_search_aliases_include_the_title(tmp_path: Path) -> None:
    path = write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)

    document = parse_document(path)

    assert "mobil şube web" in document.search_aliases
    assert "msube" in document.search_aliases


def test_deployment_lookup_by_environment(tmp_path: Path) -> None:
    path = write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)

    frontmatter = parse_document(path).frontmatter
    assert isinstance(frontmatter, ServiceFrontmatter)

    deployment = frontmatter.deployment_for("DMZ-PREPROD")
    assert deployment is not None
    assert deployment.namespace == "dmz-mobile-prep"
    assert frontmatter.deployment_for("prod") is None


def test_content_hash_changes_with_content(tmp_path: Path) -> None:
    first = write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)
    original = parse_document(first).content_hash

    changed = parse_document(first, text=first.read_text(encoding="utf-8") + "\nEk satır.\n")

    assert changed.content_hash != original


# --- Environment validation (ADR-08) -----------------------------------------


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValueError, match="tanımlı bir ortam değil"):
        normalise_environment("staging")


def test_environment_is_normalised() -> None:
    assert normalise_environment("  DMZ-PreProd ") == "dmz-preprod"


def test_deployment_rejects_unknown_environment() -> None:
    with pytest.raises(ValueError, match="Tanımlı ortamlar"):
        Deployment(environment="uat")


# --- Directory loading -------------------------------------------------------


def test_load_directory_collects_errors_instead_of_raising(tmp_path: Path) -> None:
    write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)
    write(
        tmp_path,
        DocumentType.GLOSSARY,
        "bozuk.md",
        """
        ---
        type: glossary
        updated: 2026-09-30
        ---

        Gövde.
        """,
    )

    result = load_directory(tmp_path)

    assert not result.ok
    assert len(result.documents) == 1
    assert len(result.errors) == 1
    assert "bozuk.md" in result.errors[0].format(root=tmp_path)


def test_duplicate_slugs_are_reported(tmp_path: Path) -> None:
    write(tmp_path, DocumentType.SERVICE, "msube-web.md", SERVICE_DOC)
    write(
        tmp_path,
        DocumentType.CASE,
        "msube-web.md",
        """
        ---
        type: case
        title: "Vaka"
        updated: 2026-09-30
        symptom: "Belirti"
        root_cause: "Kök neden"
        resolution: "Çözüm"
        ---

        Gövde.
        """,
    )

    result = load_directory(tmp_path)

    assert not result.ok
    assert "zaten kullanılıyor" in result.errors[0].message


def test_imported_directory_is_skipped(tmp_path: Path) -> None:
    imported = tmp_path / "imported"
    imported.mkdir()
    (imported / "ham.md").write_text("frontmatter yok", encoding="utf-8")

    result = load_directory(tmp_path)

    assert result.ok, "imported/ klasörü doğrulanmamalı"


def test_missing_root_is_reported(tmp_path: Path) -> None:
    result = load_directory(tmp_path / "yok")

    assert not result.ok
    assert "bulunamadı" in result.errors[0].message


# --- The repository's own knowledge base -------------------------------------


def test_shipped_knowledge_base_is_valid() -> None:
    result = load_directory(KNOWLEDGE_ROOT)

    assert result.ok, "\n".join(e.format(root=KNOWLEDGE_ROOT) for e in result.errors)
    assert len(result.documents) >= 5


def test_shipped_knowledge_base_covers_every_document_type() -> None:
    result = load_directory(KNOWLEDGE_ROOT)

    present = {document.doc_type for document in result.documents}
    assert present == set(DocumentType), "her doküman tipinden en az bir örnek olmalı"


def test_shipped_case_document_carries_detection_signals() -> None:
    result = load_directory(KNOWLEDGE_ROOT)

    cases = [d for d in result.documents if d.doc_type is DocumentType.CASE]
    frontmatter = cases[0].frontmatter
    assert isinstance(frontmatter, CaseFrontmatter)
    assert frontmatter.detection_signals, "vaka eşleştirmesi bu alana dayanır"
