from pathlib import Path

import pytest

from orchestrator.config import Settings
from orchestrator.runtime.container import Container
from orchestrator.supply_chain import (
    apply_procurement_revision,
    build_replenishment_approval_args,
    load_archive_csvs,
    query_supplier_offers,
)
from orchestrator.supply_chain.tools import RequestReplenishmentApprovalArgs
from tests.test_graph import decide, get, start


def revise(container, run_id: str, **fields: object) -> None:
    repo = container.repo
    approval = repo.pending_approval_for_run(run_id)
    assert approval is not None
    revised = apply_procurement_revision(
        approval.args,
        selected_plan_id=fields.get("selected_plan_id"),  # type: ignore[arg-type]
        other_plan_text=fields.get("other_plan_text"),  # type: ignore[arg-type]
    )
    validated = RequestReplenishmentApprovalArgs.model_validate(revised).model_dump(mode="json")
    payload = dict(approval.payload or {})
    payload["args"] = validated
    assert repo.update_pending_approval_args(approval.id, validated, payload=payload)


def _supply_chain_db(tmp_path: Path) -> Path:
    db = tmp_path / "supply_chain.db"
    archive = Path(__file__).resolve().parents[1] / "archive"
    load_archive_csvs(archive, db)
    return db


def test_query_supplier_offers_hyd08(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    result = query_supplier_offers("HYD-08", db_path=db)
    assert result["offer_count"] == 3
    by_name = {row["supplier_name"]: row for row in result["offers"]}
    assert by_name["SUP-01"]["qty_available"] == 5000
    assert by_name["SUP-02"]["qty_available"] == 200
    assert by_name["SUP-03"]["qty_available"] == 0


def test_build_replenishment_approval_args(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    args = build_replenishment_approval_args("HYD-08", "WH-1", 200, db_path=db)
    assert args["qty_needed"] == 200
    assert args["recommended_option_id"] == "SUP-01"
    assert len(args["options"]) == 2
    option_ids = {o["option_id"] for o in args["options"]}
    assert option_ids == {"SUP-01", "SUP-02"}
    assert len(args["excluded_suppliers"]) == 1
    assert args["excluded_suppliers"][0]["supplier_name"] == "SUP-03"
    assert len(args["offers"]) == 3
    assert args["recommended_plan"]["summary"].startswith("Purchase 200")
    assert args["coverage_status"] == "full"
    assert len(args["dataset_lines"]) >= 4
    assert "HYD-08" in args["dataset_lines"][0]
    assert len(args["analysis_lines"]) >= 2
    assert len(args["recommended_reasons"]) == 3
    assert len(args["alternatives"]) <= 3


def test_replenishment_procurement_flow(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    settings = Settings(
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
        chroma_collection="test_replenishment",
        llm_provider="mock",
        redis_url=None,
        long_term_memory_enabled=False,
        supply_chain_db_path=str(db),
    )
    container = Container(settings, synchronous_runs=True)
    task = (
        "Part HYD-08 at warehouse WH-1 is below reorder point. "
        "Replenish 200 units for leadership approval."
    )
    run_id = start(container, task)
    run = get(container, run_id)
    assert run.status == "awaiting_approval"
    approval = container.repo.pending_approval_for_run(run_id)
    assert approval is not None
    assert approval.kind == "procurement_choice"
    assert approval.tool_name == "request_replenishment_approval"
    assert len(approval.args["options"]) == 2
    assert approval.args["recommended_option_id"] == "SUP-01"
    assert approval.args["recommended_plan"]["plan_id"] == "rec-SUP-01"
    assert len(approval.args["alternatives"]) >= 1
    decide(container, run_id, {"decision": "approve"})
    run = get(container, run_id)
    assert run.status == "completed"
    audit = container.repo.list_audit(run_id=run_id)
    actions = {a.action for a in audit}
    assert "query_part_inventory" in actions
    assert "query_supplier_offers" in actions
    assert "record_replenishment_choice" in actions
    answer = run.final_answer or ""
    assert "SUP-01" in answer


def test_apply_procurement_revision_resolves_alt_option_suffix(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    args = build_replenishment_approval_args("HYD-08", "WH-1", 200, db_path=db)
    opt = next(o for o in args["options"] if o["option_id"] == "SUP-02")
    opt["option_id"] = "OPT-2"
    args["alternatives"] = []
    revised = apply_procurement_revision(args, selected_plan_id="alt-OPT-2")
    assert revised["recommended_option_id"] == "OPT-2"
    assert revised["recommended_plan"]["plan_id"] == "rec-OPT-2"


def test_apply_procurement_revision_alt_split_without_payload_alternative(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    args = build_replenishment_approval_args("HYD-08", "WH-1", 200, db_path=db)
    args["alternatives"] = [
        a for a in args["alternatives"] if str(a.get("plan_id")) != "alt-split"
    ]
    revised = apply_procurement_revision(args, selected_plan_id="alt-split")
    assert revised["recommended_plan"]["plan_id"] == "rec-split"
    assert "Split" in str(revised["recommended_plan"]["title"])


def test_apply_procurement_revision_selects_alternative(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    args = build_replenishment_approval_args("HYD-08", "WH-1", 200, db_path=db)
    alt_id = next(a["plan_id"] for a in args["alternatives"] if a["plan_id"] == "alt-SUP-02")
    revised = apply_procurement_revision(args, selected_plan_id=alt_id)
    assert revised["revision_count"] == 1
    assert revised["recommended_plan"]["plan_id"] == "rec-SUP-02"
    assert revised["recommended_option_id"] == "SUP-02"
    assert any(a["plan_id"] == "alt-SUP-01" for a in revised["alternatives"])


def test_replenishment_revise_then_approve_sup02(tmp_path: Path) -> None:
    db = _supply_chain_db(tmp_path)
    settings = Settings(
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
        chroma_collection="test_replenishment_revise",
        llm_provider="mock",
        redis_url=None,
        long_term_memory_enabled=False,
        supply_chain_db_path=str(db),
    )
    container = Container(settings, synchronous_runs=True)
    task = (
        "Part HYD-08 at warehouse WH-1 is below reorder point. "
        "Replenish 200 units for leadership approval."
    )
    run_id = start(container, task)
    revise(container, run_id, selected_plan_id="alt-SUP-02")
    approval = container.repo.pending_approval_for_run(run_id)
    assert approval is not None
    assert approval.args["recommended_option_id"] == "SUP-02"
    decide(container, run_id, {"decision": "approve"})
    run = get(container, run_id)
    assert run.status == "completed"
    answer = run.final_answer or ""
    assert "SUP-02" in answer
