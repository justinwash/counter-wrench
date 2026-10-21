import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ExploreScreen from "../explore/ExploreScreen";
import OrderScreen from "../orders/OrderScreen";
import CalibrationScreen from "./CalibrationScreen";
import ResultsScreen, { verdict } from "./ResultsScreen";

function mockApi(handlers: Record<string, (url: URL) => unknown | Response>) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : null;
    const url = new URL(req ? req.url : String(input), "http://x");
    const method = req?.method ?? init?.method ?? "GET";
    const handler = handlers[`${method} ${url.pathname}`];
    if (!handler) return new Response("not mocked", { status: 500 });
    const out = handler(url);
    return out instanceof Response ? out : Response.json(out);
  }));
}

function renderAt(node: React.ReactNode, path = "/") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const click = async (el: HTMLElement) => { await act(async () => { fireEvent.click(el); }); };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const stat = (mean: number, spread = 0.02) => ({ mean, spread, n: 100 });
const severities = ["safety_critical", "needs_service", "needs_adjustment", "cosmetic", "no_action_needed"];
const snapshot = {
  generated_at: "2026-10-21T12:00:00+00:00", commit: "abc1234", note: "re-scored", slices: ["normal", "safety"], severities,
  experiments: ["E-001b", "E-002"].map((id, i) => ({
    id, project: `p${i}`, change: i ? "Safety list" : "Baseline", runs: 186,
    evaluators: {
      safety_escalated: { is_safety: true, is_judge: false, slices: { all: stat(i ? 0.9 : 0.7), normal: stat(1), safety: stat(0.5) } },
      line_coherence: { is_safety: false, is_judge: false, slices: { all: stat(0.91, 0.06), normal: stat(0.9, 0.06), safety: null } },
    },
    confusion: { labels: severities, cells: [
      { expected: "safety_critical", predicted: "safety_critical", count: 50, cases: [] },
      { expected: "safety_critical", predicted: "needs_service", count: 3, cases: [{ case: "c02-squeak", row: "r1", runs: 3 }] },
    ] },
    safety_misses: i ? [] : [{ case: "c02-squeak", reps: 3, failed: { safety_escalated: 3 } }],
  })),
};

