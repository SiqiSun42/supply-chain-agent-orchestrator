type ProcurementPlanLine = {
  supplier_name: string;
  qty: number;
  unit_price?: number;
  lead_days?: number;
};

export type ProcurementPlan = {
  plan_id: string;
  title: string;
  summary: string;
  lines?: ProcurementPlanLine[];
  estimated_total_cost?: number;
};

type ReplenishmentOption = {
  option_id: string;
  supplier_name: string;
  product_code?: string;
  qty_available: number;
  unit_price: number;
  lead_days: number;
  qty_to_order: number;
};

type SupplierOfferRow = {
  supplier_name: string;
  qty_available: number;
  unit_price: number;
  lead_days: number;
};

type ExcludedSupplier = {
  supplier_name: string;
  qty_available: number;
  reason?: string;
};

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((x): x is string => typeof x === "string") : [];
}

function replenishmentOptions(args: Record<string, unknown>): ReplenishmentOption[] {
  const raw = args.options;
  return Array.isArray(raw) ? (raw as ReplenishmentOption[]) : [];
}

function planFromOption(
  opt: ReplenishmentOption,
  productCode: string,
  prefix: string,
): ProcurementPlan {
  const qty = opt.qty_to_order;
  const name = opt.supplier_name;
  return {
    plan_id: `${prefix}-${opt.option_id}`,
    title: `Purchase from ${name}`,
    summary: `Purchase ${qty} units of ${productCode} from ${name}.`,
    lines: [
      {
        supplier_name: name,
        qty,
        unit_price: opt.unit_price,
        lead_days: opt.lead_days,
      },
    ],
    estimated_total_cost: Math.round(opt.unit_price * qty * 100) / 100,
  };
}

function buildDatasetLines(args: Record<string, unknown>): string[] {
  const existing = stringList(args.dataset_lines);
  if (existing.length > 0) return existing;

  const lines: string[] = [];
  const productCode = String(args.product_code ?? "HYD-08");
  const warehouse = String(args.warehouse_name ?? "WH-1");
  const qtyNeeded = Number(args.qty_needed ?? args.qty_requested ?? 0);

  const inv = args.inventory;
  if (inv && typeof inv === "object" && !Array.isArray(inv)) {
    const i = inv as Record<string, unknown>;
    lines.push(
      `Part ${productCode} @ ${warehouse} (snapshot ${String(i.snapshot_date ?? "—")}): ` +
        `on_hand=${String(i.units_on_hand)}, reorder_point=${String(i.reorder_point)}, ` +
        `reserved=${String(i.units_reserved)}, in_transit=${String(i.units_in_transit)}, ` +
        `below_reorder_point=${String(i.below_reorder_point)}.`,
    );
  }
  if (qtyNeeded > 0) {
    lines.push(`Replenishment request quantity: ${qtyNeeded} units.`);
  }

  const offers = args.offers;
  if (Array.isArray(offers)) {
    for (const row of offers as SupplierOfferRow[]) {
      lines.push(
        `Supplier ${row.supplier_name}: qty_available=${row.qty_available}, ` +
          `unit_price=${row.unit_price}, lead_days=${row.lead_days}.`,
      );
    }
  }

  const excluded = args.excluded_suppliers;
  if (Array.isArray(excluded)) {
    for (const row of excluded as ExcludedSupplier[]) {
      lines.push(
        `Supplier ${row.supplier_name}: qty_available=${row.qty_available}` +
          (qtyNeeded > 0 ? ` (cannot fulfill ${qtyNeeded} in one line).` : "."),
      );
    }
  }

  return lines;
}

function buildAnalysisLines(args: Record<string, unknown>): string[] {
  const existing = stringList(args.analysis_lines);
  if (existing.length > 0) return existing;

  const warehouse = String(args.warehouse_name ?? "WH-1");
  const productCode = String(args.product_code ?? "HYD-08");
  const qtyNeeded = Number(args.qty_needed ?? 200);
  const options = replenishmentOptions(args);
  const excluded = Array.isArray(args.excluded_suppliers) ? args.excluded_suppliers.length : 0;

  return [
    `${warehouse} is below the reorder point for ${productCode}; stock must be restored before the next production window.`,
    `${options.length} supplier(s) can cover the full ${qtyNeeded}-unit requirement in a single PO line; ${excluded} supplier(s) are short at this quantity.`,
    "Leadership approval is required before issuing a purchase order for this hydraulics replenishment.",
  ];
}

