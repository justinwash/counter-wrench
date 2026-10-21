import { useQuery } from "@tanstack/react-query";
import { useReducer, useState } from "react";
import { api, type ComplaintOption, type IntakeForm } from "../api/client";
import { postStream, type RowResult, type Severity, type StreamEvent } from "../api/stream";
import BikePicker, { type BikeChoice } from "./BikePicker";
import { applyEvent, emptyRun, type RunState } from "./run";

interface Row { row_id: string; complaint: string; suspected_area: string; note: string; answer: string }

const SEVERITY: Record<Severity, { label: string; cls: string }> = {
  safety_critical: { label: "Safety-critical", cls: "bg-sev-safety" },
  needs_service: { label: "Needs service", cls: "bg-sev-service" },
  needs_adjustment: { label: "Needs adjustment", cls: "bg-sev-adjust" },
  cosmetic: { label: "Cosmetic", cls: "bg-sev-cosmetic" },
  no_action_needed: { label: "No action needed", cls: "bg-sev-none" },
};

const nice = (v: string) => v.replace(/_/g, " ");
const newRow = (n: number): Row => ({ row_id: `r${n}`, complaint: "", suspected_area: "", note: "", answer: "" });
const field = "border border-line rounded-sm px-2 py-1";
const primary = "bg-accent text-header font-semibold px-4 py-1.5 rounded-sm disabled:opacity-40";
const secondary = "border border-line font-semibold px-4 py-1.5 rounded-sm hover:border-muted disabled:opacity-40";

type Action =
  | { type: "start" } | { type: "busy" } | { type: "event"; event: StreamEvent }
  | { type: "fail"; message: string } | { type: "reset" };

function reduce(state: RunState, action: Action): RunState {
  if (action.type === "start") return { ...emptyRun, running: true };
  if (action.type === "busy") return { ...state, running: true, awaitingConfirmation: false, error: null };
  if (action.type === "reset") return emptyRun;
  if (action.type === "fail") return { ...state, running: false, error: action.message };
  return applyEvent(state, action.event);
}

