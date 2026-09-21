"""Build the approved forensic knowledge index."""

import csv
import hashlib
from pathlib import Path

from haystack import Document
from haystack.document_stores.types import DuplicatePolicy

from chatbot_app.retrieval import (
    build_document_embedder,
    build_document_store,
)


KNOWLEDGE_FILE = Path("/data/knowledge_base.tsv")

REQUIRED_COLUMNS = {
    "no",
    "term",
    "description",
    "keywords",
    "aliases",
    "topic",
    "figure_id",
    "source_id",
    "source_title",
    "source_authority",
    "source_version",
    "source_page_or_section",
    "effective_date",
    "reviewed_at",
    "reviewer",
    "approval_status",
}


def stable_document_id(row: dict[str, str]) -> str:
    source = "\x1f".join(
        (
            row["source_id"].strip(),
            row["no"].strip(),
            row["term"].strip(),
        )
    )

    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def load_documents() -> tuple[list[Document], int]:
    if not KNOWLEDGE_FILE.is_file():
        raise RuntimeError(f"Knowledge file not found: {KNOWLEDGE_FILE}")

    documents: list[Document] = []
    skipped_unapproved = 0

    with KNOWLEDGE_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")

        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns

        if missing:
            raise RuntimeError(
                f"Knowledge file is missing columns: {sorted(missing)}"
            )

        for row in reader:
            approval_status = row["approval_status"].strip().lower()

            if approval_status != "approved":
                skipped_unapproved += 1
                continue

            term = row["term"].strip()
            description = row["description"].strip()

            if not term or not description:
                raise RuntimeError(
                    f"Approved row {row['no']!r} has empty term or description"
                )

            meta = {
                key: row[key].strip()
                for key in REQUIRED_COLUMNS
                if key not in {"description"}
            }

            documents.append(
                Document(
                    id=stable_document_id(row),
                    content=f"{term}\n\n{description}",
                    meta=meta,
                )
            )

    if not documents:
        raise RuntimeError("No approved knowledge documents were found")

    return documents, skipped_unapproved


def main() -> None:
    documents, skipped_unapproved = load_documents()

    print(f"approved_documents={len(documents)}")
    print(f"skipped_unapproved={skipped_unapproved}")

    document_store = build_document_store(recreate_table=True)

    embedder = build_document_embedder()
    embedder.warm_up()

    embedded_documents = embedder.run(
        documents=documents,
    )["documents"]

    written = document_store.write_documents(
        embedded_documents,
        policy=DuplicatePolicy.OVERWRITE,
    )

    stored = document_store.count_documents()

    print(f"written_documents={written}")
    print(f"stored_documents={stored}")

    if stored != len(documents):
        raise RuntimeError(
            f"Index count mismatch: expected={len(documents)}, stored={stored}"
        )


if __name__ == "__main__":
    main()
