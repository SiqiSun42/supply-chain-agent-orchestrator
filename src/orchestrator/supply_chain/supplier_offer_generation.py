from __future__ import annotations

import random
import sqlite3
from collections import defaultdict

from orchestrator.supply_chain.supplier_offers import SupplierOfferRow

CURRENT_OFFER_AS_OF = "current"

TOP_SUPPLIERS_PER_PRODUCT = 10

HYD_08_SUPPLIER_IDS = (1, 2, 3)

QTY_PIN_BY_SUPPLIER_PRODUCT: dict[tuple[str, str], int] = {
    ("SUP-01", "HYD-08"): 5000,
    ("SUP-02", "HYD-08"): 200,
    ("SUP-03", "HYD-08"): 0,
}

_GENERATION_SEED = 42


def _historical_qty_and_cost(
    conn: sqlite3.Connection,
) -> tuple[dict[tuple[int, str], int], dict[tuple[int, str], float]]:
    rows = conn.execute(
        """
        SELECT
            po.supplier_id,
            p.product_code,
            SUM(pol.qty_ordered) AS total_qty,
            AVG(pol.unit_cost) AS avg_unit_cost
        FROM purchase_order po
        JOIN purchase_order_line pol ON pol.po_id = po.po_id
        JOIN product p ON p.product_id = pol.product_id
        GROUP BY po.supplier_id, p.product_code
        """
    ).fetchall()
    qty_map: dict[tuple[int, str], int] = {}
    cost_map: dict[tuple[int, str], float] = {}
    for supplier_id, product_code, total_qty, avg_cost in rows:
        sid = int(supplier_id)
        code = str(product_code)
        qty_map[(sid, code)] = int(total_qty)
        cost_map[(sid, code)] = float(avg_cost) if avg_cost is not None else 0.0
    return qty_map, cost_map


def _catalog_pairs(
    qty_map: dict[tuple[int, str], int],
) -> set[tuple[int, str]]:
    by_product: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for (sid, code), total in qty_map.items():
        by_product[code].append((sid, total))
    pairs: set[tuple[int, str]] = set()
    for code, ranked in by_product.items():
        if code == "HYD-08":
            for sid in HYD_08_SUPPLIER_IDS:
                if (sid, code) in qty_map:
                    pairs.add((sid, code))
            continue
        top = sorted(ranked, key=lambda item: -item[1])[:TOP_SUPPLIERS_PER_PRODUCT]
        for sid, _ in top:
            pairs.add((sid, code))
    return pairs


def _qty_available(
    rng: random.Random,
    supplier_name: str,
    product_code: str,
    historical_qty: int,
) -> int:
    pinned = QTY_PIN_BY_SUPPLIER_PRODUCT.get((supplier_name, product_code))
    if pinned is not None:
        return pinned
    roll = rng.random()
    if roll < 0.14:
        return 0
    if roll < 0.38:
        return rng.randint(1, 350)
    scale = max(100, min(12000, int(historical_qty * rng.uniform(0.0015, 0.045))))
    jitter = rng.randint(-scale // 8, scale // 8)
    return max(0, scale + jitter)


def _unit_price(
    rng: random.Random,
    product_standard_cost: float,
    historical_avg_cost: float,
) -> float:
    base = historical_avg_cost if historical_avg_cost > 0 else product_standard_cost
    if base <= 0:
        base = 10.0
    factor = rng.uniform(0.92, 1.08)
    return round(base * factor, 2)


def _lead_days(rng: random.Random, supplier_lead_time: int) -> int:
    base = max(1, int(supplier_lead_time))
    return max(1, base + rng.randint(-2, 4))


def generate_supplier_offers_from_history(conn: sqlite3.Connection) -> list[SupplierOfferRow]:
    qty_map, cost_map = _historical_qty_and_cost(conn)
    pairs = _catalog_pairs(qty_map)
    suppliers = {
        int(row[0]): (str(row[1]), int(row[2]))
        for row in conn.execute(
            "SELECT supplier_id, supplier_name, lead_time_days FROM supplier"
        ).fetchall()
    }
    standard_cost = {
        str(row[0]): float(row[1])
        for row in conn.execute(
            "SELECT product_code, standard_cost FROM product"
        ).fetchall()
    }
    rng = random.Random(_GENERATION_SEED)
    offers: list[SupplierOfferRow] = []
    for sid, product_code in sorted(pairs):
        supplier_row = suppliers.get(sid)
        if supplier_row is None:
            continue
        supplier_name, lead_time = supplier_row
        historical_qty = qty_map.get((sid, product_code), 0)
        qty = _qty_available(rng, supplier_name, product_code, historical_qty)
        avg_cost = cost_map.get((sid, product_code), 0.0)
        std = standard_cost.get(product_code, 0.0)
        price = _unit_price(rng, std, avg_cost)
        lead = _lead_days(rng, lead_time)
        offers.append(
            SupplierOfferRow(
                supplier_id=sid,
                supplier_name=supplier_name,
                product_code=product_code,
                qty_available=qty,
                unit_price=price,
                lead_days=lead,
                as_of_date=CURRENT_OFFER_AS_OF,
            )
        )
    return offers
