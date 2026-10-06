from pathlib import Path

from orchestrator.config import Settings
from orchestrator.memory.store import MemoryStore
from orchestrator.memory.vector import InMemoryVectorIndex
from orchestrator.supply_chain.tools import (
    QueryCustomerTradeSummaryArgs,
    QueryPartInventoryArgs,
    query_customer_trade_summary_tool,
    query_part_inventory_tool,
)
from orchestrator.tools.base import ToolContext


def _ctx(db: Path) -> ToolContext:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        supply_chain_db_path=str(db),
        long_term_memory_enabled=False,
    )
    memory = MemoryStore(InMemoryVectorIndex(), settings, embedder=None)
    return ToolContext(
        settings=settings,
        user_id="u1",
        run_id="r1",
        thread_id="t1",
        memory=memory,
    )


def test_part_inventory_tool_normalizes_codes(tmp_path: Path) -> None:
    from orchestrator.supply_chain import load_archive_csvs

    db = tmp_path / "supply_chain.db"
    archive = Path(__file__).resolve().parents[1] / "archive"
    load_archive_csvs(archive, db)
    args = QueryPartInventoryArgs(product_code="hyd-08", warehouse_name="wh-1")
    result = query_part_inventory_tool(args, _ctx(db))
    assert result["product_code"] == "HYD-08"
    assert result["warehouse_name"] == "WH-1"


def test_customer_trade_tool_normalizes_customer(tmp_path: Path) -> None:
    from orchestrator.supply_chain import load_archive_csvs

    db = tmp_path / "supply_chain.db"
    archive = Path(__file__).resolve().parents[1] / "archive"
    load_archive_csvs(archive, db)
    args = QueryCustomerTradeSummaryArgs(customer_name="cust-005", months=3)
    result = query_customer_trade_summary_tool(args, _ctx(db))
    assert result["customer_name"] == "CUST-005"
    assert result["shipment_count"] == 27
