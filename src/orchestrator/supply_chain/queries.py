from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from orchestrator.supply_chain.constants import (
    AS_OF_DATE,
    DEFAULT_DB_PATH,
    DEFAULT_TRADE_LOOKBACK_MONTHS,
    trade_period_end,
    trade_period_start,
)
from orchestrator.tools.base import ToolError


def query_part_inventory(
    product_code: str,
    warehouse_name: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    as_of_date: date = AS_OF_DATE,
) -> dict[str, object]:
    path = Path(db_path)
    if not path.is_file():
        msg = f"Supply chain database not found: {path.resolve()}"
        raise ToolError(msg)

    as_of = as_of_date.isoformat()
    sql = """
        SELECT
            w.warehouse_name,
            p.product_code,
            i.snapshot_date,
            i.units_on_hand,
            i.reorder_point,
            i.units_reserved,
            i.units_in_transit
        FROM inventory_snapshot i
        JOIN warehouse w ON w.warehouse_id = i.warehouse_id
        JOIN product p ON p.product_id = i.product_id
        WHERE p.product_code = ?
          AND w.warehouse_name = ?
          AND i.snapshot_date = (
              SELECT MAX(i2.snapshot_date)
              FROM inventory_snapshot i2
              JOIN warehouse w2 ON w2.warehouse_id = i2.warehouse_id
              JOIN product p2 ON p2.product_id = i2.product_id
              WHERE p2.product_code = ?
                AND w2.warehouse_name = ?
                AND i2.snapshot_date <= ?
          )
    """
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            sql,
            (product_code, warehouse_name, product_code, warehouse_name, as_of),
        ).fetchone()

    if row is None:
        msg = (
            f"No inventory snapshot for part {product_code} at {warehouse_name} "
            f"on or before {as_of}."
        )
        raise ToolError(msg)

    on_hand = int(row["units_on_hand"])
    reorder = int(row["reorder_point"])
    return {
        "warehouse_name": row["warehouse_name"],
        "product_code": row["product_code"],
        "snapshot_date": row["snapshot_date"],
        "units_on_hand": on_hand,
        "reorder_point": reorder,
        "units_reserved": int(row["units_reserved"]),
        "units_in_transit": int(row["units_in_transit"]),
        "below_reorder_point": on_hand < reorder,
        "as_of_date": as_of,
    }


def query_customer_trade_summary(
    customer_name: str,
    *,
    months: int = DEFAULT_TRADE_LOOKBACK_MONTHS,
    db_path: Path | str = DEFAULT_DB_PATH,
    as_of_date: date = AS_OF_DATE,
) -> dict[str, object]:
    path = Path(db_path)
    if not path.is_file():
        msg = f"Supply chain database not found: {path.resolve()}"
        raise ToolError(msg)

    period_start = trade_period_start(months, as_of_date).isoformat()
    period_end = trade_period_end(as_of_date).isoformat()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute(
            "SELECT 1 FROM customer WHERE customer_name = ? LIMIT 1",
            (customer_name,),
        ).fetchone()
        if exists is None:
            msg = f"Customer {customer_name} was not found."
            raise ToolError(msg)
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT sh.shipment_id) AS shipment_count,
                COALESCE(SUM(sl.qty_shipped), 0) AS total_qty_shipped,
                COALESCE(SUM(sl.revenue), 0) AS total_revenue
            FROM customer c
            JOIN shipment sh ON sh.customer_id = c.customer_id
            JOIN shipment_line sl ON sl.shipment_id = sh.shipment_id
            WHERE c.customer_name = ?
              AND sh.ship_date >= ?
              AND sh.ship_date <= ?
            """,
            (customer_name, period_start, period_end),
        ).fetchone()
        assert row is not None

    return {
        "customer_name": customer_name,
        "period_start": period_start,
        "period_end": period_end,
        "months": months,
        "shipment_count": int(row["shipment_count"]),
        "total_qty_shipped": int(row["total_qty_shipped"]),
        "total_revenue": round(float(row["total_revenue"]), 2),
        "as_of_date": as_of_date.isoformat(),
    }


def query_supplier_offers(
    product_code: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, object]:
    path = Path(db_path)
    if not path.is_file():
        msg = f"Supply chain database not found: {path.resolve()}"
        raise ToolError(msg)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        product = conn.execute(
            "SELECT 1 FROM product WHERE product_code = ? LIMIT 1",
            (product_code,),
        ).fetchone()
        if product is None:
            msg = f"Product {product_code} was not found."
            raise ToolError(msg)
        rows = conn.execute(
            """
            SELECT
                supplier_id,
                supplier_name,
                product_code,
                qty_available,
                unit_price,
                lead_days,
                as_of_date
            FROM supplier_offer
            WHERE product_code = ?
            ORDER BY supplier_name
            """,
            (product_code,),
        ).fetchall()

    offers = [
        {
            "supplier_id": int(row["supplier_id"]),
            "supplier_name": row["supplier_name"],
            "product_code": row["product_code"],
            "qty_available": int(row["qty_available"]),
            "unit_price": float(row["unit_price"]),
            "lead_days": int(row["lead_days"]),
            "as_of_date": row["as_of_date"],
        }
        for row in rows
    ]
    return {
        "product_code": product_code,
        "offer_count": len(offers),
        "offers": offers,
    }
