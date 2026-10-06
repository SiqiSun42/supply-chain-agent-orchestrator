from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.supply_chain.constants import DEFAULT_DB_PATH
from orchestrator.supply_chain.queries import query_part_inventory, query_supplier_offers


def plan_from_option(opt: dict[str, Any], product_code: str, *, prefix: str) -> dict[str, Any]:
    sid = str(opt["option_id"])
    qty = int(opt["qty_to_order"])
    name = str(opt["supplier_name"])
    return {
        "plan_id": f"{prefix}-{sid}",
        "title": f"Purchase from {name}",
        "summary": f"Purchase {qty} units of {product_code} from {name}.",
        "lines": [
            {
                "supplier_name": name,
                "qty": qty,
                "unit_price": opt["unit_price"],
                "lead_days": opt["lead_days"],
            }
        ],
        "estimated_total_cost": round(float(opt["unit_price"]) * qty, 2),
    }


def resolve_alternative_plan(args: dict[str, Any], selected_plan_id: str) -> dict[str, Any]:
    alts = list(args.get("alternatives") or [])
    for alt in alts:
        if str(alt.get("plan_id")) == selected_plan_id:
            return alt
    if selected_plan_id == "alt-split":
        qty_needed = int(args.get("qty_needed") or 0)
        options = list(args.get("options") or [])
        split = split_alternative_plan(options, qty_needed)
        if split is not None:
            return split
    product_code = str(args.get("product_code") or "HYD-08")
    options = list(args.get("options") or [])
    suffix = selected_plan_id.removeprefix("alt-").removeprefix("rec-")
    for opt in options:
        oid = str(opt.get("option_id", ""))
        sname = str(opt.get("supplier_name", ""))
        if selected_plan_id in (f"alt-{oid}", f"rec-{oid}") or suffix in (oid, sname):
            return plan_from_option(opt, product_code, prefix="alt")
    for alt in alts:
        pid = str(alt.get("plan_id", ""))
        if suffix and suffix in pid:
            return alt
    raise ValueError(f"Unknown alternative plan_id: {selected_plan_id}")


def option_id_for_selected_plan(
    args: dict[str, Any], selected_plan_id: str, picked: dict[str, Any]
) -> str:
    if selected_plan_id == "alt-split" or str(picked.get("plan_id", "")).endswith("split"):
        return ""
    suffix = selected_plan_id.removeprefix("alt-").removeprefix("rec-")
    options = list(args.get("options") or [])
    for opt in options:
        oid = str(opt.get("option_id", ""))
        sname = str(opt.get("supplier_name", ""))
        if suffix in (oid, sname):
            return oid
    lines = picked.get("lines") or []
    if isinstance(lines, list) and len(lines) == 1 and isinstance(lines[0], dict):
        sname = str(lines[0].get("supplier_name") or "")
        for opt in options:
            if str(opt.get("supplier_name")) == sname:
                return str(opt["option_id"])
    if suffix.startswith("SUP-"):
        return suffix
    return ""