function buildRecommendedReasons(
  args: Record<string, unknown>,
  recommended: ProcurementPlan | null,
  recOpt: ReplenishmentOption | null,
): string[] {
  const existing = stringList(args.recommended_reasons);
  if (existing.length > 0) return existing;
  if (!recOpt) return [];

  const qtyNeeded = recOpt.qty_to_order;
  const total = recommended?.estimated_total_cost ?? recOpt.unit_price * qtyNeeded;
  return [
    `${recOpt.supplier_name} has ${recOpt.qty_available} units available, comfortably above the ${qtyNeeded}-unit requirement.`,
    `Single-supplier PO at $${recOpt.unit_price.toFixed(2)}/unit (${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} total) simplifies receiving and AP.`,
    `${recOpt.lead_days}-day lead time is acceptable for a standard replenishment without expediting.`,
  ];
}

function buildAlternatives(
  args: Record<string, unknown>,
  recommendedId: string,
  productCode: string,
): ProcurementPlan[] {
  const fromPayload = Array.isArray(args.alternatives) ? (args.alternatives as ProcurementPlan[]) : [];
  if (fromPayload.length > 0) return fromPayload.slice(0, 3);

  const options = replenishmentOptions(args);
  const alts: ProcurementPlan[] = [];
  for (const opt of options) {
    if (opt.option_id === recommendedId) continue;
    alts.push(planFromOption(opt, productCode, "alt"));
  }
  if (options.length >= 2 && alts.length < 3) {
    const names = options.slice(0, 2).map((o) => o.supplier_name).sort();
    const qtyNeeded = Number(args.qty_needed ?? options[0]?.qty_to_order ?? 200);
    const half = Math.floor(qtyNeeded / 2);
    const rest = qtyNeeded - half;
    alts.push({
      plan_id: "alt-split",
      title: `Split between ${names[0]} and ${names[1]}`,
      summary: `Purchase ${half} units from ${names[0]} and ${rest} from ${names[1]} (total ${qtyNeeded}).`,
      lines: [
        { supplier_name: names[0], qty: half },
        { supplier_name: names[1], qty: rest },
      ],
    });
  }
  return alts.slice(0, 3);
}

export type ProcurementApprovalView = {
  datasetLines: string[];
  analysisLines: string[];
  recommended: ProcurementPlan | null;
  recommendedReasons: string[];
  alternatives: ProcurementPlan[];
  headerLine: string;
};

export function procurementApprovalView(args: Record<string, unknown>): ProcurementApprovalView {
  const productCode = String(args.product_code ?? "HYD-08");
  const warehouse = String(args.warehouse_name ?? "WH-1");
  const qtyNeeded = Number(args.qty_needed ?? 0);
  const recommendedId = String(args.recommended_option_id ?? "SUP-01");

  const recRaw = args.recommended_plan;
  let recommended =
    recRaw && typeof recRaw === "object" && !Array.isArray(recRaw) ? (recRaw as ProcurementPlan) : null;

  const options = replenishmentOptions(args);
  const recOpt = options.find((o) => o.option_id === recommendedId) ?? options[0] ?? null;

  if (!recommended && recOpt) {
    recommended = planFromOption(recOpt, productCode, "rec");
  }

  const datasetLines = buildDatasetLines(args);
  const analysisLines = buildAnalysisLines(args);
  const recommendedReasons = buildRecommendedReasons(args, recommended, recOpt);
  const alternatives = buildAlternatives(args, recommendedId, productCode);

  const headerLine =
    qtyNeeded > 0
      ? `Leadership approval: replenish ${qtyNeeded} units of ${productCode} at ${warehouse}.`
      : `Leadership approval for ${productCode} at ${warehouse}.`;

  return {
    datasetLines,
    analysisLines,
    recommended,
    recommendedReasons,
    alternatives,
    headerLine,
  };
}
