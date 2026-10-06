from pathlib import Path

from orchestrator.config import Settings
from orchestrator.runtime.container import Container
from orchestrator.supply_chain import (
    apply_po_email_revision,
    check_po_feasibility,
    load_archive_csvs,
)
from tests.test_graph import decide, get, start


def _supply_chain_db(tmp_path: Path) -> Path:
    db = tmp_path / "supply_chain.db"
    archive = Path(__file__).resolve().parents[1] / "archive"
    load_archive_csvs(archive, db)
    return db


def _settings(tmp_path: Path, db: Path, collection: str) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        log_level="WARNING",
        database_url=f"sqlite:///{tmp_path / 'orch.db'}",
        checkpointer="sqlite",
        checkpoint_sqlite_path=str(tmp_path / "checkpoints.db"),
        event_bus="memory",
        run_executor="inline",
        vector_store="chroma",
        chroma_mode="ephemeral",
        chroma_collection=collection,
        llm_provider="mock",
        redis_url=None,
        long_term_memory_enabled=False,
        supply_chain_db_path=str(db),
    )


PO_TASK = (
    "Place a purchase order for 1000 units of HYD-08 from supplier SUP-01 "
    "and send it to procurement for release."
)

PO_INFEASIBLE_TASK = (
    "Place a purchase order for 1000 units of HYD-08 from supplier SUP-02 "
    "and send it to procurement for release."
)


def test_check_po_feasibility(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    ok, _, _ = check_po_feasibility("SUP-01", "HYD-08", 1000, db_path=db)
    assert ok
    ok2, reason, _ = check_po_feasibility("SUP-02", "HYD-08", 1000, db_path=db)
    assert not ok2
    assert "200" in reason


def test_po_dispatch_approve_flow(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    container = Container(_settings(tmp_path, db, "test_po_dispatch"), synchronous_runs=True)
    run_id = start(container, PO_TASK)
    run = get(container, run_id)
    assert run.status == "awaiting_approval"
    approval = container.repo.pending_approval_for_run(run_id)
    assert approval is not None
    assert approval.kind == "tool"
    assert approval.tool_name == "send_email"
    assert approval.args["purpose"] == "purchase_order_dispatch"
    assert approval.args["to"] == "procurement@plant.example.com"
    assert "1000" in approval.args["subject"]
    decide(container, run_id, {"decision": "approve"})
    run = get(container, run_id)
    assert run.status == "completed"
    answer = run.final_answer or ""
    assert "The following content was sent to procurement:" in answer
    assert "procurement@plant.example.com" in answer
    assert "SUP-01" in answer


def test_po_dispatch_infeasible_completes(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    container = Container(_settings(tmp_path, db, "test_po_infeasible"), synchronous_runs=True)
    run_id = start(container, PO_INFEASIBLE_TASK)
    run = get(container, run_id)
    assert run.status == "completed"
    assert container.repo.pending_approval_for_run(run_id) is None
    answer = run.final_answer or ""
    assert "Cannot place order" in answer or "only has" in answer
    assert "No email was drafted" in answer


def test_po_dispatch_revise_then_approve(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    container = Container(_settings(tmp_path, db, "test_po_revise"), synchronous_runs=True)
    run_id = start(container, PO_TASK)
    approval = container.repo.pending_approval_for_run(run_id)
    assert approval is not None
    revised_body = "Custom PO body from leadership review.\nLine two."
    revised = apply_po_email_revision(approval.args, revised_body=revised_body)
    payload = dict(approval.payload or {})
    payload["args"] = revised
    assert container.repo.update_pending_approval_args(approval.id, revised, payload=payload)
    decide(container, run_id, {"decision": "approve"})
    run = get(container, run_id)
    assert run.status == "completed"
    answer = run.final_answer or ""
    assert "Custom PO body from leadership review." in answer
    assert "Line two." in answer
