import type { ProcurementApprovalView } from "../lib/procurementApprovalView";

export function ProcurementProposalBody({
  procurement,
  showConfirmation,
}: {
  procurement: ProcurementApprovalView;
  showConfirmation: boolean;
}) {
  return (
    <div className="space-y-4 text-sm text-slate-700">
      <div>
        <p className="mb-2 font-medium text-slate-800">From dataset</p>
        <ul className="list-disc space-y-1 pl-5 text-slate-600">
          {procurement.datasetLines.map((line, index) => (
            <li key={`${index}-${line.slice(0, 48)}`}>{line}</li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-2 font-medium text-slate-800">Analysis</p>
        <ul className="list-disc space-y-1 pl-5 leading-relaxed text-slate-600">
          {procurement.analysisLines.map((line, index) => (
            <li key={`${index}-${line.slice(0, 48)}`}>{line}</li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-2 font-medium text-slate-800">Recommended plan</p>
        <div className="rounded-lg bg-indigo-50/80 p-3 ring-1 ring-inset ring-indigo-200">
          <p className="font-medium text-slate-900">{procurement.recommended?.title ?? "—"}</p>
          <p className="mt-1 text-slate-700">{procurement.recommended?.summary ?? "—"}</p>
          {procurement.recommended?.lines && procurement.recommended.lines.length > 0 && (
            <ul className="mt-2 space-y-1 font-mono text-xs text-slate-600">
              {procurement.recommended.lines.map((line) => (
                <li key={`${line.supplier_name}-${line.qty}`}>
                  {line.supplier_name}: qty={line.qty}
                  {line.unit_price != null ? `, unit_price=${line.unit_price}` : ""}
                  {line.lead_days != null ? `, lead_days=${line.lead_days}` : ""}
                </li>
              ))}
            </ul>
          )}
          {procurement.recommended?.estimated_total_cost != null && (
            <p className="mt-2 text-slate-600">
              Estimated total: $
              {procurement.recommended.estimated_total_cost.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </p>
          )}
        </div>
      </div>
      <div>
        <p className="mb-2 font-medium text-slate-800">Reasons</p>
        <ul className="list-disc space-y-1 pl-5 text-slate-600">
          {procurement.recommendedReasons.map((line, index) => (
            <li key={`${index}-${line.slice(0, 48)}`}>{line}</li>
          ))}
        </ul>
      </div>
      {procurement.alternatives.length > 0 && (
        <div>
          <p className="mb-2 font-medium text-slate-800">Alternative options</p>
          <ul className="list-disc space-y-2 pl-5 text-slate-600">
            {procurement.alternatives.map((alt) => (
              <li key={alt.plan_id}>{alt.summary}</li>
            ))}
          </ul>
        </div>
      )}
      {showConfirmation && (
        <p className="text-slate-600">
          Do you accept the recommended plan? If yes, a standard procurement summary will be generated after
          approval.
        </p>
      )}
    </div>
  );
}
