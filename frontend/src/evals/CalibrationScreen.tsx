import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Calibration } from "../api/client";
import { nice, problemsFrom } from "../ui";

type Item = Calibration["items"][number];
type Cell = { judge: string; split: string; justin: "pass" | "fail"; judged: "pass" | "fail" };

const fmt = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));
// Kappa: how much better than chance the judge agrees with Justin. Zero is no better than guessing.
const kappaTone = (k: number | null | undefined) => (k == null ? "text-muted" : k >= 0.6 ? "text-good" : k >= 0.2 ? "text-warn" : "text-sev-safety");

export default function CalibrationScreen() {
  const query = useQuery({
    queryKey: ["evals-calibration"],
    queryFn: async () => {
      const res = await api.GET("/api/evals/calibration");
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
  });
  const [version, setVersion] = useState("v3");
  const [cell, setCell] = useState<Cell | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  if (query.isError) return <p className="text-warn">{(query.error as Error).message}</p>;
  const cal = query.data;
  if (!cal) return <p className="text-muted">Loading…</p>;
  const rubric = cal.rubrics.find((r) => r.version === version) ?? cal.rubrics[0];
  const shown = cell
    ? cal.items.filter((i) => i.judge === cell.judge && i.split === cell.split && i.justin === cell.justin && i.verdicts[version].verdict === cell.judged)
    : [];

  return (
    <div className="flex flex-col gap-4">
      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-1">
        <h1 className="text-base font-bold">Judge calibration</h1>
        <p className="text-muted">
          Two LLM judges grade the agent's diagnosis and explanation. Before trusting them, Justin graded {cal.n_items} of their outputs pass/fail on a page that never
          showed the judge's verdict ({cal.justin_passed} passed, {cal.justin_failed} failed). The table says how often they agree. <b>Kappa</b> is agreement beyond
          chance (0 means no better than guessing); <b>TPR</b> is how often the judge passes what Justin passes; <b>TNR</b> how often it fails what he fails. With only{" "}
          {cal.justin_failed} fails, TNR and kappa rest on very few items.
        </p>
        <div className="flex gap-1 mt-1" role="tablist">
          {cal.rubrics.map((r) => (
            <button key={r.version} type="button" role="tab" aria-selected={r.version === version}
              className={`px-3 py-1 rounded-sm text-sm font-semibold border ${r.version === version ? "border-accent text-accent" : "border-line text-muted"}`}
              onClick={() => { setVersion(r.version); setCell(null); }}>{r.label}</button>
          ))}
        </div>
        {version === "v3" && <p className="text-muted text-xs">v3 was changed using only the dev split's disagreements; the held-out split is the honest number.</p>}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {rubric.judges.map((j) => (
          <section key={j.judge} className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-muted">{nice(j.judge)}</h2>
            {j.splits.map((s) => (
              <div key={s.split} className="flex flex-wrap items-start gap-4">
                <div className="min-w-44">
                  <p className="font-semibold">{s.split === "dev" ? "Dev split" : "Held-out split"} <span className="text-muted font-normal">(n={s.metrics.n})</span></p>
                  <dl className="grid grid-cols-[auto_auto] gap-x-3 text-sm">
                    <dt className="text-muted">Kappa</dt><dd className={`font-bold tabular-nums ${kappaTone(s.metrics.kappa)}`}>{fmt(s.metrics.kappa)}</dd>
                    <dt className="text-muted">Accuracy</dt><dd className="tabular-nums">{fmt(s.metrics.accuracy)}</dd>
                    <dt className="text-muted">TPR</dt><dd className="tabular-nums">{fmt(s.metrics.tpr)}</dd>
                    <dt className="text-muted">TNR</dt><dd className="tabular-nums">{fmt(s.metrics.tnr)}</dd>
                  </dl>
                </div>
                <Confusion judge={j.judge} split={s.split} c={s.confusion} selected={cell} onSelect={setCell} />
              </div>
            ))}
          </section>
        ))}
      </div>

      {cell ? (
        <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-muted">
            {nice(cell.judge)}, {cell.split}: Justin {cell.justin}ed, judge {cell.judged}ed ({shown.length})
          </h2>
          {shown.length === 0 && <p className="text-muted">No items in this cell.</p>}
          {shown.map((i) => <ItemRow key={i.id} item={i} version={version} open={open === i.id} onToggle={() => setOpen(open === i.id ? null : i.id)} />)}
        </section>
      ) : <p className="text-muted">Click a cell of a matrix to see the items in it, with the judge's reasoning beside Justin's.</p>}
    </div>
  );
}

