import sqlite3
from pathlib import Path

from orchestrator.supply_chain import load_archive_csvs


def test_load_archive_csvs(tmp_path: Path) -> None:
    repo_archive = Path(__file__).resolve().parents[1] / "archive"
    db_path = tmp_path / "supply_chain.db"
    counts = load_archive_csvs(repo_archive, db_path)
    assert counts["warehouse"] == 4
    assert counts["product"] == 40
    assert counts["supplier_offer"] == 393
    assert sum(counts.values()) == 45310
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT supplier_name, product_code, qty_available
            FROM supplier_offer
            WHERE product_code = 'HYD-08'
            ORDER BY supplier_name
            """
        ).fetchall()
    assert rows == [
        ("SUP-01", "HYD-08", 5000),
        ("SUP-02", "HYD-08", 200),
        ("SUP-03", "HYD-08", 0),
    ]
    with sqlite3.connect(db_path) as conn:
        supplier_count = conn.execute(
            "SELECT COUNT(DISTINCT supplier_id) FROM supplier_offer"
        ).fetchone()[0]
        product_count = conn.execute(
            "SELECT COUNT(DISTINCT product_code) FROM supplier_offer"
        ).fetchone()[0]
        zero_rows = conn.execute(
            "SELECT COUNT(*) FROM supplier_offer WHERE qty_available = 0"
        ).fetchone()[0]
    assert supplier_count == 20
    assert product_count == 40
    assert zero_rows >= 30
