from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from orchestrator.supply_chain.constants import DEFAULT_TRADE_LOOKBACK_MONTHS
from orchestrator.supply_chain.queries import (
    query_customer_trade_summary,
    query_part_inventory,
    query_supplier_offers,
)
from orchestrator.tools.base import ToolContext, ToolError


class SubmitReplenishmentApprovalArgs(BaseModel):
    product_code: str = Field(min_length=2, max_length=32)
    warehouse_name: str = Field(min_length=2, max_length=32)
    qty_needed: int = Field(ge=1, le=1_000_000)


def submit_replenishment_for_approval_tool(
    _args: SubmitReplenishmentApprovalArgs, _ctx: ToolContext
) -> dict[str, Any]:
    raise ToolError("Replenishment approval must be confirmed by a human before execution.")


class QueryPartInventoryArgs(BaseModel):
    product_code: str = Field(
        min_length=2,
        max_length=32,
        description=(
            "Part product_code from the user task, hyphenated Meridian code such as HYD-08 "
            "(not an order id)."
        ),
    )
    warehouse_name: str = Field(
        min_length=2,
        max_length=32,
        description="Warehouse name from the user task, such as WH-1.",
    )


def query_part_inventory_tool(args: QueryPartInventoryArgs, ctx: ToolContext) -> dict[str, Any]:
    return query_part_inventory(
        args.product_code.strip().upper(),
        args.warehouse_name.strip().upper(),
        db_path=ctx.settings.supply_chain_db_path,
    )


class QueryCustomerTradeSummaryArgs(BaseModel):
    customer_name: str = Field(
        min_length=2,
        max_length=64,
        description=(
            "Customer identifier from the user task, such as CUST-005 (Meridian customer_name)."
        ),
    )
    months: int = Field(
        default=DEFAULT_TRADE_LOOKBACK_MONTHS,
        ge=1,
        le=24,
        description=(
            "Lookback window in months from the internal as-of date; use 3 when the user asks "
            "for the prior three months unless they give another number."
        ),
    )


def query_customer_trade_summary_tool(
    args: QueryCustomerTradeSummaryArgs, ctx: ToolContext
) -> dict[str, Any]:
    return query_customer_trade_summary(
        args.customer_name.strip().upper(),
        months=args.months,
        db_path=ctx.settings.supply_chain_db_path,
    )


class QuerySupplierOffersArgs(BaseModel):
    product_code: str = Field(
        min_length=2,
        max_length=32,
        description="Product code such as HYD-08.",
    )


def query_supplier_offers_tool(args: QuerySupplierOffersArgs, ctx: ToolContext) -> dict[str, Any]:
    return query_supplier_offers(
        args.product_code,
        db_path=ctx.settings.supply_chain_db_path,
    )


class ReplenishmentOptionArgs(BaseModel):
    option_id: str
    supplier_id: int
    supplier_name: str
    product_code: str
    qty_available: int
    unit_price: float
    lead_days: int
    qty_to_order: int


class ExcludedSupplierArgs(BaseModel):
    supplier_id: int
    supplier_name: str
    qty_available: int
    reason: str


class ProcurementPlanLineArgs(BaseModel):
    supplier_name: str
    qty: int = Field(ge=1)
    unit_price: float | None = None
    lead_days: int | None = None


class ProcurementPlanArgs(BaseModel):
    plan_id: str
    title: str
    summary: str
    lines: list[ProcurementPlanLineArgs] = Field(default_factory=list)
    estimated_total_cost: float | None = None


class RequestReplenishmentApprovalArgs(BaseModel):
    product_code: str
    warehouse_name: str
    qty_needed: int = Field(ge=1)
    inventory: dict[str, Any]
    offers: list[dict[str, Any]]
    excluded_suppliers: list[ExcludedSupplierArgs]
    options: list[ReplenishmentOptionArgs]
    recommended_option_id: str
    summary: str
    reason: str
    coverage_status: str | None = None
    dataset_lines: list[str] = Field(default_factory=list)
    analysis_lines: list[str] = Field(default_factory=list)
    recommended_plan: ProcurementPlanArgs | None = None
    recommended_reasons: list[str] = Field(default_factory=list)
    alternatives: list[ProcurementPlanArgs] = Field(default_factory=list)
    revision_count: int = Field(default=0, ge=0)


def request_replenishment_approval_tool(
    _args: RequestReplenishmentApprovalArgs, _ctx: ToolContext
) -> dict[str, Any]:
    raise ToolError("Replenishment approval must be confirmed by a human before execution.")


class RecordReplenishmentChoiceArgs(BaseModel):
    option_id: str
    supplier_id: int
    supplier_name: str
    product_code: str
    warehouse_name: str
    qty_to_order: int = Field(ge=1)
    unit_price: float
    lead_days: int


def record_replenishment_choice_tool(
    args: RecordReplenishmentChoiceArgs, _ctx: ToolContext
) -> dict[str, Any]:
    return {
        "status": "recorded",
        "option_id": args.option_id,
        "supplier_name": args.supplier_name,
        "product_code": args.product_code,
        "warehouse_name": args.warehouse_name,
        "qty_to_order": args.qty_to_order,
        "unit_price": args.unit_price,
        "lead_days": args.lead_days,
        "message": (
            f"Leadership selected {args.supplier_name} to replenish "
            f"{args.qty_to_order} units of {args.product_code} for {args.warehouse_name}."
        ),
    }