function Confusion({ judge, split, c, selected, onSelect }: {
  judge: string; split: string; c: { pass_pass: number; pass_fail: number; fail_pass: number; fail_fail: number };
  selected: Cell | null; onSelect: (c: Cell | null) => void;
}) {
  const cells: { justin: "pass" | "fail"; judged: "pass" | "fail"; n: number; tone: string }[] = [
    { justin: "pass", judged: "pass", n: c.pass_pass, tone: "bg-sev-none/25" },
    { justin: "pass", judged: "fail", n: c.pass_fail, tone: "bg-warn/25" },
    { justin: "fail", judged: "pass", n: c.fail_pass, tone: "bg-sev-safety/35" },
    { justin: "fail", judged: "fail", n: c.fail_fail, tone: "bg-sev-none/25" },
  ];
  return (
    <table className="text-center text-sm" aria-label={`${nice(judge)} ${split} confusion matrix`}>
      <thead><tr><th className="px-1 text-xs text-muted font-normal">Justin ↓ judge →</th><th className="px-1 text-xs text-muted font-semibold">pass</th><th className="px-1 text-xs text-muted font-semibold">fail</th></tr></thead>
      <tbody>
        {(["pass", "fail"] as const).map((jus) => (
          <tr key={jus}>
            <th className="px-1 text-xs text-muted font-semibold text-left">{jus}</th>
            {cells.filter((x) => x.justin === jus).map((x) => {
              const chosen = selected && selected.judge === judge && selected.split === split && selected.justin === x.justin && selected.judged === x.judged;
              return (
                <td key={x.judged} className="p-0.5">
                  <button type="button" aria-label={`${nice(judge)} ${split}: Justin ${x.justin}, judge ${x.judged}: ${x.n}`} disabled={x.n === 0}
                    className={`w-14 py-2 rounded-sm font-bold tabular-nums ${x.tone} ${chosen ? "outline outline-2 outline-accent" : ""} disabled:opacity-40`}
                    onClick={() => onSelect(chosen ? null : { judge, split, justin: x.justin, judged: x.judged })}>{x.n}</button>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ItemRow({ item, version, open, onToggle }: { item: Item; version: string; open: boolean; onToggle: () => void }) {
  const v = item.verdicts[version];
  return (
    <div className="border border-line rounded-sm p-2 text-sm">
      <button type="button" className="w-full text-left flex flex-wrap items-baseline gap-2" onClick={onToggle} aria-expanded={open}>
        <span className="font-mono text-xs">{item.case}</span>
        <span className="text-muted text-xs">{nice(item.slice)}</span>
        <span className="ml-auto text-xs text-accent">{open ? "Hide" : "Show"} details</span>
      </button>
      <p className="mt-1"><b>Justin ({item.justin}):</b> {item.justin_reason || <span className="text-muted">no reason given</span>}</p>
      {open && (
        <div className="mt-2 flex flex-col gap-2">
          <p className="whitespace-pre-wrap"><b>Judge ({v.verdict}):</b> {v.comment}</p>
          <pre className="text-xs bg-field border border-line rounded-sm p-2 whitespace-pre-wrap overflow-x-auto">{JSON.stringify(item.intake, null, 1)}</pre>
          <pre className="text-xs bg-field border border-line rounded-sm p-2 whitespace-pre-wrap overflow-x-auto">{typeof item.output === "string" ? item.output : JSON.stringify(item.output, null, 1)}</pre>
        </div>
      )}
    </div>
  );
}
