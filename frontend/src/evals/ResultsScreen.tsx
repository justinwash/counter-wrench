import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { SeverityBadge, nice } from "../ui";

// The snapshot is untyped JSON on the wire (evals/snapshot/results.json); these are the parts the page reads.
interface Stat { mean: number; spread: number; n: number }
interface Evaluator { is_safety: boolean; is_judge: boolean; slices: Record<string, Stat | null> }
interface Cell { expected: string; predicted: string; count: number; cases: { case: string; row: string; runs: number }[] }
interface Experiment {
  id: string; project: string; change: string; runs: number; partial?: boolean; rubric?: string; agent_model?: string | null; structured_method?: string;
  evaluators: Record<string, Evaluator>;
  confusion: { labels: string[]; cells: Cell[] };
  safety_misses: { case: string; reps: number; failed: Record<string, number> }[];
}
export interface Snapshot { generated_at: string; commit: string; note: string; slices: string[]; severities: string[]; experiments: Experiment[] }

const stat = (e: Evaluator, slice: string): Stat | null => e.slices[slice] ?? null;

/** A change from the baseline only counts when it is bigger than the run-to-run spread of either. */
export function verdict(base: Stat | null, now: Stat | null, higherIsBetter = true): "better" | "worse" | "noise" | null {
  if (!base || !now) return null;
  const delta = now.mean - base.mean;
  if (Math.abs(delta) <= Math.max(base.spread, now.spread, 0.005)) return "noise";
  return delta > 0 === higherIsBetter ? "better" : "worse";
}

const TONE = { better: "text-good", worse: "text-sev-safety", noise: "text-muted" };

