import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import OrderScreen from "./OrderScreen";
import OrdersScreen from "./OrdersScreen";

type Call = { method: string; path: string; query: URLSearchParams; body: unknown };
type Handler = (call: Call) => unknown | Response;

function mockApi(handlers: Record<string, Handler>) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : null;
    const url = new URL(req ? req.url : String(input), "http://x");
    const method = req?.method ?? init?.method ?? "GET";
    const text = req ? await req.text() : (init?.body as string | undefined);
    const call: Call = { method, path: url.pathname, query: url.searchParams, body: text ? JSON.parse(text) : null };
    calls.push(call);
    const handler = handlers[`${method} ${url.pathname}`];
    if (!handler) return new Response("not mocked", { status: 500 });
    const out = handler(call);
    return out instanceof Response ? out : Response.json(out);
  }));
  return calls;
}

const line = (over: object) => ({ labor_code: null, part_id: null, name: "", qty: 1, unit_price_cents: 0, position: null,
  unverified: false, unverified_reason: null, compat_reasons: [], ...over });

const detail = (over: object = {}, status = "awaiting_review") => ({
  order: { id: 7, created_at: "2026-10-21T10:00:00Z", status, bike_id: "hightower", bike_freetext: null,
    bike_name: "2024 Santa Cruz Hightower R Carbon C", severity: "safety_critical", priority: true,
    customer_explanation: "Please don't ride this bike until a mechanic has checked it.", mechanic_notes: "Check the cassette.",
    citations: [], estimate_total_cents: 9000, source: "counter", edited_by: null, edited_at: null, waiver_signed: false,
    reviewed_by: null, reviewed_at: null, review_notes: null,
    intake: { rows: [{ row_id: "r1", complaint: "skipping", suspected_area: "chain", note: "Skips on the big cogs" }],
      answers: { r1: "Only when climbing" } },
    ...over },
  lines: [
    line({ labor_code: "CASSETTE-INSTALL", name: "Cassette install", unit_price_cents: 1500 }),
    line({ part_id: "sram-pg-1230", name: "SRAM PG-1230", unit_price_cents: 7500, compat_reasons: ["hg fits hg (freehub)."] }),
  ],
  sources: [{ id: "x", title: "Drivetrain", heading: "Skipping under load" }],
  triage: { assessments: { r1: { row_id: "r1", severity: "safety_critical", likely_causes: ["Worn cassette"],
    agrees_with_suspected_area: false, disagreement_reason: "Cassette, not chain" } },
    questions: { r1: "Which gear?" }, escalation_message: "DO NOT RIDE. Safety-critical issue on row r1." },
  trace_url: "https://smith.langchain.com/public/abc/r",
  ratings: [],
});

const orderRow = (id: number, severity: string, status: string) => ({ id, status, severity, priority: severity === "safety_critical",
  bike: "2024 Trek Slash", estimate_total_cents: 5500, created_at: new Date().toISOString(), source: "counter", edited: false });

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/orders" element={<OrdersScreen />} /><Route path="/orders/:id" element={<OrderScreen />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}

const click = async (el: HTMLElement) => { await act(async () => { fireEvent.click(el); }); };

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("review queue", () => {
  it("lists what's waiting, links to each order, and switches tabs", async () => {
    const calls = mockApi({ "GET /api/orders": ({ query }) =>
      query.get("status") === "approved" ? [orderRow(3, "needs_service", "approved")]
        : [orderRow(9, "safety_critical", "awaiting_review"), orderRow(8, "needs_service", "awaiting_review")] });
    renderAt("/orders");
    expect((await screen.findByText("#9")).closest("a")!.getAttribute("href")).toBe("/orders/9");
    expect(screen.getByText("Safety-critical")).toBeTruthy();
    await click(screen.getByRole("tab", { name: "Approved" }));
    expect(await screen.findByText("#3")).toBeTruthy();
    expect(calls.at(-1)!.query.get("status")).toBe("approved");
  });
});

