from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
DOCS_ROOT = ROOT / "docs" / "src"


def _source_manuals() -> set[Path]:
    return {
        path.relative_to(SOURCE_ROOT).with_suffix(".md")
        for path in SOURCE_ROOT.rglob("*.py")
    }


def _documented_manuals() -> set[Path]:
    return {path.relative_to(DOCS_ROOT) for path in DOCS_ROOT.rglob("*.md")}


def test_source_documentation_mirrors_python_source() -> None:
    expected = _source_manuals()
    actual = _documented_manuals()

    missing = sorted(str(path) for path in expected - actual)
    orphaned = sorted(str(path) for path in actual - expected)

    assert not missing, f"Missing docs/src manuals: {missing}"
    assert not orphaned, f"Orphaned docs/src manuals: {orphaned}"
