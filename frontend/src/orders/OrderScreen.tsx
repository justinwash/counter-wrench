import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type LaborOption, type OrderDetail, type OrderLine, type PartFit, type Rating } from "../api/client";
import type { RowResult } from "../api/stream";
import { field, money, nice, primary, problemsFrom, secondary, SeverityBadge, StatusBadge, useRememberedName } from "../ui";

type Position = "front" | "rear" | null;
interface EditLine { key: string; kind: "labor" | "part"; id: string; name: string; qty: number; unit: number; position: Position; unverified: boolean }

const CATEGORIES = ["cassette", "chain", "rear_derailleur", "brake_pads", "rotor", "bottom_bracket", "tire", "tube"];

const toEdit = (l: OrderLine, i: number): EditLine => ({
  key: `${i}`, kind: l.labor_code ? "labor" : "part", id: (l.labor_code ?? l.part_id)!, name: l.name ?? "", qty: l.qty,
  unit: l.unit_price_cents, position: (l.position as Position) ?? null, unverified: l.unverified,
});

interface IntakeRow { row_id: string; complaint: string; suspected_area: string; note?: string | null }
interface StoredIntake { rows?: IntakeRow[]; answers?: Record<string, string>; general_notes?: string | null }

export default function OrderScreen() {
  const id = Number(useParams().id);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["order", id],
    queryFn: async () => {
      const res = await api.GET("/api/orders/{order_id}", { params: { path: { order_id: id } } });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
    staleTime: 0,
  });
  const [editing, setEditing] = useState<EditLine[] | null>(null);
  const [editProblems, setEditProblems] = useState<string[]>([]);
  const [name, setName] = useRememberedName("cw-reviewer");
  const [notes, setNotes] = useState("");
  const [decisionProblems, setDecisionProblems] = useState<string[]>([]);

  const decide = useMutation({
    mutationFn: async (decision: "approve" | "reject") => {
      const res = await api.POST("/api/orders/{order_id}/review", {
        params: { path: { order_id: id } },
        body: { decision, reviewer: name.trim(), notes: notes.trim() || null },
      });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
    },
    onSuccess: () => { setDecisionProblems([]); void client.invalidateQueries({ queryKey: ["order", id] }); void client.invalidateQueries({ queryKey: ["orders"] }); },
    onError: (e: Error) => setDecisionProblems([e.message]),
  });

  const detail = query.data;
  if (query.isError) return <p className="text-warn">Couldn't load order #{id}: {(query.error as Error).message}</p>;
  if (!detail) return <p className="text-muted">Loading…</p>;
  const { order, lines, triage, sources } = detail;
  const open = order.status === "awaiting_review";
  const intake = (order.intake ?? {}) as StoredIntake;
  const assessments = (triage?.assessments ?? {}) as unknown as Record<string, RowResult>;

  const refresh = (d: OrderDetail) => {
    client.setQueryData(["order", id], d);
    void client.invalidateQueries({ queryKey: ["orders"] });
  };

  async function saveLines() {
    if (!editing) return;
    const body = {
      editor: name.trim(),
      labor_lines: editing.filter((l) => l.kind === "labor").map((l) => ({ code: l.id, qty: l.qty })),
      part_lines: editing.filter((l) => l.kind === "part").map((l) => ({ part_id: l.id, qty: l.qty, position: l.position })),
    };
    const res = await api.PUT("/api/orders/{order_id}/lines", { params: { path: { order_id: id } }, body });
    if (res.data) { refresh(res.data); setEditing(null); setEditProblems([]); }
    else setEditProblems(problemsFrom(res.error));
  }

  const shown = editing ?? lines.map(toEdit);
  const total = shown.reduce((sum, l) => sum + l.qty * l.unit, 0);
  const critical = order.severity === "safety_critical";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/orders" className="text-accent underline text-sm">← Orders</Link>
        <h1 className="text-lg font-bold">Order #{order.id}</h1>
        <SeverityBadge severity={order.severity} /> <StatusBadge status={order.status} />
        <span className="text-muted">{order.bike_name ?? "Bike not identified"}</span>
        <span className="ml-auto flex gap-4 text-sm">
          {detail.draft_trace_url && (
            <a className="text-accent underline" href={detail.draft_trace_url} target="_blank" rel="noreferrer">
              Drafting trace ↗
            </a>
          )}
          {detail.trace_url && (
            <a className="text-accent underline" href={detail.trace_url} target="_blank" rel="noreferrer">
              {detail.draft_trace_url ? "Triage trace ↗" : "Open the trace in LangSmith ↗"}
            </a>
          )}
        </span>
      </div>

      {critical && open && (
        <div role="alert" className="bg-sev-safety text-white px-4 py-3 font-bold">
          {triage?.escalation_message ?? "Safety-critical: the customer was told not to ride the bike. Priority order."}
        </div>
      )}

      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-muted">What the customer said</h2>
        {(intake.rows ?? []).map((r) => {
          const a = assessments[r.row_id];
          return (
            <div key={r.row_id} className="border-t border-line first:border-0 pt-2 first:pt-0 flex flex-col gap-1">
              <p><span className="font-semibold">{nice(r.complaint)}</span> <span className="text-muted">· staff suspected {nice(r.suspected_area)}</span>
                {a && <> <SeverityBadge severity={a.severity} /></>}</p>
              {r.note && <p className="bg-ground rounded-sm px-2 py-1">“{r.note}”</p>}
              {intake.answers?.[r.row_id] && <p className="text-muted">Customer answered: <span className="text-ink">{intake.answers[r.row_id]}</span></p>}
              {a && <p>{a.likely_causes.slice(0, 3).join(" · ")}</p>}
              {a?.agrees_with_suspected_area === false && <p className="text-warn text-xs">Disagrees with staff: {a.disagreement_reason}</p>}
              {triage?.questions[r.row_id] && <p className="text-xs bg-ask-bg border border-ask-line px-1.5 py-1">Still to ask the customer: {triage.questions[r.row_id]}</p>}
            </div>
          );
        })}
        {intake.general_notes && <p className="text-muted">General notes: {intake.general_notes}</p>}
      </section>

      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-1">
        <h2 className="text-xs font-bold uppercase tracking-wider text-muted">What we told the customer</h2>
        <p>{order.customer_explanation}</p>
        {order.mechanic_notes && (<>
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted mt-2">Notes for the mechanic</h2>
          <p className="whitespace-pre-wrap">{order.mechanic_notes}</p>
        </>)}
      </section>

      <section className="bg-panel border border-line rounded-sm overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-ground text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-2 py-2">Line</th><th className="px-2 py-2 w-24">Qty</th>
              <th className="px-2 py-2 w-24 text-right">Each</th><th className="px-2 py-2 w-24 text-right">Total</th>
              <th className="px-2 py-2 min-w-64">Fit</th>{editing && <th className="px-2 py-2 w-8" aria-label="Remove"></th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((l, i) => {
              const original = lines.find((o) => (o.labor_code ?? o.part_id) === l.id && (o.position ?? null) === l.position);
              return (
                <tr key={l.key} className="border-t border-line align-top">
                  <td className="px-2 py-2">
                    <span className="font-semibold">{l.name}</span>{l.position && <span className="text-muted"> ({l.position})</span>}
                    <div className="font-mono text-xs text-muted">{l.id}</div>
                  </td>
                  <td className="px-2 py-2">
                    {editing ? (
                      <input aria-label={`Quantity for ${l.name}`} type="number" min={1} max={10} className={`${field} w-16`} value={l.qty}
                        onChange={(e) => setEditing(editing.map((x, j) => j === i ? { ...x, qty: Math.min(10, Math.max(1, Number(e.target.value) || 1)) } : x))} />
                    ) : l.qty}
                  </td>
                  <td className="px-2 py-2 text-right font-mono">{money(l.unit)}</td>
                  <td className="px-2 py-2 text-right font-mono">{money(l.qty * l.unit)}</td>
                  <td className="px-2 py-2 text-xs">
                    {l.unverified && <p className="text-warn font-semibold">Fit not confirmed: {original?.unverified_reason ?? "mechanic to confirm"}</p>}
                    {!l.unverified && original?.compat_reasons?.map((r) => <p key={r} className="text-good">{r}</p>)}
                  </td>
                  {editing && (
                    <td className="px-2 py-2">
                      <button type="button" aria-label={`Remove ${l.name}`} className="text-muted hover:text-sev-safety"
                        onClick={() => setEditing(editing.filter((_, j) => j !== i))}>×</button>
                    </td>
                  )}
                </tr>
              );
            })}
            {shown.length === 0 && <tr><td colSpan={6} className="px-2 py-4 text-muted text-center">No lines.</td></tr>}
          </tbody>
          <tfoot>
            <tr className="border-t border-line font-semibold">
              <td className="px-2 py-2" colSpan={3}>Estimate{order.edited_by && !editing ? <span className="ml-2 text-xs font-normal text-muted">edited by {order.edited_by}</span> : null}</td>
              <td className="px-2 py-2 text-right font-mono">{money(total)}</td><td colSpan={2}></td>
            </tr>
          </tfoot>
        </table>

        {open && !editing && (
          <div className="border-t border-line px-2 py-2">
            <button type="button" className={secondary} onClick={() => { setEditing(lines.map(toEdit)); setEditProblems([]); }}>Edit lines</button>
          </div>
        )}
        {editing && (
          <div className="border-t border-line px-2 py-2 flex flex-col gap-3">
            <AddLines orderId={id} onAdd={(l) => setEditing((cur) => (cur ? addOrBump(cur, l) : cur))} />
            {editProblems.length > 0 && (
              <ul role="alert" className="bg-alert-row border border-sev-safety px-3 py-2">
                {editProblems.map((p) => <li key={p}>{p}</li>)}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <input id="editor-name" aria-label="Your name" className={`${field} w-48`} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
              <button type="button" className={primary} disabled={!name.trim()} onClick={() => void saveLines()}>Save changes</button>
              <button type="button" className={secondary} onClick={() => { setEditing(null); setEditProblems([]); }}>Cancel</button>
              <span className="text-xs text-muted">Changes are checked for fit, prices and missing labor exactly like the agent's own drafts.</span>
            </div>
          </div>
        )}
      </section>

      {sources.length > 0 && (
        <section className="bg-panel border border-line rounded-sm p-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted mb-1">Shop knowledge it relied on</h2>
          <ul className="text-sm">{sources.map((s) => <li key={s.id}>{s.title}: {s.heading}</li>)}</ul>
        </section>
      )}

      <LiveScores orderId={id} />

      <Ratings orderId={id} ratings={detail.ratings ?? []} />

      {open && !editing && (
        <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted">Your decision</h2>
          <div className="flex flex-wrap items-center gap-2">
            <input id="reviewer-name" aria-label="Your name" className={`${field} w-48`} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
            <input id="review-notes" aria-label="Notes" className={`${field} flex-1 min-w-64`} placeholder="Notes (required to reject)" value={notes} onChange={(e) => setNotes(e.target.value)} />
            <button type="button" className={primary} disabled={!name.trim() || decide.isPending} onClick={() => decide.mutate("approve")}>Approve</button>
            <button type="button" className={secondary} disabled={!name.trim() || !notes.trim() || decide.isPending} onClick={() => decide.mutate("reject")}>Reject</button>
          </div>
          {decisionProblems.map((p) => <p key={p} role="alert" className="text-warn">{p}</p>)}
        </section>
      )}

      {!open && (
        <section className="bg-panel border border-line rounded-sm p-3">
          <StatusBadge status={order.status} /> {order.reviewed_by && <>by {order.reviewed_by}</>}
          {order.reviewed_at && <span className="text-muted"> · {new Date(order.reviewed_at).toLocaleString()}</span>}
          {order.status === "declined" && <p className="mt-1">{order.waiver_signed ? "Waiver of liability signed." : "No waiver needed."}</p>}
          {order.review_notes && <p className="mt-1 whitespace-pre-wrap">{order.review_notes}</p>}
        </section>
      )}
    </div>
  );
}