describe("order screen", () => {
  it("shows the customer, the triage, the lines with their fit reasons, and the trace", async () => {
    mockApi({ "GET /api/orders/7": () => detail() });
    renderAt("/orders/7");
    expect((await screen.findByRole("alert")).textContent).toContain("DO NOT RIDE");
    expect(screen.getByText("“Skips on the big cogs”")).toBeTruthy();
    expect(screen.getByText(/Customer answered:/).textContent).toContain("Only when climbing");
    expect(screen.getByText(/Disagrees with staff: Cassette, not chain/)).toBeTruthy();
    expect(screen.getByText("hg fits hg (freehub).")).toBeTruthy();
    expect(screen.getByText("$90.00")).toBeTruthy();
    expect(screen.getByText(/Open the trace/).closest("a")!.getAttribute("href")).toContain("smith.langchain.com");
  });

  it("edits lines: removes one, adds labor, and saves with the editor's name", async () => {
    const saved = detail({ edited_by: "sam", estimate_total_cents: 4000 });
    saved.lines = [line({ part_id: "sram-pg-1230", name: "SRAM PG-1230", unit_price_cents: 7500 }),
      line({ labor_code: "INSPECT", name: "Inspection and diagnosis", unit_price_cents: 2500 })];
    const calls = mockApi({
      "GET /api/orders/7": () => detail(),
      "GET /api/labor-menu": () => [{ code: "INSPECT", name: "Inspection and diagnosis", price_cents: 2500, category: "inspection" }],
      "PUT /api/orders/7/lines": () => saved,
    });
    renderAt("/orders/7");
    await click(await screen.findByText("Edit lines"));
    await click(screen.getByLabelText("Remove Cassette install"));
    await screen.findByRole("option", { name: /Inspection and diagnosis/ });
    fireEvent.change(screen.getByLabelText("Add labor"), { target: { value: "INSPECT" } });
    expect((screen.getByText("Save changes") as HTMLButtonElement).disabled).toBe(true);  // needs a name
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "sam" } });
    await click(screen.getByText("Save changes"));

    await waitFor(() => expect(screen.getByText(/edited by sam/)).toBeTruthy());
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toEqual({ editor: "sam", labor_lines: [{ code: "INSPECT", qty: 1 }],
      part_lines: [{ part_id: "sram-pg-1230", qty: 1, position: null }] });
  });

  it("shows why the server refused an edit and keeps editing", async () => {
    mockApi({
      "GET /api/orders/7": () => detail(),
      "GET /api/labor-menu": () => [],
      "PUT /api/orders/7/lines": () => new Response(JSON.stringify({ detail: { problems: ["sram-pg-1230: add the labor that fits it (CASSETTE-INSTALL)."] } }), { status: 422 }),
    });
    renderAt("/orders/7");
    await click(await screen.findByText("Edit lines"));
    await click(screen.getByLabelText("Remove Cassette install"));
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "sam" } });
    await click(screen.getByText("Save changes"));
    expect((await screen.findByText(/add the labor that fits it/)).textContent).toContain("CASSETTE-INSTALL");
    expect(screen.getByText("Save changes")).toBeTruthy();  // still editing
  });

  it("approves with a name, and won't reject without notes", async () => {
    let status = "awaiting_review";
    const calls = mockApi({
      "GET /api/orders/7": () => detail({ status, reviewed_by: status === "approved" ? "sam" : null }, status),
      "POST /api/orders/7/review": () => { status = "approved"; return { id: 7, status, resumed_graph: true }; },
    });
    renderAt("/orders/7");
    const reject = (await screen.findByText("Reject")) as HTMLButtonElement;
    const approve = screen.getByText("Approve") as HTMLButtonElement;
    expect(approve.disabled).toBe(true);  // no name yet
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "sam" } });
    expect(approve.disabled).toBe(false);
    expect(reject.disabled).toBe(true);  // a rejection needs notes
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "wrong cassette" } });
    expect(reject.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "" } });
    await click(approve);

    await waitFor(() => expect(screen.queryByText("Approve")).toBeNull());
    expect(screen.getByText(/by sam/)).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ decision: "approve", reviewer: "sam", notes: null });
  });

  it("thumbs-up goes straight through; thumbs-down asks why first", async () => {
    let ratings: object[] = [];
    const calls = mockApi({
      "GET /api/orders/7": () => ({ ...detail(), ratings }),
      "POST /api/orders/7/rating": (c) => { const b = c.body as { rater: string; rating: string; reason: string | null }; ratings = [b]; return ratings; },
    });
    renderAt("/orders/7");
    const up = (await screen.findByLabelText("Thumbs up")) as HTMLButtonElement;
    expect(up.disabled).toBe(true);  // needs a name
    fireEvent.change(screen.getByLabelText("Rating name"), { target: { value: "sam" } });
    await click(up);
    await waitFor(() => expect(screen.getByText(/👍 sam/)).toBeTruthy());
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ rater: "sam", rating: "up", reason: null });

    await click(screen.getByLabelText("Thumbs down"));
    const send = screen.getByText("Send to review") as HTMLButtonElement;
    expect(send.disabled).toBe(true);  // a reason is required
    fireEvent.change(screen.getByLabelText("What was wrong"), { target: { value: "wrong cassette" } });
    await click(send);
    await waitFor(() => expect(screen.getByText(/wrong cassette/)).toBeTruthy());
    expect(calls.filter((c) => c.method === "POST").at(-1)!.body).toEqual({ rater: "sam", rating: "down", reason: "wrong cassette" });
  });
});
