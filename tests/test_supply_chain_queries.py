from pathlib import Path

import pytest

from orchestrator.supply_chain import (
    load_archive_csvs,
    query_customer_trade_summary,
    query_part_inventory,
)
from orchestrator.tools.base import ToolError


def test_query_part_inventory_on_repo_db() -> None:
    db = Path(__file__).resolve().parents[1] / "data" / "supply_chain.db"
    if not db.is_file():
        archive = Path(__file__).resolve().parents[1] / "archive"
        load_archive_csvs(archive, db)
    result = query_part_inventory("HYD-08", "WH-1", db_path=db)
    assert result["snapshot_date"] == "2025-12-29"
    assert result["units_on_hand"] == 0
    assert result["reorder_point"] == 1019
    assert result["units_reserved"] == 0
    assert result["units_in_transit"] == 422
    assert result["below_reorder_point"] is True


def test_query_customer_trade_summary_on_repo_db() -> None:
    db = Path(__file__).resolve().parents[1] / "data" / "supply_chain.db"
    if not db.is_file():
        archive = Path(__file__).resolve().parents[1] / "archive"
        load_archive_csvs(archive, db)
    result = query_customer_trade_summary("CUST-005", db_path=db)
    assert result["period_start"] == "2025-10-01"
    assert result["period_end"] == "2026-01-01"
    assert result["shipment_count"] == 27
    assert result["total_qty_shipped"] == 13886
    assert result["total_revenue"] == 2575429.62


def test_query_part_inventory_missing(tmp_path: Path) -> None:
    archive = Path(__file__).resolve().parents[1] / "archive"
    db = tmp_path / "supply_chain.db"
    load_archive_csvs(archive, db)
    with pytest.raises(ToolError, match="No inventory snapshot"):
        query_part_inventory("NO-SUCH", "WH-1", db_path=db)
