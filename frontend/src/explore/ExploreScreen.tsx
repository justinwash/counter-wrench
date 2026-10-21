import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CompatView } from "../api/client";
import { field, nice, primary, problemsFrom } from "../ui";

const STATUS_TONE: Record<string, string> = {
  compatible: "border-good text-good",
  incompatible: "border-sev-safety text-sev-safety",
  unknown: "border-warn text-warn",
};

export default function ExploreScreen() {
  const [tab, setTab] = useState<"retrieval" | "compat">("retrieval");
  return (
    <div className="flex flex-col gap-4">
      <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-1">
        <h1 className="text-base font-bold">Explore the machinery</h1>
        <p className="text-muted">
          The parts of the system that aren't the language model, run live and free. <b>Retrieval</b> shows what the agent is handed for a query; <b>Compatibility</b> is the rules
          engine that decides whether a part fits, which the model can never override.
        </p>
        <div className="flex gap-1 mt-1" role="tablist">
          {([["retrieval", "Retrieval"], ["compat", "Compatibility"]] as const).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id}
              className={`px-3 py-1 rounded-sm text-sm font-semibold border ${tab === id ? "border-accent text-accent" : "border-line text-muted"}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
      </section>
      {tab === "retrieval" ? <Retrieval /> : <Compat />}
    </div>
  );
}

function Retrieval() {
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const result = useQuery({
    queryKey: ["explore-search", asked],
    enabled: asked !== "",
    queryFn: async () => {
      const res = await api.GET("/api/explore/search", { params: { query: { q: asked } } });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
  });
  const top = result.data?.[0]?.score ?? 1;
  return (
    <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) setAsked(text.trim()); }}>
        <input aria-label="Search query" className={`${field} flex-1`} placeholder="Try: chain skips under load, or: brake lever to the bar" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className={primary} disabled={!text.trim()}>Search</button>
      </form>
      {result.isError && <p role="alert" className="text-warn">{(result.error as Error).message}</p>}
      {result.isFetching && <p className="text-muted">Searching…</p>}
      {result.data?.length === 0 && <p className="text-muted">Nothing found.</p>}
      <ol className="flex flex-col gap-2">
        {result.data?.map((h, i) => (
          <li key={h.chunk_id} className="border border-line rounded-sm p-2">
            <div className="flex items-baseline gap-2">
              <span className="text-muted tabular-nums">#{i + 1}</span>
              <span className="font-semibold">{h.title}: {h.heading}</span>
              <span className="ml-auto font-mono text-xs text-muted">{h.chunk_id}</span>
            </div>
            <div className="h-1 bg-line rounded-sm my-1" aria-hidden><div className="h-1 bg-accent rounded-sm" style={{ width: `${Math.max(4, (h.score / top) * 100)}%` }} /></div>
            <p className="text-xs text-muted">score {h.score}</p>
            <p className="text-sm whitespace-pre-wrap line-clamp-4">{h.content}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Compat() {
  const bikes = useQuery({ queryKey: ["explore-bikes"], queryFn: async () => (await api.GET("/api/bikes")).data ?? [] });
  const parts = useQuery({ queryKey: ["explore-parts"], queryFn: async () => (await api.GET("/api/explore/parts")).data ?? [] });
  const [bike, setBike] = useState("");
  const [part, setPart] = useState("");
  const [width, setWidth] = useState("");
  const chosen = parts.data?.find((p) => p.part_id === part);
  const view = useQuery({
    queryKey: ["explore-compat", bike, part, width],
    enabled: bike !== "" && part !== "",
    queryFn: async () => {
      const res = await api.GET("/api/explore/compat", { params: { query: { bike_id: bike, part_id: part, tire_width_mm: width ? Number(width) : null } } });
      if (!res.data) throw new Error(problemsFrom(res.error).join(" "));
      return res.data;
    },
  });
  const categories = [...new Set((parts.data ?? []).map((p) => p.category))];
  return (
    <section className="bg-panel border border-line rounded-sm p-3 flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <select aria-label="Bike" className={`${field} bg-field`} value={bike} onChange={(e) => setBike(e.target.value)}>
          <option value="">Pick a bike…</option>
          {bikes.data?.map((b) => <option key={b.bike_id} value={b.bike_id}>{b.name}</option>)}
        </select>
        <select aria-label="Part" className={`${field} bg-field`} value={part} onChange={(e) => setPart(e.target.value)}>
          <option value="">Pick a part…</option>
          {categories.map((c) => (
            <optgroup key={c} label={nice(c)}>
              {parts.data?.filter((p) => p.category === c).map((p) => <option key={p.part_id} value={p.part_id}>{p.name}</option>)}
            </optgroup>
          ))}
        </select>
        {chosen?.category === "tube" && (
          <input aria-label="Installed tire width (mm)" className={`${field} w-48`} placeholder="Installed tire width, mm" inputMode="numeric" value={width} onChange={(e) => setWidth(e.target.value.replace(/\D/g, ""))} />
        )}
      </div>
      {view.isError && <p role="alert" className="text-warn">{(view.error as Error).message}</p>}
      {view.data && <Verdict view={view.data} />}
    </section>
  );
}

function Verdict({ view }: { view: CompatView }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="font-semibold">{view.part_name} on the {view.bike_name}</p>
      {view.results.map((r) => (
        <div key={r.position ?? "x"} className="border border-line rounded-sm p-2">
          <p className="flex items-center gap-2">
            <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-bold border ${STATUS_TONE[r.status]}`}>{r.status}</span>
            {r.position && <span className="text-muted">{r.position} wheel</span>}
            {r.requires_adapter && <span className="text-warn text-xs">needs: {r.requires_adapter}</span>}
          </p>
          <ul className="list-disc pl-5 mt-1">{r.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </div>
      ))}
      <div className="grid gap-3 md:grid-cols-2">
        <Specs title="Bike specs it compared" specs={view.bike_specs} />
        <Specs title="Part specs it compared" specs={view.part_specs} />
      </div>
    </div>
  );
}

function Specs({ title, specs }: { title: string; specs: Record<string, unknown> }) {
  return (
    <div>
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted mb-1">{title}</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-xs font-mono">
        {Object.entries(specs).filter(([, v]) => v !== null && typeof v !== "object").map(([k, v]) => (
          <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd>{String(v)}</dd></div>
        ))}
      </dl>
    </div>
  );
}
