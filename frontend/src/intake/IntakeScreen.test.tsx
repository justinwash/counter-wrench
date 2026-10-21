import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import IntakeScreen from "./IntakeScreen";

const taxonomy = [{ value: "brake_noise", label: "Brake noise",
  areas: [{ value: "brake_pads", label: "Brake pads" }, { value: "unsure", label: "Unsure" }] }];
const bikes = [{ bike_id: "trek-slash", name: "2024 Trek Slash 9.8 XT Gen 6" },
               { bike_id: "trek-marlin-2023", name: "2023 Trek Marlin 7 Gen 3" }];

const sse = (events: [string, object][]) =>
  events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");

function streamResponse(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({
    start(c) { c.enqueue(bytes.slice(0, 40)); c.enqueue(bytes.slice(40)); c.close(); }, // split mid-event
  }), { status: 200 });
}

function mockApi(streams: Record<string, string>) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("/api/taxonomy")) return Response.json(taxonomy);
    if (url.includes("/api/bikes")) return Response.json(bikes);
    calls.push({ url, body: init?.body ? JSON.parse(init.body as string) : null });
    const key = Object.keys(streams).find((k) => url.endsWith(k));
    return streamResponse(streams[key!]);
  }));
  return calls;
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><IntakeScreen /></MemoryRouter></QueryClientProvider>);
}

async function fillOneRow() {
  fireEvent.focus(screen.getByPlaceholderText(/Search the catalog/));  // the whole list, no typing
  expect(await screen.findByText("2023 Trek Marlin 7 Gen 3")).toBeTruthy();
  fireEvent.click(await screen.findByText("2024 Trek Slash 9.8 XT Gen 6"));
  await screen.findByRole("option", { name: "Brake noise" });
  fireEvent.change(screen.getByLabelText("Complaint"), { target: { value: "brake_noise" } });
  fireEvent.change(screen.getByLabelText("Suspected area"), { target: { value: "brake_pads" } });
  fireEvent.change(screen.getByLabelText("Customer's words"), { target: { value: "Grinding and sparks" } });
}

const click = async (text: string) => { await act(async () => { fireEvent.click(screen.getByText(text)); }); };

const row = (severity: string, question: string | null = "Does it still stop?") => ({
  row_id: "r1", severity, likely_causes: ["Pads worn to the backing plate"], likely_area: "brake_pads",
  agrees_with_suspected_area: true, disagreement_reason: null, question_for_customer: question,
  suggested_labor: ["BRAKE-PAD-INSTALL"], suggested_part_categories: ["brake_pads"], citations: [] });

