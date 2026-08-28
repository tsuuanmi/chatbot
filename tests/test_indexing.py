"""RAG document and knowledge-base indexing tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.figures.indexer import FigureDescriptionIndexer
from src.base.components.vector_databases.base import SearchHit
from src.figures.models import FigureDescription
from src.figures.store import FigureDescriptionStore
from src.index_documents import index_documents
from src.knowledge.indexer import KnowledgeIndexer


def test_figure_store_uses_exact_stable_ids_and_removes_stale_records() -> None:
    vector_database = MagicMock()
    vector_database.list_ids.return_value = ["figure:bar1", "figure:removed"]
    store = FigureDescriptionStore(vector_database)
    description = FigureDescription("bar1", "hash", "Description")

    store.save([description], ["bar1"])

    vector_database.delete.assert_called_once_with(["figure:removed"])
    ids, texts, metadata = vector_database.upsert.call_args.args
    assert ids == ["figure:bar1"]
    assert texts == ["Description"]
    assert metadata[0]["content_hash"] == "hash"


def test_figure_store_loads_exact_record() -> None:
    vector_database = MagicMock()
    vector_database.get_by_id.return_value = SearchHit(
        "figure:heatmap1",
        "Stored heatmap",
        {"figure_id": "heatmap1", "content_hash": "hash"},
        0.0,
    )
    store = FigureDescriptionStore(vector_database)

    assert store.get("heatmap1") == FigureDescription(
        "heatmap1", "hash", "Stored heatmap"
    )
    vector_database.get_by_id.assert_called_once_with("figure:heatmap1")


def test_chunk_text_is_bounded_and_overlapping() -> None:
    text = " ".join(f"word-{index}" for index in range(500))
    chunks = list(KnowledgeIndexer._chunk_text(text, chunk_size=120, overlap=20))
    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert chunks[0][-20:].split()[-1] in chunks[1]


def test_chunk_text_ignores_empty_content() -> None:
    assert list(KnowledgeIndexer._chunk_text("  \n\t ")) == []


@pytest.mark.asyncio
async def test_knowledge_base_indexing_replaces_valid_entries(tmp_path: Path) -> None:
    path = tmp_path / "knowledge_base.tsv"
    path.write_text(
        "no\tterm\tdescription\tkeywords\ttopic\tfigure_id\tsource_id\t"
        "source_title\tsource_authority\tsource_version\t"
        "source_page_or_section\tapproval_status\n"
        "1\tSTR là gì?\tSTR là trình tự lặp ngắn.\tSTR, ADN\tfaq\tpie3\t"
        "source\ttitle\tauthority\t1\tsection\tapproved\n"
        "2\tDraft question\tDraft answer\tDNA\tdraft\t\tdraft-source\t"
        "Draft title\tDraft authority\t1\tsection\tdraft\n",
        encoding="utf-8",
    )
    vector_database = MagicMock()
    vector_database.lexical_search.return_value = []
    indexer = KnowledgeIndexer(vector_database)

    count = await indexer.index_knowledge_base(path)

    assert count == 1
    vector_database.replace_source.assert_called_once()
    source, ids, texts, metadata = vector_database.replace_source.call_args.args
    assert source == "knowledge_base.tsv"
    assert ids == ["knowledge:1"]
    assert "Câu hỏi: STR là gì?" in texts[0]
    assert metadata[0]["source"] == "knowledge_base.tsv"


@pytest.mark.asyncio
async def test_project_indexer_includes_tsv_knowledge_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "knowledge_base.tsv").write_text(
        "no\tterm\tdescription\tapproval_status\n"
        "1\tDNA là gì?\tDNA mang thông tin di truyền.\tapproved\n",
        encoding="utf-8",
    )
    vector_database = MagicMock()
    container = MagicMock(vector_database=vector_database)
    monkeypatch.setattr("src.index_documents.setup_container", lambda: container)

    assert await index_documents(tmp_path, index_figures=False) == 1
    vector_database.replace_source.assert_called_once()


@pytest.mark.asyncio
async def test_figure_indexer_reuses_unchanged_descriptions(tmp_path: Path) -> None:
    from PIL import Image

    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()
    Image.new("RGB", (8, 8), "red").save(figures_dir / "bar1.png")

    from src.tools.figure_tool import FigureTool

    figure_tool = FigureTool(str(figures_dir))
    asset = figure_tool.load("bar1")
    assert asset is not None
    existing = FigureDescription("bar1", asset.content_hash, "Stored description")
    store = MagicMock()
    store.get.return_value = existing
    generate = MagicMock()
    indexer = FigureDescriptionIndexer(figure_tool, store, generate)

    assert await indexer.index() == 1
    generate.assert_not_called()
    store.save.assert_called_once_with([], ["bar1"])


@pytest.mark.asyncio
async def test_figure_indexer_generates_changed_descriptions(tmp_path: Path) -> None:
    from PIL import Image

    from src.tools.figure_tool import FigureTool

    Image.new("RGB", (8, 8), "blue").save(tmp_path / "heatmap1.png")
    store = MagicMock()
    store.get.return_value = FigureDescription("heatmap1", "old", "Old")
    generate = AsyncMock(return_value="New description")
    indexer = FigureDescriptionIndexer(FigureTool(str(tmp_path)), store, generate)

    assert await indexer.index() == 1
    assert store.save.call_count == 2
    generated, figure_ids = store.save.call_args_list[0].args
    assert figure_ids == ["heatmap1"]
    assert generated[0].figure_id == "heatmap1"
    assert generated[0].description == "New description"
    assert generated[0].content_hash != "old"
    assert store.save.call_args_list[1].args == ([], ["heatmap1"])


@pytest.mark.asyncio
async def test_figure_indexer_retries_storage_without_regenerating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    from src.tools.figure_tool import FigureTool

    Image.new("RGB", (8, 8), "green").save(tmp_path / "tree1.png")
    store = MagicMock()
    store.get.return_value = None
    store.save.side_effect = [RuntimeError("embedding failed"), None, None]
    generate = AsyncMock(return_value="Tree description")
    sleep = AsyncMock()
    monkeypatch.setattr("src.figures.indexer.asyncio.sleep", sleep)
    indexer = FigureDescriptionIndexer(FigureTool(str(tmp_path)), store, generate)

    assert await indexer.index() == 1
    generate.assert_awaited_once()
    assert store.save.call_count == 3
    first_description = store.save.call_args_list[0].args[0][0]
    retried_description = store.save.call_args_list[1].args[0][0]
    assert first_description == retried_description
    sleep.assert_awaited_once_with(5.0)


@pytest.mark.asyncio
async def test_figure_indexer_exhausts_three_storage_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    from src.tools.figure_tool import FigureTool

    Image.new("RGB", (8, 8), "yellow").save(tmp_path / "pie1.png")
    store = MagicMock()
    store.get.return_value = None
    store.save.side_effect = RuntimeError("embedding unavailable")
    generate = AsyncMock(return_value="Pie description")
    sleep = AsyncMock()
    monkeypatch.setattr("src.figures.indexer.asyncio.sleep", sleep)
    indexer = FigureDescriptionIndexer(FigureTool(str(tmp_path)), store, generate)

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await indexer.index()

    generate.assert_awaited_once()
    assert store.save.call_count == 4
    assert sleep.await_count == 3