/** Every score LangSmith holds for this order's two runs: the live checks the app ran after each, the
 * judges, the mechanic's decision and the thumbs. Comes from LangSmith, so it can be unavailable. */
function LiveScores({ orderId }: { orderId: number }) {
  const scores = useQuery({
    queryKey: ["order-scores", orderId],
    retry: false,
    queryFn: async () => {
      const res = await api.GET("/api/orders/{order_id}/scores", { params: { path: { order_id: orderId } } });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
  });
  const [open, setOpen] = useState<string | null>(null);
  if (scores.isLoading) return null;
  const data = scores.data;
  if (!data?.available) {
    return <p className="text-muted text-xs">Live scores: {data?.reason ?? "unavailable right now."}</p>;
  }
  return (
    <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
      <h2 className="text-xs font-bold uppercase tracking-wider text-muted">How it scored, live</h2>
      <p className="text-muted text-xs">The same checks as the offline evals, run on this order after each stage. Click a score for the reasoning.</p>
      {data.runs.map((r) => (
        <div key={r.run_id}>
          <p className="font-semibold capitalize">{r.stage} run {r.scores.length === 0 && <span className="text-muted font-normal">(scores still arriving, or none)</span>}</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {r.scores.map((sc) => {
              const bad = sc.score !== null && sc.score < 1;
              const k = `${r.run_id}${sc.key}`;
              return (
                <button key={k} type="button" aria-label={`${sc.key} ${sc.score}`} onClick={() => setOpen(open === k ? null : k)}
                  className={`px-2 py-0.5 rounded-sm text-xs font-mono border ${bad ? "border-sev-safety text-sev-safety" : "border-line text-ink"} ${open === k ? "outline outline-1 outline-accent" : ""}`}>
                  {sc.key} {sc.score === null ? "–" : sc.score}
                </button>
              );
            })}
          </div>
          {r.scores.filter((sc) => open === `${r.run_id}${sc.key}`).map((sc) => (
            <p key={sc.key} className="text-sm mt-1 whitespace-pre-wrap border-l-2 border-line pl-2">{sc.comment || "No comment recorded."}</p>
          ))}
        </div>
      ))}
    </section>
  );
}

/** Anyone can say whether the agent did well. A thumbs-down needs a reason and goes to the failure
 * review; a thumbs-up makes the order a candidate for the golden set (nothing is auto-labeled). */
function Ratings({ orderId, ratings }: { orderId: number; ratings: Rating[] }) {
  const client = useQueryClient();
  const [name, setName] = useRememberedName("cw-reviewer");
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const mine = ratings.find((r) => r.rater === name.trim());

  const rate = useMutation({
    mutationFn: async (rating: "up" | "down") => {
      const res = await api.POST("/api/orders/{order_id}/rating", {
        params: { path: { order_id: orderId } },
        body: { rater: name.trim(), rating, reason: rating === "down" ? reason.trim() : null },
      });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
    onSuccess: (votes) => {
      setProblems([]); setAsking(false); setReason("");
      client.setQueryData(["order", orderId], (d: OrderDetail | undefined) => (d ? { ...d, ratings: votes } : d));
    },
    onError: (e: Error) => setProblems([e.message]),
  });
  const mark = (rating: "up" | "down") => (mine?.rating === rating ? "border-accent text-accent" : "");

  return (
    <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
      <h2 className="text-xs font-bold uppercase tracking-wider text-muted">Did the agent get it right?</h2>
      <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Rating name" className={`${field} w-48`} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
        <button type="button" aria-label="Thumbs up" className={`${secondary} ${mark("up")}`} disabled={!name.trim() || rate.isPending} onClick={() => rate.mutate("up")}>👍</button>
        <button type="button" aria-label="Thumbs down" className={`${secondary} ${mark("down")}`} disabled={!name.trim() || rate.isPending} onClick={() => setAsking(true)}>👎</button>
      </div>
      {asking && (
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label="What was wrong" className={`${field} flex-1 min-w-64`} placeholder="What was wrong? (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="button" className={primary} disabled={!reason.trim() || rate.isPending} onClick={() => rate.mutate("down")}>Send to review</button>
        </div>
      )}
      {problems.map((p) => <p key={p} role="alert" className="text-warn">{p}</p>)}
      {ratings.length > 0 && (
        <ul className="text-sm">
          {ratings.map((r) => <li key={r.rater}>{r.rating === "up" ? "👍" : "👎"} {r.rater}{r.reason && <span className="text-muted"> · {r.reason}</span>}</li>)}
        </ul>
      )}
    </section>
  );
}

function addOrBump(lines: EditLine[], add: EditLine): EditLine[] {
  const i = lines.findIndex((l) => l.kind === add.kind && l.id === add.id && l.position === add.position);
  if (i < 0) return [...lines, { ...add, key: `new-${Date.now()}-${lines.length}` }];
  return lines.map((l, j) => (j === i ? { ...l, qty: Math.min(10, l.qty + 1) } : l));
}

function AddLines({ orderId, onAdd }: { orderId: number; onAdd: (l: EditLine) => void }) {
  const [category, setCategory] = useState("");
  const menu = useQuery({
    queryKey: ["labor-menu"],
    queryFn: async () => (await api.GET("/api/labor-menu")).data ?? [],
    staleTime: Infinity,
  });
  const options = useQuery({
    queryKey: ["part-options", orderId, category],
    queryFn: async () => (await api.GET("/api/orders/{order_id}/part-options", {
      params: { path: { order_id: orderId }, query: { category } } })).data,
    enabled: category !== "",
  });
  const price = (p: PartFit) => Math.round(Number(p.price.replace("$", "")) * 100);
  const addPart = (p: PartFit, unverified: boolean) => onAdd({
    key: "", kind: "part", id: p.part_id, name: p.name, qty: 1, unit: price(p),
    position: (p.position as Position) ?? null, unverified,
  });
  const labor = menu.data ?? [];
  return (
    <div className="flex flex-wrap gap-4">
      <label className="flex flex-col gap-1 text-xs text-muted">Add labor
        <select aria-label="Add labor" className={`${field} w-72 text-ink`} value=""
          onChange={(e) => {
            const item = labor.find((m: LaborOption) => m.code === e.target.value);
            if (item) onAdd({ key: "", kind: "labor", id: item.code, name: item.name, qty: 1, unit: item.price_cents, position: null, unverified: false });
          }}>
          <option value="">Choose from the service menu…</option>
          {labor.map((m: LaborOption) => <option key={m.code} value={m.code}>{m.name} ({money(m.price_cents)})</option>)}
        </select>
      </label>
      <div className="flex flex-col gap-1 text-xs text-muted">
        <label className="flex flex-col gap-1">Add a part for this bike
          <select aria-label="Part category" className={`${field} w-72 text-ink`} value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Choose a type of part…</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{nice(c)}</option>)}
          </select>
        </label>
        {options.data?.error && <p className="text-warn max-w-96">{options.data.error}</p>}
        {options.data && !options.data.error && (
          <ul className="border border-line rounded-sm max-h-48 overflow-auto w-[28rem] max-w-full text-ink text-sm">
            {options.data.compatible.map((p) => (
              <li key={`${p.part_id}-${p.position}`}>
                <button type="button" className="w-full text-left px-2 py-1 hover:bg-ground" onClick={() => addPart(p, false)}>
                  {p.name}{p.position ? ` (${p.position})` : ""} <span className="text-muted">{p.price}</span>
                </button>
              </li>
            ))}
            {options.data.unverified.map((p) => (
              <li key={`${p.part_id}-${p.position}-u`}>
                <button type="button" className="w-full text-left px-2 py-1 hover:bg-ground" onClick={() => addPart(p, true)}>
                  {p.name}{p.position ? ` (${p.position})` : ""} <span className="text-muted">{p.price}</span>
                  <span className="text-warn"> · fit not confirmed</span>
                </button>
              </li>
            ))}
            {options.data.compatible.length + options.data.unverified.length === 0 && <li className="px-2 py-1 text-muted">Nothing in the catalog fits.</li>}
          </ul>
        )}
      </div>
    </div>
  );
}
