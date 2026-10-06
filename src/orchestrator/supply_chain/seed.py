from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Literal

from orchestrator.supply_chain.supplier_offers import seed_supplier_offers

SqliteType = Literal["INTEGER", "REAL", "TEXT"]

TABLES: dict[str, list[tuple[str, SqliteType]]] = {
    "carrier": [
        ("carrier_id", "INTEGER"),
        ("carrier_name", "TEXT"),
        ("mode", "TEXT"),
        ("cost_per_kg", "REAL"),
        ("avg_transit_days", "INTEGER"),
        ("co2_kg_per_km", "REAL"),
        ("reliability_score", "REAL"),
    ],
    "customer": [
        ("customer_id", "INTEGER"),
        ("customer_name", "TEXT"),
        ("industry_segment", "TEXT"),
        ("region", "TEXT"),
        ("priority_tier", "TEXT"),
        ("credit_limit", "REAL"),
        ("contract_type", "TEXT"),
        ("since_year", "INTEGER"),
    ],
    "warehouse": [
        ("warehouse_id", "INTEGER"),
        ("warehouse_name", "TEXT"),
        ("region", "TEXT"),
        ("capacity_units", "INTEGER"),
        ("operating_cost_monthly", "INTEGER"),
        ("automation_level", "TEXT"),
    ],
    "product": [
        ("product_id", "INTEGER"),
        ("product_code", "TEXT"),
        ("category", "TEXT"),
        ("unit_weight_kg", "REAL"),
        ("standard_cost", "REAL"),
        ("list_price", "REAL"),
        ("abc_class", "TEXT"),
        ("hazardous", "INTEGER"),
        ("shelf_life_days", "INTEGER"),
    ],
    "supplier": [
        ("supplier_id", "INTEGER"),
        ("supplier_name", "TEXT"),
        ("country", "TEXT"),
        ("tier", "TEXT"),
        ("lead_time_days", "INTEGER"),
        ("quality_rating", "REAL"),
        ("onboard_date", "TEXT"),
        ("payment_terms_days", "INTEGER"),
        ("min_order_value", "REAL"),
        ("is_single_source", "INTEGER"),
    ],
    "purchase_order": [
        ("po_id", "INTEGER"),
        ("order_date", "TEXT"),
        ("supplier_id", "INTEGER"),
        ("promised_date", "TEXT"),
        ("actual_delivery_date", "TEXT"),
        ("status", "TEXT"),
        ("expedited", "INTEGER"),
    ],
    "purchase_order_line": [
        ("po_line_id", "INTEGER"),
        ("po_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("qty_ordered", "INTEGER"),
        ("qty_received", "INTEGER"),
        ("qty_rejected", "INTEGER"),
        ("unit_cost", "REAL"),
    ],
    "inventory_snapshot": [
        ("snapshot_id", "INTEGER"),
        ("snapshot_date", "TEXT"),
        ("warehouse_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("units_on_hand", "INTEGER"),
        ("reorder_point", "INTEGER"),
        ("units_reserved", "INTEGER"),
        ("units_in_transit", "INTEGER"),
    ],
    "production_run": [
        ("production_id", "INTEGER"),
        ("run_date", "TEXT"),
        ("plant_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("units_produced", "INTEGER"),
        ("defect_count", "INTEGER"),
        ("downtime_min", "INTEGER"),
        ("labor_hours", "REAL"),
        ("shift", "TEXT"),
    ],
    "shipment": [
        ("shipment_id", "INTEGER"),
        ("ship_date", "TEXT"),
        ("warehouse_id", "INTEGER"),
        ("customer_id", "INTEGER"),
        ("carrier_id", "INTEGER"),
        ("delivery_date", "TEXT"),
        ("on_time_flag", "INTEGER"),
        ("damaged_flag", "INTEGER"),
    ],
    "shipment_line": [
        ("ship_line_id", "INTEGER"),
        ("shipment_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("qty_shipped", "INTEGER"),
        ("revenue", "REAL"),
        ("freight_cost", "REAL"),
    ],
}

DEFAULT_ARCHIVE_DIR = Path("archive")
DEFAULT_DB_PATH = Path("data/supply_chain.db")


def _coerce(value: str, col_type: SqliteType) -> int | float | str | None:
    raw = value.strip()
    if raw == "":
        return None
    if col_type == "TEXT":
        return raw
    if col_type == "INTEGER":
        return int(raw)
    return float(raw)


def _create_table(conn: sqlite3.Connection, table: str) -> None:
    columns = TABLES[table]
    parts = [f"{name} {col_type}" for name, col_type in columns]
    pk = columns[0][0]
    ddl = f"CREATE TABLE {table} ({', '.join(parts)}, PRIMARY KEY ({pk}))"
    conn.execute(ddl)


def _import_table(conn: sqlite3.Connection, archive_dir: Path, table: str) -> int:
    csv_path = archive_dir / f"{table}.csv"
    if not csv_path.is_file():
        msg = f"missing CSV for table {table}: {csv_path}"
        raise FileNotFoundError(msg)

    columns = TABLES[table]
    col_names = [name for name, _ in columns]
    placeholders = ", ".join("?" for _ in col_names)
    insert_sql = f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})"

    rows: list[tuple[int | float | str | None, ...]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != col_names:
            msg = (
                f"{csv_path.name}: expected columns {col_names}, got {reader.fieldnames}"
            )
            raise ValueError(msg)
        for line in reader:
            rows.append(
                tuple(_coerce(line[name], col_type) for name, col_type in columns)
            )

    conn.executemany(insert_sql, rows)
    return len(rows)


def load_archive_csvs(
    archive_dir: Path | str = DEFAULT_ARCHIVE_DIR,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, int]:
    archive = Path(archive_dir)
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    if db_file.is_file():
        db_file.unlink()

    counts: dict[str, int] = {}
    with sqlite3.connect(db_file) as conn:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            _create_table(conn, table)
            counts[table] = _import_table(conn, archive, table)
        counts["supplier_offer"] = seed_supplier_offers(conn)
        conn.commit()

    return counts
