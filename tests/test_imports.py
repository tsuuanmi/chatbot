"""Architectural import and route sanity tests."""

import importlib

from src.api.app import create_app


def test_authoritative_modules_import() -> None:
    modules = [
        "src.api.app",
        "src.api.auth",
        "src.api.capacity",
        "src.api.v1.chat",
        "src.common.exact_match",
        "src.database.history_service",
        "src.domain.classifier",
        "src.knowledge.indexer",
        "src.knowledge.retriever",
        "src.readiness",
        "src.workflow.graph",
        "src.workflow.nodes",
    ]
    for module in modules:
        assert importlib.import_module(module)


def test_removed_legacy_modules_are_absent() -> None:
    for module in [
        "src.chat_engine",
        "src.api.v1.experts",
        "src.experts.qna.expert",
        "src.llm.generator",
        "src.base.components.memories",
    ]:
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"Legacy module still exists: {module}")


def test_route_set_has_no_expert_switching() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/stream" in paths
    assert "/api/v1/live" in paths
    assert "/api/v1/ready" in paths
    assert not any(path.startswith("/api/v1/rag") for path in paths)
    assert not any(path.startswith("/api/v1/experts") for path in paths)
