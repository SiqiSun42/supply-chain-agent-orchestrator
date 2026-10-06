"""Deterministic, offline LLM used for tests, demos and keyless local development.

It does not try to be clever: it follows a small script driven by keywords in the task so
that every orchestration feature (delegation, tool use, memory, HITL escalation, low
confidence review) can be exercised end-to-end without network access.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from pydantic import BaseModel

from orchestrator.agents.contracts import FinalAnswer, MemoryExtraction, MemoryItem, RouteDecision
from orchestrator.supply_chain import (
    build_replenishment_approval_args,
    build_send_email_args_for_po,
    is_purchase_order_dispatch_task,
)
from orchestrator.supply_chain.constants import DEFAULT_DB_PATH
from orchestrator.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    PromptContext,
    ToolCall,
    ToolSpec,
    Usage,
)

AGENT_ORDER = ("researcher", "analyst", "ops", "writer")

_OPS_RE = re.compile(
    r"\b(refund\w*|e-?mail\w*|ticket\w*|orders?|ord-\d+|escalat\w*|manager|human|cancel\w*|complain\w*)\b"
)
_ANALYST_RE = re.compile(
    r"\b(calculat\w*|compute\w*|how much|total|percent\w*|sum|average|math|times|"
    r"what time|today|date|current time)\b"
)
_RESEARCH_RE = re.compile(
    r"\b(research\w*|what|why|how|explain\w*|polic(?:y|ies)|find|look up|search\w*|"
    r"include\w*|who|tell me|know|plan|pricing|shipping|compare)\b"
)
_WRITER_RE = re.compile(
    r"\b(write|draft\w*|summar\w*|compose|note|announcement|reply|blog|memo|welcome)\b"
)
_SPECULATIVE_RE = re.compile(r"\b(forecast\w*|predict\w*|guess\w*|speculat\w*|next year)\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_ORDER_RE = re.compile(r"\b(ORD-\d{3,})\b", re.IGNORECASE)
_PART_CODE_RE = re.compile(r"\b([A-Z]{3}-\d+)\b")
_WAREHOUSE_RE = re.compile(r"\b(WH-\d+)\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s?(?:usd|dollars)\b"
)
_EXPR_RE = re.compile(r"[\d(][\d\s.+\-*/^()]*[\d)]")
_PERCENT_OF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_NUM_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _call_id(*parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]
    return f"call_{digest}"


_CUSTOMER_RE = re.compile(r"\b(CUST-\d+)\b", re.IGNORECASE)


def is_part_inventory_task(task: str) -> bool:
    if is_replenishment_task(task):
        return False
    if not _PART_CODE_RE.search(task):
        return False
    t = task.lower()
    return "inventory" in t or "warehouse" in t or bool(_WAREHOUSE_RE.search(task))


def _requested_replenishment_approval(scratch: list[Message]) -> bool:
    for message in scratch:
        if message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                if call.name in (
                    "request_replenishment_approval",
                    "submit_replenishment_for_approval",
                ):
                    return True
    return False


def is_replenishment_task(task: str) -> bool:
    if not _PART_CODE_RE.search(task):
        return False
    t = task.lower()
    return "replenish" in t or ("leadership" in t and "approval" in t)


def replenishment_qty(task: str) -> int:
    match = re.search(r"\breplenish(?:ment)?\s+(\d+)\s*units?\b", task, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\s*units?\b", task, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 200


def is_customer_trade_task(task: str) -> bool:
    if not _CUSTOMER_RE.search(task):
        return False
    t = task.lower()
    return any(
        phrase in t
        for phrase in (
            "trading",
            "trade",
            "shipment",
            "revenue",
            "three months",
            "3 months",
            "prior three",
        )
    )


def _requested_send_email(scratch: list[Message]) -> bool:
    for message in scratch:
        if message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                if call.name == "send_email":
                    return True
    return False


def _po_email_sent_summary(item: dict[str, Any]) -> str:
    body = str(item.get("body") or "")
    lines = [
        "Operations summary:",
        "",
        "The following content was sent to procurement:",
        "",
        f"To: {item.get('to', '')}",
        f"Subject: {item.get('subject', '')}",
        "",
        body,
        "",
        "Procurement will review release of this purchase order request.",
    ]
    return "\n".join(lines)


def plan_agents(task: str) -> list[str]:
    """Which specialists a task needs, in delegation order."""
    if is_purchase_order_dispatch_task(task):
        return ["ops"]
    if is_replenishment_task(task):
        return ["ops"]
    if is_part_inventory_task(task):
        return ["ops"]
    if is_customer_trade_task(task):
        return ["ops"]
    t = task.lower()
    needed: set[str] = set()
    if _OPS_RE.search(t):
        needed.add("ops")
        if "refund" in t:
            needed.add("researcher")  # check the refund policy before acting
    if extract_expressions(task) or _ANALYST_RE.search(t):
        needed.add("analyst")
    if _RESEARCH_RE.search(t):
        needed.add("researcher")
    if _WRITER_RE.search(t):
        needed.add("writer")
    if not needed:
        needed = {"researcher", "writer"}
    return [a for a in AGENT_ORDER if a in needed]


def extract_expressions(task: str) -> list[str]:
    text = _NUM_COMMA_RE.sub("", task)
    text = _PERCENT_OF_RE.sub(lambda m: f"({m.group(1)}/100)*{m.group(2)}", text)
    text = re.sub("(\\d)\\s*[x\u00d7]\\s*(\\d)", r"\1*\2", text)
    found: list[str] = []
    for match in _EXPR_RE.finditer(text):
        expr = match.group(0).strip()
        if re.search(r"\d\s*[+\-*/^]\s*[\d(]", expr) or re.search(r"\)\s*[*/+\-]", expr):
            found.append(expr)
    return found


def _leadership_decision_bullets(
    scratch: list[Message], results: dict[str, list[dict[str, Any]]]
) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()

    def add(line: str) -> None:
        key = line.strip()
        if key and key not in seen:
            seen.add(key)
            bullets.append(line)

    for item in results.get("record_replenishment_choice", []):
        if item.get("message"):
            add(f"- {item['message']}")
        elif item.get("status") == "recorded" and item.get("supplier_name"):
            add(
                f"- Leadership selected {item['supplier_name']} to replenish "
                f"{item.get('qty_to_order', '?')} units of {item.get('product_code', 'part')} "
                f"for {item.get('warehouse_name', 'warehouse')}."
            )
    for item in results.get("request_replenishment_approval", []):
        if item.get("message"):
            add(f"- {item['message']}")
        elif item.get("status") == "recorded":
            plan = item.get("plan") if isinstance(item.get("plan"), dict) else {}
            summary = str(plan.get("summary") or "").strip()
            if summary:
                add(f"- Leadership approved plan: {summary}")
    for msg in scratch:
        if msg.role != "tool":
            continue
        try:
            data = json.loads(msg.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("status") == "recorded" and data.get("message"):
            add(f"- {data['message']}")
        elif data.get("supplier_name") and data.get("qty_to_order"):
            add(
                f"- Leadership selected {data['supplier_name']} to replenish "
                f"{data['qty_to_order']} units of {data.get('product_code', 'part')} "
                f"for {data.get('warehouse_name', 'warehouse')}."
            )
    return bullets


def _replenishment_ready_to_summarize(
    ctx: PromptContext, results: dict[str, list[dict[str, Any]]]
) -> bool:
    if not is_replenishment_task(ctx.task):
        return False
    if "query_part_inventory" not in results or "query_supplier_offers" not in results:
        return False
    if _leadership_decision_bullets(ctx.scratch, results):
        return True
    if results.get("record_replenishment_choice"):
        return True
    for item in results.get("request_replenishment_approval", []):
        if item.get("status") == "recorded" or item.get("message"):
            return True
    return False


def _replenishment_operations_summary(
    scratch: list[Message], results: dict[str, list[dict[str, Any]]]
) -> str:
    lines: list[str] = ["Operations summary:", ""]
    for item in results.get("query_part_inventory", []):
        if "product_code" not in item:
            continue
        below = item.get("below_reorder_point")
        status = "below reorder point" if below else "at or above reorder point"
        lines.append(
            f"- {item['product_code']} @ {item['warehouse_name']} "
            f"(snapshot {item['snapshot_date']}): "
            f"on_hand={item['units_on_hand']}, reorder={item['reorder_point']}, "
            f"reserved={item['units_reserved']}, "
            f"in_transit={item['units_in_transit']}; {status}."
        )
    lines.append("")
    for item in results.get("query_supplier_offers", []):
        if "offers" not in item:
            continue
        product_code = item.get("product_code", "HYD-08")
        count = item.get("offer_count", len(item.get("offers") or []))
        lines.append(f"Supplier offers for {product_code} ({count} rows):")
        for offer in item.get("offers") or []:
            lines.append(
                f"- {offer['supplier_name']}: qty_available={offer['qty_available']}, "
                f"unit_price={offer['unit_price']}, lead_days={offer['lead_days']}"
            )
    lines.append("")
    lines.append("Leadership decision:")
    decision_bullets = _leadership_decision_bullets(scratch, results)
    if decision_bullets:
        lines.extend(decision_bullets)
    else:
        lines.append("- Leadership approval recorded (see audit for plan details).")
    lines.append("")
    lines.append(
        "Procurement summary: leadership approval is on file. "
        "No live purchase order is issued in this demo environment."
    )
    return "\n".join(lines)


def _tool_results(scratch: list[Message]) -> dict[str, list[dict[str, Any]]]:
    """Map tool name -> list of parsed results already present in the scratchpad."""
    names: dict[str, str] = {}
    for msg in scratch:
        for call in msg.tool_calls:
            names[call.id] = call.name
        if msg.role == "tool" and msg.tool_call_id and msg.name:
            names.setdefault(msg.tool_call_id, msg.name)
    results: dict[str, list[dict[str, Any]]] = {}
    for msg in scratch:
        if msg.role == "tool" and msg.tool_call_id:
            name = names.get(msg.tool_call_id, msg.name or "unknown")
            try:
                parsed = json.loads(msg.content)
            except json.JSONDecodeError:
                parsed = {"text": msg.content}
            if not isinstance(parsed, dict):
                parsed = {"value": parsed}
            results.setdefault(name, []).append(parsed)
    return results


def _user_name(memories: list[str]) -> str | None:
    for memory in memories:
        match = re.search(r"name is ([A-Z][\w'-]+)", memory)
        if match:
            return match.group(1)
    return None


class MockProvider(LLMProvider):
    """Scripted provider. Behaviour is a pure function of the prompt context."""

    name = "mock"

    def __init__(self, model: str = "mock-scripted-v1") -> None:
        super().__init__(model)

    # ------------------------------------------------------------------ helpers
    def _respond(
        self,
        messages: list[Message],
        content: str = "",
        calls: list[ToolCall] | None = None,
        system: str = "",
    ) -> LLMResponse:
        start = time.perf_counter()
        prompt_chars = len(system) + sum(len(m.content) for m in messages)
        output = content + json.dumps([c.model_dump() for c in calls or []])
        return LLMResponse(
            content=content,
            tool_calls=calls or [],
            usage=Usage(input_tokens=max(1, prompt_chars // 4), output_tokens=_tokens(output)),
            model=self.model,
            latency_ms=round((time.perf_counter() - start) * 1000 + 1.0, 2),
        )

    # ------------------------------------------------------------------ chat (workers)
    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        context: PromptContext,
    ) -> LLMResponse:
        allowed = {t.name for t in tools}
        handler = {
            "researcher": self._researcher,
            "analyst": self._analyst,
            "ops": self._ops,
            "writer": self._writer,
        }.get(context.agent)
        if handler is None:
            return self._respond(messages, f"[{context.agent}] Nothing to do.", system=system)
        content, calls = handler(context, _tool_results(context.scratch))
        calls = [c for c in calls if c.name in allowed]
        return self._respond(messages, content, calls, system=system)

    def _researcher(
        self, ctx: PromptContext, results: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, list[ToolCall]]:
        query = ctx.instructions or ctx.task
        if "knowledge_search" not in results:
            return "Searching the knowledge base and long-term memory.", [
                ToolCall(
                    id=_call_id("kb", query),
                    name="knowledge_search",
                    args={"query": ctx.task, "top_k": 3},
                ),
                ToolCall(
                    id=_call_id("mem", query),
                    name="recall_memory",
                    args={"query": ctx.task, "k": 3},
                ),
            ]
        lines = ["Research findings:"]
        for hit in results["knowledge_search"][0].get("results", [])[:3]:
            lines.append(f"- {hit['title']} / {hit['section']}: {hit['snippet']}")
        if len(lines) == 1:
            lines.append("- No relevant knowledge-base articles were found.")
        recalled = results.get("recall_memory", [{}])[0].get("memories", [])
        if recalled:
            lines.append("Relevant memories: " + "; ".join(m["content"] for m in recalled))
        return "\n".join(lines), []

    def _analyst(
        self, ctx: PromptContext, results: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, list[ToolCall]]:
        expressions = extract_expressions(ctx.task)
        wants_time = bool(re.search(r"\b(time|today|date)\b", ctx.task.lower()))
        if "calculator" not in results and "current_time" not in results:
            calls = [
                ToolCall(id=_call_id("calc", e), name="calculator", args={"expression": e})
                for e in expressions
            ]
            if wants_time:
                calls.append(
                    ToolCall(id=_call_id("time"), name="current_time", args={"timezone": "UTC"})
                )
            if calls:
                return "Running the numbers.", calls
            return "No quantitative computation was required for this task.", []
        lines = ["Analysis:"]
        for res in results.get("calculator", []):
            if "result" in res:
                lines.append(f"- {res['expression']} = {res['result']}")
            else:
                lines.append(f"- Could not evaluate: {res.get('error', 'unknown error')}")
        for res in results.get("current_time", []):
            lines.append(f"- Current time ({res.get('timezone')}): {res.get('iso')}")
        return "\n".join(lines), []

    def _ops_plan(self, ctx: PromptContext) -> list[ToolCall]:
        task = ctx.task
        t = task.lower()
        if is_replenishment_task(task):
            part = _PART_CODE_RE.search(task)
            warehouse = _WAREHOUSE_RE.search(task)
            product_code = part.group(1) if part else "HYD-08"
            warehouse_name = warehouse.group(1).upper() if warehouse else "WH-1"
            return [
                ToolCall(
                    id=_call_id("inv", product_code, warehouse_name),
                    name="query_part_inventory",
                    args={
                        "product_code": product_code,
                        "warehouse_name": warehouse_name,
                    },
                ),
                ToolCall(
                    id=_call_id("offers", product_code),
                    name="query_supplier_offers",
                    args={"product_code": product_code},
                ),
            ]
        if is_part_inventory_task(task):
            part = _PART_CODE_RE.search(task)
            warehouse = _WAREHOUSE_RE.search(task)
            product_code = part.group(1) if part else "HYD-08"
            warehouse_name = warehouse.group(1).upper() if warehouse else "WH-1"
            return [
                ToolCall(
                    id=_call_id("inv", product_code, warehouse_name),
                    name="query_part_inventory",
                    args={
                        "product_code": product_code,
                        "warehouse_name": warehouse_name,
                    },
                )
            ]
        if is_customer_trade_task(task):
            customer = _CUSTOMER_RE.search(task)
            customer_name = customer.group(1).upper() if customer else "CUST-005"
            months = 3
            if re.search(r"\b(\d+)\s*months?\b", t):
                months = int(re.search(r"\b(\d+)\s*months?\b", t).group(1))  # type: ignore[union-attr]
            return [
                ToolCall(
                    id=_call_id("trade", customer_name, str(months)),
                    name="query_customer_trade_summary",
                    args={"customer_name": customer_name, "months": months},
                )
            ]
        plan: list[ToolCall] = []
        order = _ORDER_RE.search(task)
        order_id = order.group(1).upper() if order else None
        if order_id:
            plan.append(
                ToolCall(
                    id=_call_id("lookup", order_id),
                    name="lookup_order",
                    args={"order_id": order_id},
                )
            )
        if re.search(r"\bescalat\w*|\bmanager\b|\bspeak to a human\b|\bhuman agent\b", t):
            plan.append(
                ToolCall(
                    id=_call_id("escalate", task),
                    name="escalate_to_human",
                    args={
                        "reason": "Customer explicitly asked for a human / manager.",
                        "question": f"How should we respond to: {task[:200]}",
                    },
                )
            )
        if "refund" in t:
            amount_match = _AMOUNT_RE.search(task)
            raw_amount = (
                next((g for g in amount_match.groups() if g), None) if amount_match else None
            )
            amount = float(raw_amount.replace(",", "")) if raw_amount else 49.0
            plan.append(
                ToolCall(
                    id=_call_id("refund", order_id or "", str(amount)),
                    name="issue_refund",
                    args={
                        "order_id": order_id or "ORD-1001",
                        "amount": amount,
                        "reason": "damaged item" if "damag" in t else "customer request",
                    },
                )
            )
        email = _EMAIL_RE.search(task)
        if email and re.search(r"\b(e-?mail|send|notify|confirm|contact)\b", t):
            plan.append(
                ToolCall(
                    id=_call_id("email", email.group(0)),
                    name="send_email",
                    args={
                        "to": email.group(0),
                        "subject": "Update on your request",
                        "body": "Hello,\n\nWe have processed your request. "
                        "Please reply to this email if anything looks wrong.\n\n"
                        "- Support Team",
                    },
                )
            )
        if re.search(r"\b(ticket|bug|issue|outage|broken)\b", t):
            plan.append(
                ToolCall(
                    id=_call_id("ticket", task),
                    name="create_ticket",
                    args={
                        "subject": task[:80],
                        "description": task,
                        "priority": "high" if "urgent" in t else "normal",
                    },
                )
            )
        return plan

    def _ops(
        self, ctx: PromptContext, results: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, list[ToolCall]]:
        done_ids = {m.tool_call_id for m in ctx.scratch if m.role == "tool"}
        if is_purchase_order_dispatch_task(ctx.task):
            sent_items = [
                item
                for item in results.get("send_email", [])
                if item.get("status") == "sent"
            ]
            if sent_items:
                return _po_email_sent_summary(sent_items[-1]), []
            if not _requested_send_email(ctx.scratch):
                try:
                    email_args = build_send_email_args_for_po(
                        ctx.task, db_path=DEFAULT_DB_PATH
                    )
                except ValueError as exc:
                    return (
                        "Purchase order request cannot be executed.\n\n"
                        f"{exc}\n\nNo email was drafted or sent."
                    ), []
                return "PO email drafted. Awaiting approval to send to procurement.", [
                    ToolCall(
                        id=_call_id(
                            "po-email",
                            email_args["supplier_name"],
                            str(email_args["qty"]),
                        ),
                        name="send_email",
                        args=email_args,
                    )
                ]
        if is_replenishment_task(ctx.task):
            if "record_replenishment_choice" not in results and not _requested_replenishment_approval(
                ctx.scratch
            ):
                for call in self._ops_plan(ctx):
                    if call.id not in done_ids:
                        return f"Next action: {call.name}.", [call]
            if (
                "record_replenishment_choice" not in results
                and "query_part_inventory" in results
                and "query_supplier_offers" in results
                and not _requested_replenishment_approval(ctx.scratch)
            ):
                part = _PART_CODE_RE.search(ctx.task)
                warehouse = _WAREHOUSE_RE.search(ctx.task)
                product_code = part.group(1) if part else "HYD-08"
                warehouse_name = warehouse.group(1).upper() if warehouse else "WH-1"
                qty = replenishment_qty(ctx.task)
                return "Submit replenishment options for leadership approval.", [
                    ToolCall(
                        id=_call_id("repl-approval", product_code, str(qty)),
                        name="submit_replenishment_for_approval",
                        args={
                            "product_code": product_code,
                            "warehouse_name": warehouse_name,
                            "qty_needed": qty,
                        },
                    )
                ]
        for call in self._ops_plan(ctx):
            if call.id not in done_ids:
                return f"Next action: {call.name}.", [call]
        if _replenishment_ready_to_summarize(ctx, results):
            return _replenishment_operations_summary(ctx.scratch, results), []
        lines = ["Operations summary:"]
        for name, items in results.items():
            for item in items:
                status = item.get("status", "ok")
                if name == "query_part_inventory" and "product_code" in item:
                    below = item.get("below_reorder_point")
                    status = "below reorder point" if below else "at or above reorder point"
                    lines.append(
                        f"- {item['product_code']} @ {item['warehouse_name']} "
                        f"(snapshot {item['snapshot_date']}): "
                        f"on_hand={item['units_on_hand']}, reorder={item['reorder_point']}, "
                        f"reserved={item['units_reserved']}, "
                        f"in_transit={item['units_in_transit']}; {status}."
                    )
                elif name == "query_supplier_offers" and "offers" in item:
                    lines.append(f"- Supplier offers for {item['product_code']} ({item['offer_count']} rows):")
                    for offer in item["offers"]:
                        lines.append(
                            f"  - {offer['supplier_name']}: qty_available={offer['qty_available']}, "
                            f"unit_price={offer['unit_price']}, lead_days={offer['lead_days']}"
                        )
                elif name == "record_replenishment_choice" and item.get("status") == "recorded":
                    lines.append(f"- {item.get('message', 'Replenishment choice recorded.')}")
                elif name == "query_customer_trade_summary" and "customer_name" in item:
                    period = f"{item['period_start']} to {item['period_end']}"
                    lines.append(
                        f"- {item['customer_name']} ({period}): "
                        f"shipments={item['shipment_count']}, "
                        f"qty_shipped={item['total_qty_shipped']}, "
                        f"revenue=${item['total_revenue']:,.2f}."
                    )
                elif name == "lookup_order" and "order" in item:
                    order = item["order"]
                    lines.append(
                        f"- Order {order['order_id']}: {order['status']}, "
                        f"total ${order['total']:.2f} ({order['item']})"
                    )
                elif name == "issue_refund":
                    if status == "rejected_by_human":
                        lines.append(
                            "- Refund NOT issued: a reviewer rejected it "
                            f"({item.get('comment') or 'no comment'})."
                        )
                    elif "refund_id" in item:
                        lines.append(
                            f"- Refund {item['refund_id']} issued for ${item['amount']:.2f} "
                            f"on {item['order_id']}."
                        )
                    else:
                        lines.append(f"- Refund failed: {item.get('error', status)}")
                elif name == "send_email":
                    if status == "rejected_by_human":
                        lines.append("- Email was NOT sent: rejected by a reviewer.")
                    elif "message_id" in item:
                        if item.get("purpose") == "purchase_order_dispatch" and item.get("body"):
                            lines.extend(_po_email_sent_summary(item).splitlines()[2:])
                        else:
                            lines.append(f"- Email {item['message_id']} sent to {item['to']}.")
                    else:
                        lines.append(f"- Email failed: {item.get('error', status)}")
                elif name == "create_ticket" and "ticket_id" in item:
                    lines.append(f"- Ticket {item['ticket_id']} created ({item['priority']}).")
                elif name == "escalate_to_human":
                    lines.append(
                        "- Escalated to a human. Guidance received: "
                        f"{item.get('human_response') or 'none'}"
                    )
                elif "error" in item:
                    lines.append(f"- {name} failed: {item['error']}")
        if len(lines) == 1:
            lines.append("- No operational action was necessary.")
        return "\n".join(lines), []

    def _writer(
        self, ctx: PromptContext, results: dict[str, list[dict[str, Any]]]
    ) -> tuple[str, list[ToolCall]]:
        name = _user_name(ctx.memories)
        greeting = f"Hi {name}," if name else "Hello,"
        body = [greeting, ""]
        findings = [s["output"] for s in ctx.steps if s.get("agent") != "writer"]
        if findings:
            body.append("Here is a concise summary of what the team found:")
            for chunk in findings:
                for line in chunk.splitlines():
                    if line.startswith("- "):
                        body.append(line)
        else:
            body.append(
                "Welcome aboard - we're glad to have you with us. The team is here to help "
                "with orders, billing and anything else you need."
            )
            prefs = [
                m[len("User prefers ") :] for m in ctx.memories if m.startswith("User prefers ")
            ]
            if prefs:
                body.append(f"(Noted from earlier conversations: you prefer {'; '.join(prefs)}.)")
        body += ["", "Best regards,", "The Assistant"]
        return "\n".join(body), []

    # ------------------------------------------------------------------ structured
    def structured[T: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T],
        context: PromptContext,
    ) -> tuple[T, LLMResponse]:
        result: BaseModel
        if schema is RouteDecision:
            result = self._route(context)
        elif schema is FinalAnswer:
            result = self._finalize(context)
        elif schema is MemoryExtraction:
            result = self._extract(context)
        else:  # pragma: no cover - defensive
            raise TypeError(f"MockProvider cannot produce {schema.__name__}")
        meta = self._respond(messages, result.model_dump_json(), system=system)
        return result, meta  # type: ignore[return-value]

    def _route(self, ctx: PromptContext) -> RouteDecision:
        done = {s["agent"] for s in ctx.steps}
        for agent in plan_agents(ctx.task):
            if agent in ctx.agents and agent not in done:
                return RouteDecision(
                    next=agent,
                    instructions=f"Handle the {agent} portion of the task: {ctx.task}",
                    reasoning=f"The task needs the {agent} specialist and it has not run yet.",
                )
        return RouteDecision(
            next="FINISH",
            instructions="",
            reasoning="All required specialists have contributed; ready to answer.",
        )

    def _finalize(self, ctx: PromptContext) -> FinalAnswer:
        name = _user_name(ctx.memories)
        writer = next((s for s in ctx.steps if s["agent"] == "writer"), None)
        if writer:
            answer = writer["output"]
        else:
            parts = [f"Hi {name}! " if name else ""]
            parts.append("Here's what I did:\n")
            for step in ctx.steps:
                parts.append(f"\n**{step['agent'].title()}**\n{step['output']}\n")
            if not ctx.steps:
                parts.append("I could not find anything to do for this request.")
            answer = "".join(parts).strip()
        confidence = 0.86
        errors = sum(1 for s in ctx.steps if "failed" in s["output"].lower())
        confidence -= 0.25 * errors
        if _SPECULATIVE_RE.search(ctx.task.lower()):
            confidence = 0.35
            answer += "\n\nNote: this is a speculative estimate based on limited internal data."
        return FinalAnswer(answer=answer, confidence=round(max(0.05, confidence), 2))

    def _extract(self, ctx: PromptContext) -> MemoryExtraction:
        text = ctx.task
        items: list[MemoryItem] = []
        patterns: list[tuple[str, str, str]] = [
            (r"\bmy name is ([A-Z][\w'-]+)", "profile", "User's name is {0}"),
            (
                r"\bi (?:work|am working) (?:at|for) ([A-Z][\w&.\- ]*?)(?=[.,;!?]|\band\b|$)",
                "profile",
                "User works at {0}",
            ),
            (r"\bi(?: am|'m) an? ([\w\- ]+?)(?=[.,;!?]|\band\b|$)", "profile", "User is a {0}"),
            (
                r"\bi (?:prefer|always prefer) ([^.;!?]+?)(?=[.;!?]|\band\b|$)",
                "preference",
                "User prefers {0}",
            ),
            (r"\bremember(?: that)? ([^.;!?]+)", "fact", "{0}"),
            (r"\bmy (?!name\b)([a-z ]{3,30}?) is ([^.;!?,]+)", "fact", "User's {0} is {1}"),
        ]
        for pattern, kind, template in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                groups = [g.strip() for g in match.groups()]
                content = template.format(*groups).strip()
                content = re.sub(r"\bmy\b", "the user's", content, flags=re.IGNORECASE)
                content = content[0].upper() + content[1:]
                if len(content) > 8 and all(i.content != content for i in items):
                    items.append(MemoryItem(content=content, kind=kind))
        return MemoryExtraction(memories=items)