const triage = (id: string, severity: string, extra: [string, object][] = []) => sse([
  ["accepted", { intake_id: id, run_id: id, previous: null, pii_redacted: { phone: 1 }, guardrail_flags: [] }],
  ["bike", { bike_id: "trek-slash", name: "2024 Trek Slash 9.8 XT Gen 6", note: "Catalog bike.", question: null }],
  ["row", row(severity)],
  ...extra,
  ["triaged", { stage: "confirm" }],
  ["done", { intake_id: id, outcome: "ready_to_draft", work_order_id: null, awaiting_confirmation: true, awaiting_review: false }],
]);
const escalation: [string, object][] = [["route", { outcome: "escalated", escalated: true,
  escalation_message: "DO NOT RIDE. Safety-critical issue on row r1.", questions: { r1: "Does it still stop?" } }]];

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("IntakeScreen", () => {
  it("triages, turns red on a safety escalation, then creates the work order", async () => {
    const calls = mockApi({
      "/api/intakes": triage("i1", "safety_critical", escalation),
      "/api/intakes/i1/continue": sse([
        ["draft", { work_order_id: 42, estimate_total: "$55.00", unverified_parts: [], error: null }],
        ["done", { intake_id: "i1", outcome: "escalated", work_order_id: 42, awaiting_confirmation: false, awaiting_review: true }],
      ]),
    });
    renderScreen();
    await fillOneRow();
    await click("Triage");

    expect((await screen.findByRole("alert")).textContent).toBe("DO NOT RIDE. Safety-critical issue on row r1.");
    expect(screen.getByText("Safety-critical")).toBeTruthy();
    expect(screen.getByText(/Removed from the notes before triage: 1 phone/)).toBeTruthy();
    expect(screen.queryByText(/Work order #/)).toBeNull();  // nothing drafted yet
    await click("Create work order");
    expect(await screen.findByText(/Work order #42/)).toBeTruthy();
    expect(screen.getByText("Safety-critical")).toBeTruthy();  // the triage stays on screen
    expect(calls.map((c) => c.url)).toEqual(["/api/intakes", "/api/intakes/i1/continue"]);
    expect(calls[0].body).toMatchObject({ bike_id: "trek-slash",
      rows: [{ row_id: "r1", complaint: "brake_noise", suspected_area: "brake_pads", note: "Grinding and sparks" }] });
  });

  it("re-triages with the customer's answer and a corrected note", async () => {
    const calls = mockApi({
      "/api/intakes": triage("i1", "needs_service"),
      "/api/intakes/i1/revise": triage("i2", "needs_adjustment"),
    });
    renderScreen();
    await fillOneRow();
    await click("Triage");
    const reTriage = await screen.findByText("Re-triage with changes");
    expect((reTriage as HTMLButtonElement).disabled).toBe(true);  // nothing changed yet
    fireEvent.change(screen.getByLabelText("Customer's answer"), { target: { value: "Yes, but it's weak" } });
    fireEvent.change(screen.getByLabelText("Customer's words"), { target: { value: "Grinding, no sparks" } });
    await click("Re-triage with changes");

    await waitFor(() => expect(screen.getByText("Needs adjustment")).toBeTruthy());
    const earlier = screen.getByLabelText("Earlier triage").textContent ?? "";
    expect(earlier).toContain("Needs service: Pads worn to the backing plate");
    expect(earlier).toContain("Answer: Yes, but it's weak");
    expect(earlier).toContain("Note changed to: Grinding, no sparks");
    expect(calls[1]).toEqual({ url: "/api/intakes/i1/revise",
      body: { answers: { r1: "Yes, but it's weak" }, notes: { r1: "Grinding, no sparks" } } });
  });

  it("records a declined safety-critical job only with a signed waiver", async () => {
    const calls = mockApi({
      "/api/intakes": triage("i1", "safety_critical", escalation),
      "/api/intakes/i1/decline": sse([["done", { intake_id: "i1", outcome: "declined", work_order_id: 9,
        awaiting_confirmation: false, awaiting_review: false }]]),
    });
    renderScreen();
    await fillOneRow();
    await click("Triage");
    await click("Customer declined…");
    const record = screen.getByText("Record decline and release the bike") as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Sam" } });
    expect(record.disabled).toBe(true);  // no waiver yet
    fireEvent.click(screen.getByLabelText(/signed the waiver/));
    expect(record.disabled).toBe(false);
    await click("Record decline and release the bike");

    expect(await screen.findByText(/Record #9 kept; the bike is released/)).toBeTruthy();
    expect(calls[1]).toEqual({ url: "/api/intakes/i1/decline", body: { staff: "Sam", waiver_signed: true } });
  });

  it("says so when triage stops asking after two rounds, instead of looping", async () => {
    mockApi({ "/api/intakes": triage("i1", "needs_service", [["row_unresolved", { row_id: "r1", question: "Does it squeal on dry days too?" }]]) });
    renderScreen();
    await fillOneRow();
    await click("Triage");
    expect(await screen.findByText(/Still unclear after two rounds of questions, so no more/)).toBeTruthy();
    expect(screen.getByText(/Does it squeal on dry days too\?/)).toBeTruthy();
  });

  it("carries on without a confirmed bike when the customer doesn't know the year", async () => {
    const calls = mockApi({
      "/api/intakes": sse([
        ["accepted", { intake_id: "i1", run_id: "i1", previous: null, pii_redacted: {}, guardrail_flags: [] }],
        ["route", { outcome: "needs_answers", escalated: false, escalation_message: null,
                    questions: { bike: "Which bike is it: 2023 or 2025 Trek Marlin 7?" } }],
        ["done", { intake_id: "i1", outcome: "needs_answers", work_order_id: null, awaiting_confirmation: false, awaiting_review: false }],
      ]),
      "/api/intakes/i1/answers": triage("i2", "needs_service"),
    });
    renderScreen();
    fireEvent.click(screen.getByText("Not in the catalog"));
    fireEvent.change(screen.getByPlaceholderText(/Describe the bike/), { target: { value: "Trek Marlin 7" } });
    await screen.findByRole("option", { name: "Brake noise" });
    fireEvent.change(screen.getByLabelText("Complaint"), { target: { value: "brake_noise" } });
    fireEvent.change(screen.getByLabelText("Suspected area"), { target: { value: "brake_pads" } });
    await click("Triage");

    expect(await screen.findByText("Which bike is it: 2023 or 2025 Trek Marlin 7?")).toBeTruthy();
    await click("Customer doesn't know: draft without a confirmed bike");
    await waitFor(() => expect(screen.getByText("Needs service")).toBeTruthy());
    expect(calls[1]).toEqual({ url: "/api/intakes/i1/answers", body: { bike_unconfirmed: true } });
  });
});