def build_replenishment_approval_args(
    product_code: str,
    warehouse_name: str,
    qty_needed: int,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    inventory = query_part_inventory(
        product_code,
        warehouse_name,
        db_path=db_path,
    )
    offers_payload = query_supplier_offers(product_code, db_path=db_path)
    offers = list(offers_payload["offers"])

    excluded_suppliers: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for offer in offers:
        qty = int(offer["qty_available"])
        name = str(offer["supplier_name"])
        if qty < qty_needed:
            excluded_suppliers.append(
                {
                    "supplier_id": offer["supplier_id"],
                    "supplier_name": name,
                    "qty_available": qty,
                    "reason": f"Available quantity {qty} is below required {qty_needed}.",
                }
            )
            continue
        options.append(
            {
                "option_id": name,
                "supplier_id": offer["supplier_id"],
                "supplier_name": name,
                "product_code": product_code,
                "qty_available": qty,
                "unit_price": offer["unit_price"],
                "lead_days": offer["lead_days"],
                "qty_to_order": qty_needed,
            }
        )

    recommended_option_id = "SUP-01"
    if not any(o["option_id"] == recommended_option_id for o in options):
        if options:
            recommended_option_id = max(options, key=lambda o: int(o["qty_available"]))[
                "option_id"
            ]
        else:
            recommended_option_id = ""

    recommended_plan: dict[str, Any] | None = None
    alternatives: list[dict[str, Any]] = []
    for opt in options:
        if opt["option_id"] == recommended_option_id:
            recommended_plan = plan_from_option(opt, product_code, prefix="rec")
        else:
            alternatives.append(plan_from_option(opt, product_code, prefix="alt"))

    if recommended_plan is None and options:
        pick = max(options, key=lambda o: int(o["qty_available"]))
        recommended_option_id = str(pick["option_id"])
        recommended_plan = plan_from_option(pick, product_code, prefix="rec")
        alternatives = [
            plan_from_option(o, product_code, prefix="alt")
            for o in options
            if o["option_id"] != recommended_option_id
        ]

    if len(options) >= 2 and len(alternatives) < 3:
        split = split_alternative_plan(options, qty_needed)
        if split is not None:
            alternatives.append(split)

    alternatives = alternatives[:3]

    dataset_lines: list[str] = [
        (
            f"Part {product_code} @ {warehouse_name} (snapshot {inventory.get('snapshot_date')}): "
            f"on_hand={inventory.get('units_on_hand')}, reorder_point={inventory.get('reorder_point')}, "
            f"reserved={inventory.get('units_reserved')}, in_transit={inventory.get('units_in_transit')}, "
            f"below_reorder_point={inventory.get('below_reorder_point')}."
        ),
        f"Replenishment request quantity: {qty_needed} units.",
    ]
    for offer in offers:
        dataset_lines.append(
            f"Supplier {offer['supplier_name']}: qty_available={offer['qty_available']}, "
            f"unit_price={offer['unit_price']}, lead_days={offer['lead_days']}."
        )
    for row in excluded_suppliers:
        dataset_lines.append(
            f"Supplier {row['supplier_name']}: qty_available={row['qty_available']} "
            f"(cannot fulfill {qty_needed} in one line)."
        )

    analysis_lines = [
        (
            f"{warehouse_name} is below the reorder point for {product_code}; "
            "stock must be restored before the next production window."
        ),
        (
            f"{len(options)} supplier(s) can cover the full {qty_needed}-unit requirement in a single PO line; "
            f"{len(excluded_suppliers)} supplier(s) are short at this quantity."
        ),
        "Leadership approval is required before issuing a purchase order for this hydraulics replenishment.",
    ]

    recommended_reasons: list[str] = []
    rec_opt = next((o for o in options if o["option_id"] == recommended_option_id), None)
    if rec_opt and recommended_plan:
        rec_name = str(rec_opt["supplier_name"])
        recommended_reasons = [
            (
                f"{rec_name} has {rec_opt['qty_available']} units available, "
                f"comfortably above the {qty_needed}-unit requirement."
            ),
            (
                f"Single-supplier PO at ${float(rec_opt['unit_price']):.2f}/unit "
                f"({recommended_plan['estimated_total_cost']:,.2f} total) simplifies receiving and AP."
            ),
            (
                f"{int(rec_opt['lead_days'])}-day lead time is acceptable for a standard replenishment "
                "without expediting."
            ),
        ]

    summary = (
        f"Replenish {qty_needed} units of {product_code} for {warehouse_name}. "
        f"{len(options)} supplier option(s) meet the quantity requirement; "
        f"{len(excluded_suppliers)} excluded."
    )
    reason = (
        f"Leadership approval required to replenish {qty_needed} units of {product_code} "
        f"at {warehouse_name}."
    )
    if recommended_option_id:
        reason += f" Recommended supplier: {recommended_option_id}."

    coverage_status = "full" if options else "none"

    return {
        "product_code": product_code,
        "warehouse_name": warehouse_name,
        "qty_needed": qty_needed,
        "coverage_status": coverage_status,
        "inventory": inventory,
        "offers": offers,
        "excluded_suppliers": excluded_suppliers,
        "options": options,
        "recommended_option_id": recommended_option_id,
        "dataset_lines": dataset_lines,
        "analysis_lines": analysis_lines,
        "recommended_plan": recommended_plan,
        "recommended_reasons": recommended_reasons,
        "alternatives": alternatives,
        "summary": summary,
        "reason": reason,
        "revision_count": 0,
    }


def split_alternative_plan(
    options: list[dict[str, Any]], qty_needed: int
) -> dict[str, Any] | None:
    if len(options) < 2 or qty_needed < 1:
        return None
    names = sorted(str(o["supplier_name"]) for o in options[:2])
    half = qty_needed // 2
    rest = qty_needed - half
    return {
        "plan_id": "alt-split",
        "title": f"Split between {names[0]} and {names[1]}",
        "summary": (
            f"Purchase {half} units from {names[0]} and {rest} from {names[1]} "
            f"(total {qty_needed})."
        ),
        "lines": [
            {"supplier_name": names[0], "qty": half},
            {"supplier_name": names[1], "qty": rest},
        ],
    }


def _reasons_for_supplier_option(opt: dict[str, Any], estimated_total: float) -> list[str]:
    qty = int(opt["qty_to_order"])
    name = str(opt["supplier_name"])
    return [
        (
            f"{name} has {opt['qty_available']} units available, "
            f"comfortably above the {qty}-unit requirement."
        ),
        (
            f"Single-supplier PO at ${float(opt['unit_price']):.2f}/unit "
            f"({estimated_total:,.2f} total) simplifies receiving and AP."
        ),
        (
            f"{int(opt['lead_days'])}-day lead time is acceptable for a standard replenishment "
            "without expediting."
        ),
    ]


def apply_procurement_revision(
    args: dict[str, Any],
    *,
    selected_plan_id: str | None = None,
    other_plan_text: str | None = None,
) -> dict[str, Any]:
    text = (other_plan_text or "").strip()
    if text:
        new_rec: dict[str, Any] = {
            "plan_id": "rec-custom",
            "title": "Custom plan",
            "summary": text,
            "lines": [],
            "source": "other",
        }
        new_option_id = ""
        picked_id: str | None = None
    elif selected_plan_id:
        picked_id = selected_plan_id
        picked = resolve_alternative_plan(args, selected_plan_id)
        suffix = selected_plan_id.removeprefix("alt-").removeprefix("rec-")
        new_plan_id = f"rec-{suffix}" if suffix else "rec-chosen"
        if selected_plan_id == "alt-split":
            new_plan_id = "rec-split"
        new_rec = {k: v for k, v in picked.items() if k != "source"}
        new_rec["plan_id"] = new_plan_id
        new_option_id = option_id_for_selected_plan(args, selected_plan_id, picked)
        if not new_option_id and suffix.startswith("SUP-"):
            new_option_id = suffix
    else:
        raise ValueError("selected_plan_id or other_plan_text is required")

    old_rec = args.get("recommended_plan")
    old_id = str(old_rec.get("plan_id")) if isinstance(old_rec, dict) else ""
    new_alts = list(args.get("alternatives") or [])
    if picked_id:
        new_alts = [a for a in new_alts if str(a.get("plan_id")) != picked_id]
    if isinstance(old_rec, dict) and old_id and old_id != str(new_rec.get("plan_id")):
        alt_id = old_id.replace("rec-", "alt-", 1) if old_id.startswith("rec-") else f"alt-{old_id}"
        if not any(str(a.get("plan_id")) == alt_id for a in new_alts):
            old_alt = {k: v for k, v in old_rec.items() if k not in {"source", "estimated_total_cost"}}
            old_alt["plan_id"] = alt_id
            new_alts.insert(0, old_alt)
    new_alts = new_alts[:3]

    options = list(args.get("options") or [])
    rec_opt = (
        next((o for o in options if str(o.get("option_id")) == new_option_id), None)
        if new_option_id
        else None
    )
    estimated = new_rec.get("estimated_total_cost")
    if new_rec.get("source") == "other":
        reasons = [
            "Leadership specified this custom procurement path for replenishment.",
            "Custom plans are recorded for audit; execution follows leadership wording.",
        ]
    elif str(new_rec.get("plan_id")) == "rec-split" or "Split" in str(new_rec.get("title", "")):
        reasons = [
            "Split PO reduces dependence on a single supplier for the full quantity.",
            "Both suppliers meet minimum line quantity for this replenishment.",
            "Receiving may schedule two inbound deliveries instead of one consolidated shipment.",
        ]
    elif rec_opt is not None:
        total = float(estimated) if estimated is not None else float(rec_opt["unit_price"]) * int(
            rec_opt["qty_to_order"]
        )
        reasons = _reasons_for_supplier_option(rec_opt, total)
    else:
        reasons = [f"Leadership selected: {new_rec.get('summary', '')}"]

    updated = dict(args)
    updated["recommended_plan"] = new_rec
    updated["recommended_option_id"] = new_option_id
    updated["alternatives"] = new_alts
    updated["recommended_reasons"] = reasons
    updated["revision_count"] = int(args.get("revision_count") or 0) + 1
    return updated