export default function ResultsScreen() {
  const query = useQuery({
    queryKey: ["evals-results"],
    queryFn: async () => {
      const res = await fetch("/api/evals/results");
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `HTTP ${res.status}`);
      return (await res.json()) as Snapshot;
    },
  });
  const [slice, setSlice] = useState("all");
  const [expId, setExpId] = useState<string | null>(null);
  const [cell, setCell] = useState<Cell | null>(null);

  if (query.isError) return <p className="text-warn">{(query.error as Error).message}</p>;
  const snap = query.data;
  if (!snap) return <p className="text-muted">Loading…</p>;
  const [base] = snap.experiments;
  const exp = snap.experiments.find((e) => e.id === expId) ?? snap.experiments[snap.experiments.length - 1];
  const keys = Object.keys(base.evaluators).sort((a, b) => Number(base.evaluators[b].is_safety) - Number(base.evaluators[a].is_safety) || a.localeCompare(b));

  return (
    <div className="flex flex-col gap-4">
      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-1">
        <h1 className="text-base font-bold">Experiment results</h1>
        <p className="text-muted">
          {snap.experiments.length} experiments, each changing one thing (E-008 changes nothing: it repeats E-007 to show the noise), every one re-scored on today's labels so the columns compare. Each cell is the mean over all runs with the
          run-to-run spread after the ±. Against the baseline, <span className="text-good">green</span> or <span className="text-sev-safety">red</span> means
          the gap is larger than the spread; <span className="text-muted">grey</span> means it could be noise.
        </p>
        <p className="text-muted text-xs">{snap.note} Generated {new Date(snap.generated_at).toLocaleString()} at commit {snap.commit}.</p>
        <label className="text-xs text-muted mt-1">Slice{" "}
          <select aria-label="Slice" className="border border-line rounded-sm bg-field px-1.5 py-0.5 text-ink" value={slice} onChange={(e) => setSlice(e.target.value)}>
            <option value="all">All slices</option>
            {snap.slices.map((s) => <option key={s} value={s}>{nice(s)}</option>)}
          </select>
        </label>
      </section>

      <section className="bg-panel border border-line rounded-sm overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs text-muted uppercase tracking-wider">
              <th className="px-2 py-2">Evaluator</th>
              {snap.experiments.map((e) => (
                <th key={e.id} className="px-2 py-2" title={e.change}>
                  <button type="button" className={`font-bold uppercase ${exp.id === e.id ? "text-accent" : ""}`} onClick={() => { setExpId(e.id); setCell(null); }}>{e.id}</button>
                  {e.partial && <span className="block text-[10px] normal-case font-normal text-warn" title="Many runs errored; spreads aren't meaningful and nothing is colored">{e.runs}/186 runs</span>}
                  {e.rubric && e.rubric !== base.rubric && <span className="block text-[10px] normal-case font-normal text-warn" title="Scored by judge rubric v3; the baseline's judges used v2">judge {e.rubric}</span>}
                  {e.agent_model && !e.agent_model.includes("haiku") && <span className="block text-[10px] normal-case font-normal text-accent" title={e.agent_model}>{e.agent_model.split("/").pop()}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k} className="border-t border-line">
                <td className="px-2 py-1 font-mono text-xs">
                  {k}{base.evaluators[k].is_safety && <span className="ml-1 text-sev-safety" title="Safety evaluator">●</span>}
                  {base.evaluators[k].is_judge && <span className="ml-1 text-muted" title="LLM judge, rubric v2: see the Judges page">(judge)</span>}
                </td>
                {snap.experiments.map((e, i) => {
                  const now = e.evaluators[k] ? stat(e.evaluators[k], slice) : null;
                  // A judge scored with a different rubric than the baseline's can't be compared with it.
                  const comparable = !base.evaluators[k].is_judge || !e.rubric || e.rubric === base.rubric;
                  const v = i === 0 || !comparable || e.partial ? null : verdict(stat(base.evaluators[k], slice), now);
                  return (
                    <td key={e.id} className={`px-2 py-1 tabular-nums ${v ? TONE[v] : ""}`}>
                      {now ? <>{now.mean.toFixed(2)} {!e.partial && <span className="text-muted text-xs">±{now.spread.toFixed(2)}</span>}</> : "–"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-muted">Severity: what Justin labeled against what the agent said ({exp.id})</h2>
        <p className="text-muted">{exp.change}. {exp.runs} runs. Each count is a row of an intake in one run. Red cells are hazards the agent under-called; amber cells are escalations the labels don't call for.</p>
        <Matrix exp={exp} labels={snap.severities} selected={cell} onSelect={setCell} />
        {cell && (
          <div className="text-sm border border-line rounded-sm p-2">
            <p className="mb-1"><SeverityBadge severity={cell.expected} /> labeled, <SeverityBadge severity={cell.predicted} /> predicted:</p>
            <ul>{cell.cases.map((c) => <li key={c.case + c.row} className="font-mono text-xs">{c.case} ({c.row}) in {c.runs} of 3 runs</li>)}</ul>
          </div>
        )}
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted mt-2">Safety misses, by case</h3>
        {exp.safety_misses.length === 0 ? <p className="text-good">None.</p> : (
          <ul className="text-sm">{exp.safety_misses.map((m) => (
            <li key={m.case}><span className="font-mono text-xs">{m.case}</span>: {Object.entries(m.failed).map(([k, n]) => `${k} failed ${n}/${m.reps}`).join(", ")}</li>
          ))}</ul>
        )}
      </section>
    </div>
  );
}

function Matrix({ exp, labels, selected, onSelect }: { exp: Experiment; labels: string[]; selected: Cell | null; onSelect: (c: Cell | null) => void }) {
  const at = (e: string, p: string) => exp.confusion.cells.find((c) => c.expected === e && c.predicted === p);
  return (
    <div className="overflow-x-auto">
      <table className="text-center">
        <thead>
          <tr><th className="px-2 py-1 text-xs text-muted text-left">labeled ↓ / agent →</th>{labels.map((l) => <th key={l} className="px-2 py-1 text-xs text-muted font-semibold">{nice(l)}</th>)}</tr>
        </thead>
        <tbody>
          {labels.map((e, ei) => (
            <tr key={e}>
              <th className="px-2 py-1 text-xs text-muted text-left font-semibold">{nice(e)}</th>
              {labels.map((p, pi) => {
                const c = at(e, p);
                const tone = !c ? "" : ei === pi ? "bg-sev-none/20" : e === "safety_critical" ? "bg-sev-safety/40" : p === "safety_critical" ? "bg-warn/30" : "bg-line/60";
                return (
                  <td key={p} className="p-0.5">
                    {c ? (
                      <button type="button" aria-label={`${nice(e)} labeled, ${nice(p)} predicted: ${c.count}`}
                        className={`w-full min-w-16 py-1.5 rounded-sm font-bold tabular-nums ${tone} ${selected === c ? "outline outline-2 outline-accent" : ""}`} onClick={() => onSelect(selected === c ? null : c)}>
                        {c.count}
                      </button>
                    ) : <span className="block py-1.5 text-line">·</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
