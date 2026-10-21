import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type BikeCandidate } from "../api/client";

export type BikeChoice = { kind: "catalog"; bike: BikeCandidate } | { kind: "other"; text: string };

/** Search the catalog, or switch to free text for a bike that isn't in it. */
export default function BikePicker({ value, onChange, disabled }: {
  value: BikeChoice | null;
  onChange: (choice: BikeChoice | null) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);  // the full list shows on focus, so no bike knowledge is needed
  const bikes = useQuery({
    queryKey: ["bikes", query],
    queryFn: async () => (await api.GET("/api/bikes", { params: { query: { q: query } } })).data ?? [],
    enabled: value?.kind !== "other",
  });

  if (value?.kind === "catalog") {
    return (
      <div className="flex items-center gap-2">
        <span className="font-semibold">{value.bike.name}</span>
        <button type="button" disabled={disabled} className="text-accent text-sm underline"
          onClick={() => onChange(null)}>Change</button>
      </div>
    );
  }
  if (value?.kind === "other") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <input id="bike-freetext" className="border border-line rounded-sm px-2 py-1 w-80" disabled={disabled}
          placeholder="Describe the bike: make, model, year, color" value={value.text}
          onChange={(e) => onChange({ kind: "other", text: e.target.value })} />
        <button type="button" disabled={disabled} className="text-accent text-sm underline"
          onClick={() => onChange(null)}>Search the catalog instead</button>
      </div>
    );
  }
  return (
    // Close only when focus leaves the whole picker, so the list works by keyboard too.
    <div className="relative flex flex-col gap-1"
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false); }}>
      <div className="flex flex-wrap items-center gap-2">
        <input id="bike-search" className="border border-line rounded-sm px-2 py-1 w-80" disabled={disabled}
          placeholder="Search the catalog, or pick from the list" value={query}
          onFocus={() => setOpen(true)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }} />
        <button type="button" disabled={disabled} className="text-accent text-sm underline"
          onClick={() => onChange({ kind: "other", text: query })}>Not in the catalog</button>
      </div>
      {open && (
        // Floats over the page (absolute) instead of pushing everything below it down.
        <ul className="absolute top-full left-0 z-20 mt-1 border border-line rounded-sm bg-panel shadow-lg shadow-black/50 max-h-72 overflow-auto w-[28rem] max-w-[calc(100vw-2rem)]">
          {(bikes.data ?? []).map((b) => (
            <li key={b.bike_id}>
              <button type="button" className="w-full text-left px-2 py-1 hover:bg-ground"
                onClick={() => { onChange({ kind: "catalog", bike: b }); setQuery(""); setOpen(false); }}>
                {b.name}
              </button>
            </li>
          ))}
          {bikes.data?.length === 0 && <li className="px-2 py-1 text-muted">No catalog bike matches.</li>}
        </ul>
      )}
    </div>
  );
}
