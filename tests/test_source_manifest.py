"""Controlled PDF source-manifest tests."""

import hashlib
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.manifest import SourceManifest


def manifest_payload(file: str, content: bytes, **overrides) -> dict:
    payload = {
        "source_id": "sop-dna-qa",
        "file": file,
        "title": "Quy trình kiểm soát chất lượng ADN",
        "authority": "Đơn vị giám định ADN",
        "version": "1.0",
        "effective_date": "2026-01-01",
        "reviewed_at": "2026-08-12",
        "reviewer": "reviewer-01",
        "approver": "approver-01",
        "approval_status": "approved",
        "access_class": "internal",
        "sha256": hashlib.sha256(content).hexdigest(),
        "supersedes": None,
        "max_chunks": 100,
    }
    payload.update(overrides)
    return payload


def write_manifest(directory: Path, payload: dict, name: str = "source") -> Path:
    path = directory / f"{name}.manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_rejects_unknown_fields_and_same_reviewer_approver() -> None:
    content = b"pdf"
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(
            manifest_payload("source.pdf", content, unexpected=True)
        )
    with pytest.raises(ValidationError, match="reviewer and approver"):
        SourceManifest.model_validate(
            manifest_payload("source.pdf", content, reviewer="same", approver="same")
        )


def test_manifest_rejects_non_pdf_paths_future_review_and_restricted_access() -> None:
    content = b"pdf"
    with pytest.raises(ValidationError, match="one PDF filename"):
        SourceManifest.model_validate(manifest_payload("../source.pdf", content))
    with pytest.raises(ValidationError, match="future"):
        SourceManifest.model_validate(
            manifest_payload(
                "source.pdf",
                content,
                reviewed_at=date.today()
                .replace(year=date.today().year + 1)
                .isoformat(),
            )
        )
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(
            manifest_payload("source.pdf", content, access_class="restricted")
        )


def test_manifest_verifies_exact_file_hash(tmp_path: Path) -> None:
    content = b"approved pdf bytes"
    (tmp_path / "source.pdf").write_bytes(content)
    manifest = SourceManifest.model_validate(manifest_payload("source.pdf", content))
    assert manifest.verify_file(tmp_path).name == "source.pdf"

    (tmp_path / "source.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        manifest.verify_file(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["orphan.pdf", "orphan.PDF"])
async def test_directory_rejects_unmanifested_pdf(
    tmp_path: Path, filename: str
) -> None:
    (tmp_path / filename).write_bytes(b"pdf")
    indexer = KnowledgeIndexer(MagicMock())
    with pytest.raises(ValueError, match="requires one source manifest"):
        await indexer.index_directory(tmp_path)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_directory_rejects_reserved_source_id(tmp_path: Path) -> None:
    content = b"pdf"
    (tmp_path / "source.pdf").write_bytes(content)
    write_manifest(
        tmp_path,
        manifest_payload("source.pdf", content, source_id="knowledge_base.tsv"),
    )
    with pytest.raises(ValueError, match="Reserved source_id"):
        await KnowledgeIndexer(MagicMock()).index_directory(tmp_path)


@pytest.mark.asyncio
async def test_directory_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    for name in ("a", "b"):
        content = name.encode()
        (tmp_path / f"{name}.pdf").write_bytes(content)
        write_manifest(
            tmp_path,
            manifest_payload(f"{name}.pdf", content),
            name,
        )
    with pytest.raises(ValueError, match="Duplicate source_id"):
        await KnowledgeIndexer(MagicMock()).index_directory(tmp_path)


@pytest.mark.asyncio
async def test_approved_manifest_indexes_auditable_metadata(tmp_path: Path) -> None:
    content = b"approved pdf"
    (tmp_path / "source.pdf").write_bytes(content)
    write_manifest(tmp_path, manifest_payload("source.pdf", content))
    database = MagicMock()
    indexer = KnowledgeIndexer(database)
    with patch.object(
        KnowledgeIndexer,
        "_read_pdf_chunks",
        return_value=(
            ["Controlled content"],
            [
                {
                    "source": "sop-dna-qa",
                    "source_id": "sop-dna-qa",
                    "source_title": "Quy trình kiểm soát chất lượng ADN",
                    "source_authority": "Đơn vị giám định ADN",
                    "source_version": "1.0",
                    "source_page_or_section": "1",
                    "effective_date": "2026-01-01",
                    "reviewed_at": "2026-08-12",
                    "reviewer": "reviewer-01",
                    "approver": "approver-01",
                    "approval_status": "approved",
                    "access_class": "internal",
                    "content_hash": hashlib.sha256(content).hexdigest(),
                    "supersedes": "",
                    "page": 1,
                    "chunk": 1,
                }
            ],
        ),
    ):
        assert await indexer.index_directory(tmp_path) == 1

    source, ids, texts, metadata = database.replace_source.call_args.args
    assert source == "sop-dna-qa"
    assert ids == ["pdf:sop-dna-qa:chunk:1"]
    assert texts == ["Controlled content"]
    assert metadata[0]["approver"] == "approver-01"
    assert metadata[0]["content_hash"] == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["withdrawn", "superseded"])
async def test_inactive_manifest_removes_source_without_requiring_pdf(
    tmp_path: Path, status: str
) -> None:
    payload = manifest_payload(
        "removed.pdf",
        b"old",
        approval_status=status,
    )
    write_manifest(tmp_path, payload)
    database = MagicMock()

    assert await KnowledgeIndexer(database).index_directory(tmp_path) == 0
    database.replace_source.assert_called_once_with("sop-dna-qa", [], [], [])


@pytest.mark.asyncio
async def test_directory_validates_all_sources_before_database_writes(
    tmp_path: Path,
) -> None:
    first = b"first"
    second = b"second"
    for name, content in (("first", first), ("second", second)):
        (tmp_path / f"{name}.pdf").write_bytes(content)
        payload = manifest_payload(
            f"{name}.pdf",
            content,
            source_id=f"sop-{name}",
        )
        if name == "second":
            payload["sha256"] = "0" * 64
        write_manifest(tmp_path, payload, name)

    database = MagicMock()
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        await KnowledgeIndexer(database).index_directory(tmp_path)
    database.replace_source.assert_not_called()


@pytest.mark.asyncio
async def test_approved_pdf_requires_extractable_text(tmp_path: Path) -> None:
    content = b"empty pdf"
    (tmp_path / "source.pdf").write_bytes(content)
    write_manifest(tmp_path, manifest_payload("source.pdf", content))
    database = MagicMock()
    with patch.object(KnowledgeIndexer, "_read_pdf_chunks", return_value=([], [])):
        with pytest.raises(ValueError, match="no extractable text"):
            await KnowledgeIndexer(database).index_directory(tmp_path)
    database.replace_source.assert_not_called()
