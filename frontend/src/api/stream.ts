// Server-sent events over a POST (EventSource only does GET). The event shapes mirror
// src/counterwrench/api/events.py; the stream itself isn't described by the OpenAPI schema.

export type Severity =
  | "safety_critical"
  | "needs_service"
  | "needs_adjustment"
  | "cosmetic"
  | "no_action_needed";

export interface RowResult {
  row_id: string;
  severity: Severity;
  likely_causes: string[];
  likely_area: string | null;
  agrees_with_suspected_area: boolean | null;
  disagreement_reason: string | null;
  question_for_customer: string | null;
  suggested_labor: string[];
  suggested_part_categories: string[];
  citations: string[];
}

export type StreamEvent =
  | { event: "accepted"; data: { intake_id: string; run_id: string; previous: string | null;
      pii_redacted: Record<string, number>; guardrail_flags: string[] } }
  | { event: "bike"; data: { bike_id: string | null; name: string | null; note: string | null;
      question: string | null } }
  | { event: "row"; data: RowResult }
  | { event: "row_failed"; data: { row_id: string; error: string } }
  | { event: "route"; data: { outcome: string; escalated: boolean;
      escalation_message: string | null; questions: Record<string, string> } }
  | { event: "draft"; data: { work_order_id: number | null; estimate_total: string | null;
      unverified_parts: string[]; error: string | null } }
  | { event: "triaged"; data: Record<string, unknown> }
  | { event: "review"; data: Record<string, unknown> }
  | { event: "done"; data: { intake_id: string; outcome: string; work_order_id: number | null;
      awaiting_confirmation: boolean; awaiting_review: boolean } }
  | { event: "error"; data: { message: string } };

/** Split buffered text into complete events; returns them and the unfinished remainder. */
export function parseEvents(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (event && data.length) events.push({ event, data: JSON.parse(data.join("\n")) } as StreamEvent);
  }
  return { events, rest };
}

/** POST `body` and call `onEvent` for each event as it arrives. Throws on an HTTP error with
 *  the server's message (e.g. a 422 for an invalid intake), before any event is delivered. */
export async function postStream(url: string, body: unknown, onEvent: (e: StreamEvent) => void) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text.slice(0, 500)}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseEvents(buffer);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseEvents(buffer + "\n\n").events.forEach(onEvent);
}
