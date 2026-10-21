import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
  render(<QueryClientProvider client={client}><IntakeScreen /></QueryClientProvider>);
}

async function fillOneRow(bikeSearch: string, pick: string) {
  fireEvent.change(screen.getByPlaceholderText(/Search the catalog/), { target: { value: bikeSearch } });
  fireEvent.click(await screen.findByText(pick));
  await screen.findByRole("option", { name: "Brake noise" });
  fireEvent.change(screen.getByLabelText("Complaint"), { target: { value: "brake_noise" } });
  fireEvent.change(screen.getByLabelText("Suspected area"), { target: { value: "brake_pads" } });
  fireEvent.change(screen.getByLabelText("Customer's words"), { target: { value: "Grinding and sparks" } });
}

const row = (severity: string) => ({ row_id: "r1", severity, likely_causes: ["Pads worn to the backing plate"],
  likely_area: "brake_pads", agrees_with_suspected_area: true, disagreement_reason: null,
  question_for_customer: "Does it still stop?", suggested_labor: ["BRAKE-PAD-INSTALL"],
  suggested_part_categories: ["brake_pads"], citations: [] });

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("IntakeScreen", () => {
  it("fills the row from the stream and turns red on a safety escalation", async () => {
    const calls = mockApi({ "/api/intakes": sse([
      ["accepted", { intake_id: "i1", run_id: "i1", previous: null, pii_redacted: { phone: 1 }, guardrail_flags: [] }],
      ["bike", { bike_id: "trek-slash", name: "2024 Trek Slash 9.8 XT Gen 6", note: "Catalog bike.", question: null }],
      ["row", row("safety_critical")],
      ["route", { outcome: "escalated", escalated: true, escalation_message: "DO NOT RIDE. Safety-critical issue on row r1.", questions: {} }],
      ["draft", { work_order_id: 42, estimate_total: "$55.00", unverified_parts: [], error: null }],
      ["done", { intake_id: "i1", outcome: "escalated", work_order_id: 42, awaiting_review: true }],
    ]) });
    renderScreen();
    await fillOneRow("slash", "2024 Trek Slash 9.8 XT Gen 6");
    await act(async () => { fireEvent.click(screen.getByText("Submit intake")); });

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "DO NOT RIDE. Safety-critical issue on row r1.");
    expect(screen.getByText("Safety-critical")).toBeTruthy();
    expect(screen.getByText(/Ask the customer: Does it still stop\?/)).toBeTruthy();
    expect(screen.getByText(/Draft work order #42/)).toBeTruthy();
    expect(screen.getByText(/Removed from the notes before triage: 1 phone/)).toBeTruthy();
    expect(calls[0].body).toMatchObject({ bike_id: "trek-slash",
      rows: [{ row_id: "r1", complaint: "brake_noise", suspected_area: "brake_pads", note: "Grinding and sparks" }] });
  });

  it("asks which bike when the free text is ambiguous, then re-runs with the answer", async () => {
    const calls = mockApi({
      "/api/intakes": sse([
        ["accepted", { intake_id: "i1", run_id: "i1", previous: null, pii_redacted: {}, guardrail_flags: [] }],
        ["route", { outcome: "needs_answers", escalated: false, escalation_message: null,
                    questions: { bike: "Which Trek Marlin 7: 2023 or 2025?" } }],
        ["done", { intake_id: "i1", outcome: "needs_answers", work_order_id: null, awaiting_review: false }],
      ]),
      "/api/intakes/i1/answers": sse([
        ["accepted", { intake_id: "i2", run_id: "i2", previous: "i1", pii_redacted: {}, guardrail_flags: [] }],
        ["row", row("needs_service")],
        ["done", { intake_id: "i2", outcome: "ready_to_draft", work_order_id: 7, awaiting_review: true }],
      ]),
    });
    renderScreen();
    fireEvent.click(screen.getByText("Not in the catalog"));
    fireEvent.change(screen.getByPlaceholderText(/Describe the bike/), { target: { value: "Trek Marlin 7" } });
    await screen.findByRole("option", { name: "Brake noise" });
    fireEvent.change(screen.getByLabelText("Complaint"), { target: { value: "brake_noise" } });
    fireEvent.change(screen.getByLabelText("Suspected area"), { target: { value: "brake_pads" } });
    await act(async () => { fireEvent.click(screen.getByText("Submit intake")); });

    expect(await screen.findByText("Which Trek Marlin 7: 2023 or 2025?")).toBeTruthy();
    const search = screen.getAllByPlaceholderText(/Search the catalog/).at(-1)!;
    fireEvent.change(search, { target: { value: "marlin" } });
    fireEvent.click(await screen.findByText("2023 Trek Marlin 7 Gen 3"));
    await act(async () => { fireEvent.click(screen.getByText("Re-run with this bike")); });

    await waitFor(() => expect(screen.getByText("Needs service")).toBeTruthy());
    expect(calls.map((c) => c.url)).toEqual(["/api/intakes", "/api/intakes/i1/answers"]);
    expect(calls[1].body).toEqual({ bike_id: "trek-marlin-2023" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