export default function IntakeScreen() {
  const taxonomy = useQuery({
    queryKey: ["taxonomy"],
    queryFn: async () => (await api.GET("/api/taxonomy")).data ?? [],
  });
  const complaints = new Map((taxonomy.data ?? []).map((c: ComplaintOption) => [c.value, c]));

  const [bike, setBike] = useState<BikeChoice | null>(null);
  const [rows, setRows] = useState<Row[]>([newRow(1)]);
  const [generalNotes, setGeneralNotes] = useState("");
  const [triagedNotes, setTriagedNotes] = useState<Record<string, string>>({});
  // Earlier triage results per row, oldest first, with what changed before each re-triage.
  const [history, setHistory] = useState<Record<string, Earlier[]>>({});
  const [run, dispatch] = useReducer(reduce, emptyRun);
  const [answerBike, setAnswerBike] = useState<BikeChoice | null>(null);
  const [declining, setDeclining] = useState(false);
  const [staff, setStaff] = useState("");
  const [waiver, setWaiver] = useState(false);

  const started = run.intakeId !== null || run.running;  // the rows are fixed once triaged
  const confirming = run.awaitingConfirmation && !run.running;
  const escalated = run.escalationMessage !== null;
  const waitingOnBike = run.outcome === "needs_answers" && !!run.questions.bike && !run.running;
  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const ready = bike !== null && (bike.kind === "catalog" || bike.text.trim() !== "")
    && rows.every((r) => r.complaint && r.suspected_area);
  const answers = Object.fromEntries(rows.filter((r) => r.answer.trim()).map((r) => [r.row_id, r.answer.trim()]));
  const changedNotes = Object.fromEntries(
    rows.filter((r) => r.note.trim() !== (triagedNotes[r.row_id] ?? "")).map((r) => [r.row_id, r.note.trim() || null]));
  const revisable = Object.keys(answers).length > 0 || Object.keys(changedNotes).length > 0;

  async function stream(url: string, body?: unknown, keepResults = false) {
    dispatch({ type: keepResults ? "busy" : "start" });
    try {
      await postStream(url, body ?? {}, (event) => dispatch({ type: "event", event }));
    } catch (err) {
      dispatch({ type: "fail", message: (err as Error).message });
    }
  }

  function snapshotNotes() {
    setTriagedNotes(Object.fromEntries(rows.map((r) => [r.row_id, r.note.trim()])));
  }

  function submit() {
    const form = {
      ...(bike?.kind === "catalog" ? { bike_id: bike.bike.bike_id } : { bike_freetext: bike?.kind === "other" ? bike.text : "" }),
      rows: rows.map((r) => ({ row_id: r.row_id, complaint: r.complaint, suspected_area: r.suspected_area, note: r.note.trim() || null })),
      general_notes: generalNotes.trim() || null,
    } as IntakeForm;
    snapshotNotes();
    void stream("/api/intakes", form);
  }

  function retriage() {
    setHistory((h) => {
      const next = { ...h };
      for (const r of rows) {
        const result = run.rows[r.row_id];
        if (!result) continue;
        const noteChanged = r.note.trim() !== (triagedNotes[r.row_id] ?? "");
        next[r.row_id] = [...(h[r.row_id] ?? []), { result, answer: r.answer.trim() || null,
          note: noteChanged ? r.note.trim() : null }];
      }
      return next;
    });
    snapshotNotes();
    setRows((rs) => rs.map((r) => ({ ...r, answer: "" })));
    void stream(`/api/intakes/${run.intakeId}/revise`, { answers, notes: changedNotes });
  }

  function createWorkOrder() {
    void stream(`/api/intakes/${run.intakeId}/continue`, undefined, true);
  }

  function recordDecline() {
    setDeclining(false);
    void stream(`/api/intakes/${run.intakeId}/decline`, { staff: staff.trim(), waiver_signed: waiver }, true);
  }

  function answerTheBikeQuestion(choice: { bike_id: string } | { bike_unconfirmed: true }) {
    if (!run.intakeId) return;
    if ("bike_id" in choice && answerBike?.kind === "catalog") setBike(answerBike);
    setAnswerBike(null);
    void stream(`/api/intakes/${run.intakeId}/answers`, choice);
  }

  function startOver() {
    dispatch({ type: "reset" });
    setRows([newRow(1)]); setBike(null); setGeneralNotes(""); setTriagedNotes({}); setHistory({});
    setDeclining(false); setStaff(""); setWaiver(false);
  }

  return (
    <div className={`flex flex-col gap-3 ${escalated ? "outline-4 outline-sev-safety" : ""}`}>
      {escalated && (
        <div role="alert" className="bg-sev-safety text-white px-4 py-3 font-bold text-base">
          {run.escalationMessage}
        </div>
      )}

      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-muted">Bike</h2>
        <BikePicker value={bike} onChange={setBike} disabled={started} />
        {run.bike?.note && run.bike.note !== "Catalog bike." && <p className="text-sm text-muted">{run.bike.note}</p>}
      </section>

      <section className="bg-panel border border-line rounded-sm overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-ground text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-2 py-2 w-8">#</th>
              <th className="px-2 py-2 w-44">Complaint</th>
              <th className="px-2 py-2 w-44">Suspected area</th>
              <th className="px-2 py-2 min-w-56">Customer's words</th>
              <th className="px-2 py-2 w-36">Severity</th>
              <th className="px-2 py-2 min-w-64">Likely cause</th>
              <th className="px-2 py-2 min-w-48">Labor and parts</th>
              <th className="px-2 py-2 w-8" aria-label="Remove row"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const result = run.rows[r.row_id];
              const failed = run.failedRows[r.row_id];
              const areas = complaints.get(r.complaint)?.areas ?? [];
              return (
                <tr key={r.row_id} className={`border-t border-line align-top ${result?.severity === "safety_critical" ? "bg-alert-row" : ""}`}>
                  <td className="px-2 py-2 font-mono text-muted">{i + 1}</td>
                  <td className="px-2 py-2">
                    <select id={`complaint-${r.row_id}`} aria-label="Complaint" disabled={started}
                      className={`${field} w-full`} value={r.complaint}
                      onChange={(e) => update(i, { complaint: e.target.value, suspected_area: "" })}>
                      <option value="">Choose…</option>
                      {(taxonomy.data ?? []).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    <select id={`area-${r.row_id}`} aria-label="Suspected area" disabled={started || !r.complaint}
                      className={`${field} w-full`} value={r.suspected_area}
                      onChange={(e) => update(i, { suspected_area: e.target.value })}>
                      <option value="">Choose…</option>
                      {areas.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    <input id={`note-${r.row_id}`} aria-label="Customer's words" disabled={started && !confirming}
                      className={`${field} w-full`} value={r.note}
                      placeholder="What the customer said" onChange={(e) => update(i, { note: e.target.value })} />
                  </td>
                  <ResultCells result={result} failed={failed} pending={run.running && !result && !failed}
                    earlier={history[r.row_id] ?? []}
                    answer={confirming ? { value: r.answer, set: (v) => update(i, { answer: v }), id: `answer-${r.row_id}` } : null} />
                  <td className="px-2 py-2">
                    {rows.length > 1 && !started && (
                      <button type="button" aria-label={`Remove row ${i + 1}`} className="text-muted hover:text-sev-safety"
                        onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>×</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-2 py-2">
          {!started && (
            <button type="button" disabled={rows.length >= 10} className="text-accent text-sm font-semibold"
              onClick={() => setRows((rs) => [...rs, newRow(Math.max(0, ...rs.map((r) => Number(r.row_id.slice(1)))) + 1)])}>
              + Add row
            </button>
          )}
          <input id="general-notes" aria-label="General notes" disabled={started} value={generalNotes}
            onChange={(e) => setGeneralNotes(e.target.value)} placeholder="General notes (optional)"
            className={`${field} flex-1 min-w-64`} />
          {!started && (
            <button type="button" disabled={!ready} onClick={submit} className={primary}>Triage</button>
          )}
          {run.running && <span className="text-muted font-semibold">Working…</span>}
          {started && !run.running && (
            <button type="button" className="text-sm underline text-muted" onClick={startOver}>Start a new intake</button>
          )}
        </div>
      </section>

      <RunNotices run={run} />

      {confirming && (
        <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-3">
          <p className="text-sm text-muted">
            Check the triage with the customer. Answer any questions or fix the notes and re-triage, or create the work order for the mechanic.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={secondary} disabled={!revisable} onClick={retriage}>Re-triage with changes</button>
            <button type="button" className={primary} onClick={createWorkOrder}>Create work order</button>
            <button type="button" className={`${secondary} ml-auto`} onClick={() => setDeclining((d) => !d)}>Customer declined…</button>
          </div>
          {declining && (
            <div className="border border-line rounded-sm p-3 flex flex-col gap-2">
              <p className="font-semibold">Record that the customer declined the work and release the bike.</p>
              {escalated && (
                <label className="flex items-center gap-2 text-warn">
                  <input id="waiver" type="checkbox" checked={waiver} onChange={(e) => setWaiver(e.target.checked)} />
                  The customer signed the waiver of liability (required: this bike is unsafe to ride).
                </label>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <input id="decline-staff" aria-label="Your name" className={`${field} w-56`} placeholder="Your name"
                  value={staff} onChange={(e) => setStaff(e.target.value)} />
                <button type="button" className={primary} disabled={!staff.trim() || (escalated && !waiver)} onClick={recordDecline}>
                  Record decline and release the bike
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {waitingOnBike && (
        <section className="bg-panel border-2 border-sev-service rounded-sm p-3 flex flex-col gap-2">
          <p className="font-semibold">{run.questions.bike}</p>
          <BikePicker value={answerBike} onChange={setAnswerBike} />
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={answerBike?.kind !== "catalog"} className={primary}
              onClick={() => answerBike?.kind === "catalog" && answerTheBikeQuestion({ bike_id: answerBike.bike.bike_id })}>
              Re-run with this bike
            </button>
            <button type="button" className={secondary} onClick={() => answerTheBikeQuestion({ bike_unconfirmed: true })}>
              Customer doesn't know: draft without a confirmed bike
            </button>
          </div>
          <p className="text-xs text-muted">Without a confirmed bike, the work order quotes labor only; the mechanic identifies the bike, confirms part fitment and calls the customer.</p>
        </section>
      )}

      {run.draft && (
        <section className="bg-panel border border-line rounded-sm p-3">
          {run.draft.work_order_id ? (
            <p>
              <span className="font-semibold">Work order #{run.draft.work_order_id}</span> saved for mechanic review.
              Estimate <span className="font-mono">{run.draft.estimate_total}</span>
              {run.draft.unverified_parts.length > 0 && (
                <span className="text-warn"> · fit to confirm: {run.draft.unverified_parts.join(", ")}</span>
              )}
            </p>
          ) : (
            <p className="text-warn">{run.draft.error}</p>
          )}
        </section>
      )}

      {run.outcome === "declined" && !run.running && (
        <section className="bg-panel border border-line rounded-sm p-3">
          <p><span className="font-semibold">Declined.</span> Record #{run.workOrderId} kept; the bike is released, no further action.</p>
        </section>
      )}
    </div>
  );
}

interface Earlier { result: RowResult; answer: string | null; note: string | null }

function EarlierTriage({ earlier }: { earlier: Earlier[] }) {
  if (!earlier.length) return null;
  return (
    <ol className="mt-2 border-t border-line pt-1 flex flex-col gap-1 text-xs text-muted" aria-label="Earlier triage">
      {earlier.map((e, i) => (
        <li key={i}>
          <span className="font-semibold">Before re-triage {i + 1}:</span> {SEVERITY[e.result.severity].label}: {e.result.likely_causes[0]}
          {e.result.question_for_customer && <> · Asked: {e.result.question_for_customer}</>}
          {e.answer && <> · Answer: <span className="text-ink">{e.answer}</span></>}
          {e.note && <> · Note changed to: <span className="text-ink">{e.note}</span></>}
        </li>
      ))}
    </ol>
  );
}

function ResultCells({ result, failed, pending, answer, earlier }: {
  result?: RowResult; failed?: string; pending: boolean; earlier: Earlier[];
  answer: { value: string; set: (v: string) => void; id: string } | null;
}) {
  if (failed) return <td colSpan={3} className="px-2 py-2 text-warn">Couldn't assess this row; a mechanic will check it.</td>;
  if (!result) return (
    <td colSpan={3} className="px-2 py-2 text-muted">{pending ? "Triaging…" : ""}<EarlierTriage earlier={earlier} /></td>
  );
  const sev = SEVERITY[result.severity];
  const agree = result.agrees_with_suspected_area;
  return (
    <>
      <td className="px-2 py-2">
        <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-bold text-white ${sev.cls}`}>{sev.label}</span>
      </td>
      <td className="px-2 py-2">
        <p>{result.likely_causes[0]}</p>
        {agree === false && (
          <p className="text-warn text-xs mt-1">
            Not the {result.likely_area ? `staff pick: looks like ${nice(result.likely_area)}` : "area staff picked"}. {result.disagreement_reason}
          </p>
        )}
        {agree === true && <p className="text-good text-xs mt-1">Agrees with the area staff picked.</p>}
        <EarlierTriage earlier={earlier} />
        {result.question_for_customer && (
          <div className="text-xs mt-1 bg-ask-bg border border-ask-line px-1.5 py-1 flex flex-col gap-1">
            <span>Ask the customer: {result.question_for_customer}</span>
            {answer && (
              <input id={answer.id} aria-label="Customer's answer" className="border border-line rounded-sm px-1.5 py-0.5"
                placeholder="Their answer" value={answer.value} onChange={(e) => answer.set(e.target.value)} />
            )}
          </div>
        )}
      </td>
      <td className="px-2 py-2 font-mono text-xs">
        {result.suggested_labor.join(", ") || "—"}
        {result.suggested_part_categories.length > 0 && (
          <div className="text-muted">parts: {result.suggested_part_categories.map(nice).join(", ")}</div>
        )}
      </td>
    </>
  );
}

function RunNotices({ run }: { run: RunState }) {
  const redacted = Object.entries(run.redacted);
  if (!run.error && !redacted.length && !run.flags.length) return null;
  return (
    <section className="flex flex-col gap-1 text-sm">
      {run.error && <p className="bg-alert-row border border-sev-safety px-3 py-2">Something went wrong: {run.error}</p>}
      {redacted.length > 0 && (
        <p className="text-muted">Removed from the notes before triage: {redacted.map(([k, n]) => `${n} ${k}`).join(", ")}.</p>
      )}
      {run.flags.length > 0 && (
        <p className="text-warn">Flagged for the mechanic: {run.flags.map(nice).join(", ")}.</p>
      )}
    </section>
  );
}
