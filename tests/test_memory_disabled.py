from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from orchestrator.config import Settings
from orchestrator.runtime.container import Container
from orchestrator.tools.base import ToolContext


@pytest.fixture
def disabled_container(tmp_path: Path) -> Container:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        log_level="WARNING",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        checkpointer="sqlite",
        checkpoint_sqlite_path=str(tmp_path / "checkpoints.db"),
        event_bus="memory",
        run_executor="inline",
        vector_store="chroma",
        chroma_mode="ephemeral",
        chroma_collection=f"test_{uuid.uuid4().hex[:12]}",
        llm_provider="mock",
        long_term_memory_enabled=False,
    )
    c = Container(settings, synchronous_runs=True)
    yield c
    c.close()


def test_recall_and_save_return_empty_when_disabled(disabled_container: Container) -> None:
    ctx = ToolContext(
        user_id="u1",
        run_id="r1",
        thread_id="t1",
        memory=disabled_container.memory,
        settings=disabled_container.settings,
        agent="researcher",
    )
    from orchestrator.tools.builtin import build_default_registry

    reg = build_default_registry()
    save = reg.get("save_memory")
    recall = reg.get("recall_memory")
    assert save is not None and recall is not None
    assert save.invoke(save.validate({"content": "User's name is Dana"}), ctx)["status"] == "disabled"
    assert recall.invoke(recall.validate({"query": "name"}), ctx)["memories"] == []


def test_run_emits_empty_memory_recalled(disabled_container: Container) -> None:
    repo = disabled_container.repo
    tid = repo.create_thread("u1", "inventory").id
    run = repo.create_run(
        thread_id=tid,
        user_id="u1",
        task=(
            "My name is Dana. What is the latest inventory for part HYD-08 at warehouse WH-1?"
        ),
        llm_provider="mock",
        model="m",
    )
    disabled_container.runner.execute(run.id)
    recalled = next(e for e in repo.list_events(run.id) if e.type == "memory_recalled")
    assert recalled.data["memories"] == []
    assert disabled_container.memory.list_for_user("u1") == []
