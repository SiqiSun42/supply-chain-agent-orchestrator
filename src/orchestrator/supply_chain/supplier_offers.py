from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SqliteType = Literal["INTEGER", "REAL", "TEXT"]

SUPPLIER_OFFER_COLUMNS: list[tuple[str, SqliteType]] = [
    ("supplier_id", "INTEGER"),
    ("supplier_name", "TEXT"),
    ("product_code", "TEXT"),
    ("qty_available", "INTEGER"),
    ("unit_price", "REAL"),
    ("lead_days", "INTEGER"),
    ("as_of_date", "TEXT"),
]

SUPPLIER_OFFER_TABLE = "supplier_offer"


@dataclass(frozen=True, slots=True)
class SupplierOfferRow:
    supplier_id: int
    supplier_name: str
    product_code: str
    qty_available: int
    unit_price: float
    lead_days: int
    as_of_date: str

    def as_tuple(self) -> tuple[int, str, str, int, float, int, str]:
        return (
            self.supplier_id,
            self.supplier_name,
            self.product_code,
            self.qty_available,
            self.unit_price,
            self.lead_days,
            self.as_of_date,
        )


def create_supplier_offer_table(conn: sqlite3.Connection) -> None:
    parts = [f"{name} {col_type}" for name, col_type in SUPPLIER_OFFER_COLUMNS]
    ddl = (
        f"CREATE TABLE {SUPPLIER_OFFER_TABLE} ({', '.join(parts)}, "
        "PRIMARY KEY (supplier_id, product_code))"
    )
    conn.execute(f"DROP TABLE IF EXISTS {SUPPLIER_OFFER_TABLE}")
    conn.execute(ddl)


def _validate_supplier(conn: sqlite3.Connection, supplier_id: int, supplier_name: str) -> None:
    row = conn.execute(
        "SELECT supplier_name FROM supplier WHERE supplier_id = ?",
        (supplier_id,),
    ).fetchone()
    if row is None:
        msg = f"supplier_id {supplier_id} not in supplier table"
        raise ValueError(msg)
    if row[0] != supplier_name:
        msg = f"supplier_name mismatch for id {supplier_id}: expected {row[0]!r}, got {supplier_name!r}"
        raise ValueError(msg)


def _validate_product(conn: sqlite3.Connection, product_code: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM product WHERE product_code = ?",
        (product_code,),
    ).fetchone()
    if row is None:
        msg = f"product_code {product_code!r} not in product table"
        raise ValueError(msg)


def seed_supplier_offers(
    conn: sqlite3.Connection,
    offers: tuple[SupplierOfferRow, ...] | list[SupplierOfferRow] | None = None,
) -> int:
    from orchestrator.supply_chain.supplier_offer_generation import (
        generate_supplier_offers_from_history,
    )

    create_supplier_offer_table(conn)
    if offers is None:
        rows = generate_supplier_offers_from_history(conn)
    else:
        rows = list(offers)
    col_names = [name for name, _ in SUPPLIER_OFFER_COLUMNS]
    placeholders = ", ".join("?" for _ in col_names)
    insert_sql = (
        f"INSERT INTO {SUPPLIER_OFFER_TABLE} ({', '.join(col_names)}) VALUES ({placeholders})"
    )
    for offer in rows:
        _validate_supplier(conn, offer.supplier_id, offer.supplier_name)
        _validate_product(conn, offer.product_code)
    conn.executemany(insert_sql, [o.as_tuple() for o in rows])
    return len(rows)


def seed_supplier_offers_file(
    db_path: Path | str,
    offers: tuple[SupplierOfferRow, ...] | list[SupplierOfferRow] | None = None,
) -> int:
    path = Path(db_path)
    if not path.is_file():
        msg = f"Supply chain database not found: {path.resolve()}"
        raise FileNotFoundError(msg)
    with sqlite3.connect(path) as conn:
        n = seed_supplier_offers(conn, offers)
        conn.commit()
    return n