describe("Results", () => {
  it("a change counts only when it is bigger than the spread", () => {
    expect(verdict(stat(0.7, 0.05), stat(0.9, 0.05))).toBe("better");
    expect(verdict(stat(0.9, 0.05), stat(0.7, 0.05))).toBe("worse");
    expect(verdict(stat(0.83, 0.06), stat(0.86, 0.02))).toBe("noise");
    expect(verdict(null, stat(1))).toBeNull();
  });

  it("shows every experiment, switches slice, and opens a confusion cell's cases", async () => {
    mockApi({ "GET /api/evals/results": () => snapshot });
    renderAt(<ResultsScreen />);
    expect(await screen.findByText("Experiment results")).toBeTruthy();
    const row = screen.getByText("safety_escalated").closest("tr")!;
    expect(within(row).getByText("0.70")).toBeTruthy();
    expect(within(row).getByText("0.90")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Slice"), { target: { value: "safety" } });
    expect(within(screen.getByText("safety_escalated").closest("tr")!).getAllByText("0.50").length).toBe(2);
    expect(screen.getAllByText("–").length).toBeGreaterThan(0);  // line_coherence has no safety slice

    await click(screen.getByLabelText("safety critical labeled, needs service predicted: 3"));
    expect(screen.getByText(/c02-squeak \(r1\) in 3 of 3 runs/)).toBeTruthy();
    await click(screen.getByText("E-001b", { selector: "button" }));
    expect(screen.getByText(/safety_escalated failed 3\/3/)).toBeTruthy();
  });

  it("says what is missing instead of failing blank", async () => {
    mockApi({ "GET /api/evals/results": () => new Response(JSON.stringify({ detail: "No results snapshot yet: run `make evals-snapshot`." }), { status: 404 }) });
    renderAt(<ResultsScreen />);
    expect((await screen.findByText(/make evals-snapshot/)).textContent).toContain("snapshot");
  });
});

const split = (name: string, kappa: number | null, c: [number, number, number, number]) => ({
  split: name, metrics: { n: c.reduce((a, b) => a + b), accuracy: 0.75, tpr: 0.8, tnr: 0.5, kappa },
  confusion: { pass_pass: c[0], pass_fail: c[1], fail_pass: c[2], fail_fail: c[3] },
});
const calibration = {
  experiment: "8d43b45", n_items: 2, justin_passed: 1, justin_failed: 1,
  rubrics: [
    { version: "v2", label: "Rubric v2", judges: [{ judge: "explanation_quality", splits: [split("dev", 0, [1, 0, 1, 0]), split("heldout", 0.1, [1, 0, 0, 1])] }] },
    { version: "v3", label: "Rubric v3", judges: [{ judge: "explanation_quality", splits: [split("dev", -0.2, [1, 0, 1, 0]), split("heldout", 0.6, [1, 0, 0, 1])] }] },
  ],
  items: [
    { id: "cal-01", judge: "explanation_quality", case: "e04-tube", slice: "edge", split: "dev", justin: "fail", justin_reason: "never says why", intake: { rows: [] }, output: "Plain text",
      verdicts: { v2: { verdict: "fail", comment: "v2 reasoning" }, v3: { verdict: "pass", comment: "v3 reasoning" } } },
    { id: "cal-02", judge: "explanation_quality", case: "n01", slice: "normal", split: "dev", justin: "pass", justin_reason: "fine", intake: { rows: [] }, output: "x",
      verdicts: { v2: { verdict: "pass", comment: "ok" }, v3: { verdict: "pass", comment: "ok" } } },
  ],
};

describe("Judge calibration", () => {
  it("shows kappa per split, and a cell lists the items with both graders' reasoning", async () => {
    mockApi({ "GET /api/evals/calibration": () => calibration });
    renderAt(<CalibrationScreen />);
    expect(await screen.findByText("Judge calibration")).toBeTruthy();
    expect(screen.getByText("-0.20")).toBeTruthy();  // v3 dev kappa, reported as it is
    expect(screen.getByText("0.60")).toBeTruthy();
    await click(screen.getByLabelText("explanation quality dev: Justin fail, judge pass: 1"));
    expect(screen.getByText("never says why")).toBeTruthy();
    expect(screen.queryByText("n01")).toBeNull();  // only the cell's item
    await click(screen.getByText("Show details"));
    expect(screen.getByText(/v3 reasoning/)).toBeTruthy();
    await click(screen.getByRole("tab", { name: "Rubric v2" }));
    expect(screen.queryByText("never says why")).toBeNull();  // v2 judged it fail: a different cell
    expect(screen.getByText(/Click a cell/)).toBeTruthy();
  });
});

describe("Explore", () => {
  it("shows ranked retrieval and the rules engine's reasons", async () => {
    mockApi({
      "GET /api/explore/search": (u) => (u.searchParams.get("q") === "skips" ? [{ chunk_id: "diag#skip", title: "Drivetrain", heading: "Skipping under load", content: "Worn cassette", score: 0.03 }] : []),
      "GET /api/bikes": () => [{ bike_id: "ht", name: "2024 Hightower" }],
      "GET /api/explore/parts": () => [{ part_id: "pg1210", category: "cassette", name: "SRAM PG-1210" }],
      "GET /api/explore/compat": () => ({ bike_id: "ht", bike_name: "2024 Hightower", part_id: "pg1210", part_name: "SRAM PG-1210", category: "cassette",
        bike_specs: { speeds: 12 }, part_specs: { speeds: 12 }, results: [{ part_id: "pg1210", status: "compatible", reasons: ["12 speed matches 12 speed."], position: null }] }),
    });
    renderAt(<ExploreScreen />);
    fireEvent.change(screen.getByLabelText("Search query"), { target: { value: "skips" } });
    await click(screen.getByText("Search"));
    expect(await screen.findByText("Drivetrain: Skipping under load")).toBeTruthy();

    await click(screen.getByRole("tab", { name: "Compatibility" }));
    fireEvent.change(await screen.findByLabelText("Bike"), { target: { value: "ht" } });
    await waitFor(() => expect((screen.getByLabelText("Part") as HTMLSelectElement).options.length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText("Part"), { target: { value: "pg1210" } });
    expect(await screen.findByText("12 speed matches 12 speed.")).toBeTruthy();
    expect(screen.getByText("compatible")).toBeTruthy();
  });
});

describe("Live scores on an order", () => {
  const order = {
    order: { id: 7, created_at: "2026-10-21T10:00:00Z", status: "awaiting_review", bike_id: "ht", bike_freetext: null, bike_name: "Hightower", severity: "needs_service",
      priority: false, customer_explanation: "x", mechanic_notes: null, citations: [], estimate_total_cents: 0, source: "counter", edited_by: null, edited_at: null,
      waiver_signed: false, reviewed_by: null, reviewed_at: null, review_notes: null, intake: { rows: [] } },
    lines: [], sources: [], triage: null, trace_url: null, draft_trace_url: null, ratings: [],
  };
  const open = (scores: unknown) => {
    mockApi({ "GET /api/orders/7": () => order, "GET /api/orders/7/scores": () => scores });
    renderAt(<Routes><Route path="/orders/:id" element={<OrderScreen />} /></Routes>, "/orders/7");
  };

  it("lists each run's scores, marks a failing one, and shows the reasoning on click", async () => {
    open({ available: true, runs: [{ stage: "drafting", run_id: "r", scores: [
      { key: "parts_all_compatible", score: 1, comment: null }, { key: "prices_match_catalog", score: 0, comment: "total off by $5" }] }] });
    expect(await screen.findByText("How it scored, live")).toBeTruthy();
    await click(screen.getByLabelText("prices_match_catalog 0"));
    expect(screen.getByText("total off by $5")).toBeTruthy();
  });

  it("says so when LangSmith isn't available, and the order still works", async () => {
    open({ available: false, reason: "Tracing is off in this deployment.", runs: [] });
    expect(await screen.findByText(/Tracing is off in this deployment/)).toBeTruthy();
    expect(screen.getByText("Did the agent get it right?")).toBeTruthy();
  });
});
