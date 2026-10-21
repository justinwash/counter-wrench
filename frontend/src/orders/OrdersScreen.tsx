import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { money, SeverityBadge, StatusBadge } from "../ui";

const TABS: [string, string][] = [
  ["awaiting_review", "Review queue"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
  ["declined", "Declined"],
  ["", "All"],
];

const ago = (iso: string) => {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 1440)} d ago`;
};

export default function OrdersScreen() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "awaiting_review";
  const orders = useQuery({
    queryKey: ["orders", status],
    queryFn: async () =>
      (await api.GET("/api/orders", { params: { query: status ? { status } : {} } })).data ?? [],
    staleTime: 0,
    refetchInterval: 10_000,  // a new draft shows up without anyone reloading
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1" role="tablist">
        {TABS.map(([value, label]) => (
          <button key={label} type="button" role="tab" aria-selected={status === value}
            className={`px-3 py-1.5 rounded-sm text-sm font-semibold border ${status === value ? "bg-panel border-line text-ink" : "border-transparent text-muted hover:text-ink"}`}
            onClick={() => setParams(value === "awaiting_review" ? {} : { status: value })}>
            {label}
          </button>
        ))}
      </div>

      <section className="bg-panel border border-line rounded-sm overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-ground text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-2 py-2 w-20">Order</th>
              <th className="px-2 py-2 w-40">Severity</th>
              <th className="px-2 py-2">Bike</th>
              <th className="px-2 py-2 w-44">Status</th>
              <th className="px-2 py-2 w-24 text-right">Estimate</th>
              <th className="px-2 py-2 w-28">Opened</th>
            </tr>
          </thead>
          <tbody>
            {(orders.data ?? []).map((o) => (
              <tr key={o.id} className={`border-t border-line ${o.priority && o.status === "awaiting_review" ? "bg-alert-row" : ""}`}>
                <td className="px-2 py-2 font-mono">
                  <Link className="text-accent underline" to={`/orders/${o.id}`}>#{o.id}</Link>
                </td>
                <td className="px-2 py-2"><SeverityBadge severity={o.severity} /></td>
                <td className="px-2 py-2">{o.bike}</td>
                <td className="px-2 py-2"><StatusBadge status={o.status} />{o.edited && <span className="ml-2 text-xs text-muted">edited</span>}</td>
                <td className="px-2 py-2 text-right font-mono">{money(o.estimate_total_cents)}</td>
                <td className="px-2 py-2 text-muted">{ago(o.created_at)}</td>
              </tr>
            ))}
            {orders.data?.length === 0 && (
              <tr><td colSpan={6} className="px-2 py-6 text-center text-muted">
                {status === "awaiting_review" ? "Nothing waiting for review." : "No orders here yet."}
              </td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
