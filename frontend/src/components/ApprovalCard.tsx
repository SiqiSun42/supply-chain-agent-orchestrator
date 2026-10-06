import clsx from "clsx";
import { Check, ExternalLink, Pencil, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import { timeAgo, titleCase } from "../lib/format";
import { procurementApprovalView } from "../lib/procurementApprovalView";
import type { Approval, DecisionInput } from "../lib/types";
import { ProcurementProposalBody } from "./ProcurementProposalBody";
import { AgentBadge, Badge, Button, Card, JsonBlock } from "./ui";

const RISK_TONE = { low: "green", medium: "amber", high: "red" } as const;

function isPoDispatchEmail(approval: Approval): boolean {
  return (
    approval.kind === "tool" &&
    approval.tool_name === "send_email" &&
    approval.args.purpose === "purchase_order_dispatch"
  );
}

export function ApprovalCard({ approval, onDecided, compact = false }: {
  approval: Approval;
  onDecided?: (approval: Approval) => void;
  compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [argsText, setArgsText] = useState(() => JSON.stringify(approval.args, null, 2));
  const [response, setResponse] = useState(
    approval.kind === "final_review" ? String(approval.args.answer ?? "") : "",
  );
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejectPanel, setRejectPanel] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [otherPlanText, setOtherPlanText] = useState("");
  const pending = approval.status === "pending";
  const [procurementArgs, setProcurementArgs] = useState(approval.args);
  const revisionKey = Number(procurementArgs.revision_count ?? approval.args.revision_count ?? 0);

  useEffect(() => {
    setProcurementArgs(approval.args);
  }, [approval.args]);

  useEffect(() => {
    setRejectPanel(false);
    setSelectedPlanId("");
    setOtherPlanText("");
    setError(null);
  }, [approval.id, revisionKey]);

  const procurement =
    approval.kind === "procurement_choice" ? procurementApprovalView(procurementArgs) : null;
  const poEmail = isPoDispatchEmail(approval);
  const [emailArgs, setEmailArgs] = useState(approval.args);
  const emailRevisionKey = Number(emailArgs.revision_count ?? approval.args.revision_count ?? 0);

  useEffect(() => {
    setEmailArgs(approval.args);
  }, [approval.args]);

  useEffect(() => {
    if (poEmail) {
      setRejectPanel(false);
      setOtherPlanText("");
      setError(null);
    }
  }, [approval.id, emailRevisionKey, poEmail]);

  const submit = async (decision: DecisionInput["decision"], extra?: Partial<DecisionInput>) => {
    setError(null);
    const body: DecisionInput = {
      decision,
      comment: comment || undefined,
      reviewer: "console-reviewer",
      ...extra,
    };
    if (decision === "edit") {
      if (approval.kind === "tool") {
        try {
          body.args = JSON.parse(argsText) as Record<string, unknown>;
        } catch {
          setError("Arguments must be valid JSON.");
          return;
        }
      } else {
        body.response = response;
      }
    }
    if (decision === "approve" && approval.kind === "escalation" && response) body.response = response;
    setBusy(decision);
    try {
      const updated = await api.decide(approval.id, body);
      if (body.decision === "revise") {
        if (approval.kind === "procurement_choice") setProcurementArgs(updated.args);
        if (poEmail) setEmailArgs(updated.args);
      }
      onDecided?.(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const confirmRevision = async () => {
    const other = otherPlanText.trim();
    if (poEmail) {
      if (!other) {
        setError("Enter the revised email body.");
        return;
      }
      await submit("revise", { other_plan_text: other });
      return;
    }
    const planId = selectedPlanId.trim();
    if (!other && !planId) {
      setError("Select an alternative or enter a custom plan.");
      return;
    }
    if (other && planId) {
      setError("Use either an alternative or the text box, not both.");
      return;
    }
    await submit("revise", other ? { other_plan_text: other } : { selected_plan_id: planId });
  };

  const title =
    poEmail
      ? "Purchase order email to procurement"
      : approval.kind === "procurement_choice"
      ? "Replenishment proposal"
      : approval.kind === "tool"
        ? `Run ${approval.tool_name}`
        : approval.kind === "escalation"
          ? "Agent escalated to a human"
          : "Review low-confidence answer";

  const revisionChoice = otherPlanText.trim() ? "other" : selectedPlanId.trim() ? "alt" : "none";

  return (
    <Card
      className={clsx(
        "min-w-0 w-full max-w-full overflow-hidden",
        pending && "border-amber-300 ring-1 ring-amber-200",
      )}
    >
      <div className="flex flex-wrap items-start gap-3 p-4">
        <div className="rounded-lg bg-amber-100 p-2 text-amber-700">
          <ShieldAlert className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-slate-900">{title}</h3>
            <AgentBadge agent={approval.agent} />
            <Badge tone={RISK_TONE[approval.risk_level] ?? "slate"}>{approval.risk_level} risk</Badge>
            {!pending && <Badge tone={approval.status === "rejected" ? "red" : "green"}>{approval.status}</Badge>}
            {revisionKey > 0 && pending && approval.kind === "procurement_choice" && (
              <Badge tone="slate">Revision {revisionKey}</Badge>
            )}
            {emailRevisionKey > 0 && pending && poEmail && (
              <Badge tone="slate">Revision {emailRevisionKey}</Badge>
            )}
          </div>
          {poEmail ? (
            <div className="mt-2 space-y-1.5 text-sm text-slate-600">
              <p>Leadership approval is required before this email is sent.</p>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs sm:text-sm">
                <dt className="font-medium text-slate-700">Order</dt>
                <dd className="min-w-0 break-words">
                  {String(emailArgs.qty ?? "")} × {String(emailArgs.product_code ?? "")} from{" "}
                  {String(emailArgs.supplier_name ?? "")}
                </dd>
                <dt className="font-medium text-slate-700">To</dt>
                <dd className="min-w-0 break-all font-mono text-[0.8125rem] leading-snug text-slate-600">
                  {String(emailArgs.to ?? "")}
                </dd>
              </dl>
            </div>
          ) : (
            <p className="mt-1 break-words text-sm text-slate-600">
              {approval.kind === "procurement_choice" && procurement
                ? procurement.headerLine
                : approval.reason}
            </p>
          )}
          <p className="mt-1 text-xs text-slate-400">
            {timeAgo(approval.created_at)} · user <span className="font-mono">{approval.user_id}</span>
            {!compact && (
              <>
                {" · "}
                <Link to={`/runs/${approval.run_id}`} className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline">
                  view run <ExternalLink className="h-3 w-3" />
                </Link>
              </>
            )}
          </p>
        </div>
      </div>

      <div className="space-y-3 border-t border-slate-100 px-4 py-3">
        {poEmail && !rejectPanel && (
          <div className="space-y-3 text-sm text-slate-700">
            <p className="text-slate-600">
              Review the email below. Approve to send to procurement, or reject to revise the body.
            </p>
            <p className="min-w-0 break-words">
              <span className="font-medium text-slate-800">To:</span>{" "}
              <span className="break-all font-mono text-xs text-slate-700">{String(emailArgs.to ?? "")}</span>
            </p>
            <p>
              <span className="font-medium text-slate-800">Subject:</span> {String(emailArgs.subject ?? "")}
            </p>
            <p className="font-medium text-slate-800">Body</p>
            <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-700 ring-1 ring-inset ring-slate-200">
              {String(emailArgs.body ?? "")}
            </pre>
          </div>
        )}
        {poEmail && rejectPanel && pending && (
          <div className="space-y-3 text-sm text-slate-700">
            <p className="font-medium text-slate-800">Revise the email body</p>
            <p className="text-slate-600">Your text replaces the entire email body (mock).</p>
            <textarea
              value={otherPlanText}
              onChange={(e) => setOtherPlanText(e.target.value)}
              rows={10}
              placeholder="Enter the full revised email body"
              className="w-full rounded-lg border border-slate-300 p-2.5 font-mono text-xs focus:border-indigo-500 focus:outline-none"
            />
          </div>
        )}
        {approval.kind === "tool" &&
          !poEmail &&
          (editing && pending ? (
            <textarea
              value={argsText}
              onChange={(e) => setArgsText(e.target.value)}
              rows={Math.min(12, argsText.split("\n").length + 1)}
              spellCheck={false}
              className="w-full rounded-lg border border-slate-300 bg-slate-900 p-3 font-mono text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          ) : (
            <JsonBlock value={approval.args} />
          ))}
        {approval.kind === "escalation" && (
          <div className="space-y-2">
            <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700 ring-1 ring-inset ring-slate-200">
              {String(approval.args.question ?? "")}
            </p>
            {pending && (
              <textarea
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                rows={2}
                placeholder="Guidance for the agent (e.g. 'Offer a 20% voucher and apologise')"
                className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            )}
          </div>
        )}
        {approval.kind === "final_review" &&
          (pending ? (
            <textarea
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          ) : (
            <p className="whitespace-pre-wrap text-sm text-slate-600">{String(approval.args.answer ?? "")}</p>
          ))}
        {approval.kind === "procurement_choice" && procurement && !rejectPanel && (
          <ProcurementProposalBody procurement={procurement} showConfirmation={pending} />
        )}
        {approval.kind === "procurement_choice" && procurement && rejectPanel && pending && (
          <div className="space-y-4 text-sm text-slate-700">
            <p className="font-medium text-slate-800">
              You rejected the recommended plan. Which option do you want to proceed with?
            </p>
            {procurement.alternatives.length > 0 && (
              <div className="space-y-2">
                {procurement.alternatives.map((alt) => (
                  <label
                    key={alt.plan_id}
                    className={clsx(
                      "flex cursor-pointer gap-3 rounded-lg border p-3",
                      revisionChoice === "alt" && selectedPlanId === alt.plan_id
                        ? "border-indigo-400 bg-indigo-50/50"
                        : "border-slate-200 bg-white",
                    )}
                  >
                    <input
                      type="radio"
                      name={`reject-alt-${approval.id}`}
                      className="mt-1"
                      checked={selectedPlanId === alt.plan_id}
                      onChange={() => {
                        setSelectedPlanId(alt.plan_id);
                        setOtherPlanText("");
                      }}
                    />
                    <span className="text-slate-700">{alt.summary}</span>
                  </label>
                ))}
              </div>
            )}
            <div>
              <p className="mb-1 font-medium text-slate-800">Other</p>
              <textarea
                value={otherPlanText}
                onChange={(e) => {
                  setOtherPlanText(e.target.value);
                  if (e.target.value.trim()) setSelectedPlanId("");
                }}
                rows={3}
                placeholder="Describe the plan you want to proceed with"
                className="w-full rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
        )}
        {!pending && approval.decision && (
          <p className="text-xs text-slate-500">
            {titleCase(String(approval.decision.decision))} by {approval.reviewer}
            {approval.decision.comment ? ` - "${String(approval.decision.comment)}"` : ""}
          </p>
        )}
      </div>

      {pending && (
        <div
          className={
            approval.kind === "procurement_choice" || poEmail
              ? "flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-3"
              : "flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-3"
          }
        >
          {approval.kind !== "procurement_choice" && !poEmail && (
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Optional comment"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          )}
          {approval.kind === "tool" && !poEmail && !editing && (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="h-3.5 w-3.5" /> Edit
            </Button>
          )}
          {(approval.kind === "procurement_choice" || poEmail) && rejectPanel ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setRejectPanel(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" loading={busy === "revise"} onClick={() => void confirmRevision()}>
                {poEmail ? "Apply body" : "Confirm plan"}
              </Button>
            </>
          ) : (
            <>
              {approval.kind === "procurement_choice" || poEmail ? (
                <Button variant="danger" size="sm" onClick={() => setRejectPanel(true)}>
                  <X className="h-3.5 w-3.5" /> Reject
                </Button>
              ) : (
                <Button variant="danger" size="sm" loading={busy === "reject"} onClick={() => void submit("reject")}>
                  <X className="h-3.5 w-3.5" /> Reject
                </Button>
              )}
              {(editing || approval.kind === "final_review") &&
                approval.kind !== "procurement_choice" &&
                !poEmail && (
                <Button variant="primary" size="sm" loading={busy === "edit"} onClick={() => void submit("edit")}>
                  <Pencil className="h-3.5 w-3.5" /> {approval.kind === "final_review" ? "Send edited" : "Approve edited"}
                </Button>
              )}
              <Button variant="success" size="sm" loading={busy === "approve"} onClick={() => void submit("approve")}>
                <Check className="h-3.5 w-3.5" /> {poEmail ? "Approve send" : "Approve"}
              </Button>
            </>
          )}
          {error && <p className="w-full text-xs text-red-600">{error}</p>}
        </div>
      )}
    </Card>
  );
}
