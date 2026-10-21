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
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <input id="bike-search" className="border border-line rounded-sm px-2 py-1 w-80" disabled={disabled}
          placeholder="Search the catalog: Hightower, Marlin 2023…" value={query}
          onChange={(e) => setQuery(e.target.value)} />
        <button type="button" disabled={disabled} className="text-accent text-sm underline"
          onClick={() => onChange({ kind: "other", text: query })}>Not in the catalog</button>
      </div>
      {query.length > 0 && (
        <ul className="border border-line rounded-sm bg-panel max-h-56 overflow-auto w-[28rem]">
          {(bikes.data ?? []).slice(0, 12).map((b) => (
            <li key={b.bike_id}>
              <button type="button" className="w-full text-left px-2 py-1 hover:bg-ground"
                onClick={() => { onChange({ kind: "catalog", bike: b }); setQuery(""); }}>
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
