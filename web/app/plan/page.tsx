"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ExplainPanel from "@/components/ExplainPanel";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import type { PlanRun, StoreLine, Summary } from "@/lib/types";

const PAGE = 25;
const n = (x: number, d = 1) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: d });

type Filters = { status: string; city: string; stockout: string; expiring: boolean; undecided: boolean; sort: string };
const INITIAL: Filters = { status: "", city: "", stockout: "", expiring: false, undecided: false, sort: "order_qty" };
const BADGE: Record<string, string> = {
  order: "bg-blue-100 text-blue-900",
  "warehouse short": "bg-amber-100 text-amber-900",
  hold: "bg-slate-200 text-slate-800",
};

export default function PlanPage() {
  const router = useRouter();
  const [run, setRun] = useState<PlanRun | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<StoreLine[]>([]);
  const [f, setF] = useState<Filters>(INITIAL);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [explainLine, setExplainLine] = useState<StoreLine | null>(null);
  const [editing, setEditing] = useState<{ id: number; value: string } | null>(null);

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { setToken(null); router.replace("/login"); return; }
    setError(e instanceof Error ? e.message : "Something went wrong");
  }, [router]);

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    api<PlanRun[]>("/plans").then((p) => setRun(p[0] ?? null)).catch(fail);
  }, [router, fail]);

  const loadSummary = useCallback(() => {
    if (!run) return;
    api<Summary>(`/plans/${run.id}/summary`).then(setSummary).catch(fail);
  }, [run, fail]);
  useEffect(() => { loadSummary(); }, [loadSummary]);

  const loadRows = useCallback(() => {
    if (!run) return;
    const q = new URLSearchParams({ sort: f.sort, limit: String(PAGE), offset: String(offset) });
    if (f.status) q.set("status", f.status);
    if (f.city) q.set("city_id", f.city);
    if (f.stockout) q.set("stockout", f.stockout);
    if (f.expiring) q.set("expiring", "true");
    if (f.undecided) q.set("undecided", "true");
    setLoading(true);
    api<StoreLine[]>(`/plans/${run.id}/store-lines?${q}`)
      .then((r) => { setRows(r); setError(""); })
      .catch(fail)
      .finally(() => setLoading(false));
  }, [run, f, offset, fail]);
  useEffect(() => { loadRows(); }, [loadRows]);

  function change<K extends keyof Filters>(key: K, value: Filters[K]) {
    setF((prev) => ({ ...prev, [key]: value })); setOffset(0);
  }

  async function decide(line: StoreLine, action: "approve" | "edit" | "reject", qty?: number) {
    const body: Record<string, unknown> = { action };
    if (action === "edit") body.final_qty = qty;
    try {
      await api(`/store-lines/${line.id}/decision`, { method: "POST", body: JSON.stringify(body) });
      setEditing(null); setError(""); loadRows(); loadSummary();
    } catch (e) { fail(e); }
  }

  const cards: [string, string][] = summary ? [
    ["Lines", n(summary.lines, 0)], ["To order", n(summary.orders, 0)],
    ["Warehouse short", n(summary.warehouse_short, 0)], ["Hold", n(summary.holds, 0)],
    ["Stockout likely", n(summary.stockout_likely, 0)], ["Expiring units", n(summary.expiring_units, 0)],
    ["Decided", n(summary.decided_lines, 0)],
  ] : [];

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Perishables Network Planner</h1>
          {run && <p className="text-sm text-slate-600">
            Plan for {run.plan_date} · shelf life {run.shelf_life_days} days · κ {run.kappa}
          </p>}
        </div>
        <button onClick={() => { setToken(null); router.replace("/login"); }}
                className="text-sm border border-slate-300 rounded-md px-3 py-1.5 bg-white">Sign out</button>
      </header>

      {run?.note && <p className="mt-3 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-md p-2">{run.note}</p>}

      <section aria-label="Plan summary" className="mt-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {cards.map(([label, value]) => (
          <div key={label} className="bg-white border border-slate-200 rounded-lg p-3">
            <p className="text-xs text-slate-600">{label}</p>
            <p className="text-xl font-semibold">{value}</p>
          </div>
        ))}
      </section>

      <section aria-label="Filters" className="mt-4 flex flex-wrap items-end gap-3 bg-white border border-slate-200 rounded-lg p-3 text-sm">
        <label>Status
          <select value={f.status} onChange={(e) => change("status", e.target.value)} className="block mt-1 border border-slate-300 rounded-md px-2 py-1">
            <option value="">All</option><option value="order">Order</option>
            <option value="warehouse short">Warehouse short</option><option value="hold">Hold</option>
          </select></label>
        <label>City
          <select value={f.city} onChange={(e) => change("city", e.target.value)} className="block mt-1 border border-slate-300 rounded-md px-2 py-1">
            <option value="">All</option><option value="3">City 3</option><option value="12">City 12</option><option value="16">City 16</option>
          </select></label>
        <label>Stockout
          <select value={f.stockout} onChange={(e) => change("stockout", e.target.value)} className="block mt-1 border border-slate-300 rounded-md px-2 py-1">
            <option value="">Any</option><option value="likely">Likely</option><option value="possible">Possible</option>
          </select></label>
        <label>Sort by
          <select value={f.sort} onChange={(e) => change("sort", e.target.value)} className="block mt-1 border border-slate-300 rounded-md px-2 py-1">
            <option value="order_qty">Order quantity</option><option value="short_qty">Short quantity</option>
            <option value="expiring_units">Expiring units</option><option value="on_hand">Stock on hand</option>
            <option value="target">Target</option>
          </select></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={f.expiring} onChange={(e) => change("expiring", e.target.checked)} />Expiring only</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={f.undecided} onChange={(e) => change("undecided", e.target.checked)} />Undecided only</label>
        <button onClick={() => { setF(INITIAL); setOffset(0); }} className="border border-slate-300 rounded-md px-3 py-1">Reset</button>
      </section>

      {error && <p role="alert" className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-2">{error}</p>}

      <div className="mt-4 overflow-x-auto bg-white border border-slate-200 rounded-lg">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-xs text-slate-700">
            <tr>{["Store", "Product", "City", "Status", "On hand", "Forecast", "P90", "Target", "Order", "Ship", "Short", "Expiring", "Stockout", "Decision", "Actions"]
              .map((h) => <th key={h} className="px-3 py-2 whitespace-nowrap">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 align-top">
                <td className="px-3 py-2">{r.store_id}</td><td className="px-3 py-2">{r.product_id}</td><td className="px-3 py-2">{r.city_id}</td>
                <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs whitespace-nowrap ${BADGE[r.status] ?? ""}`}>{r.status}</span></td>
                <td className="px-3 py-2">{n(r.on_hand)}</td><td className="px-3 py-2">{n(r.forecast_today)}</td><td className="px-3 py-2">{n(r.p90_today)}</td>
                <td className="px-3 py-2">{n(r.target, 0)}</td><td className="px-3 py-2 font-semibold">{n(r.order_qty)}</td>
                <td className="px-3 py-2">{n(r.ship_qty)}</td><td className="px-3 py-2">{n(r.short_qty)}</td><td className="px-3 py-2">{n(r.expiring_units)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{r.stockout_likely ? "Likely" : r.stockout_possible ? "Possible" : "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{r.decision_action
                  ? `${r.decision_action}${r.decision_action === "edit" && r.decision_qty != null ? ` (${n(r.decision_qty)})` : ""}` : "—"}</td>
                <td className="px-3 py-2">
                  {editing?.id === r.id ? (
                    <div className="flex gap-1">
                      <input aria-label="New quantity" type="number" min={0} value={editing.value}
                             onChange={(e) => setEditing({ id: r.id, value: e.target.value })}
                             className="w-20 border border-slate-300 rounded-md px-2 py-1" />
                      <button onClick={() => decide(r, "edit", Number(editing.value))} disabled={editing.value === ""}
                              className="border border-slate-300 rounded-md px-2 py-1 disabled:opacity-50">Save</button>
                      <button onClick={() => setEditing(null)} className="border border-slate-300 rounded-md px-2 py-1">Cancel</button>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      <button onClick={() => decide(r, "approve")} className="border border-slate-300 rounded-md px-2 py-1">Approve</button>
                      <button onClick={() => setEditing({ id: r.id, value: String(Math.round(r.order_qty)) })} className="border border-slate-300 rounded-md px-2 py-1">Edit</button>
                      <button onClick={() => decide(r, "reject")} className="border border-slate-300 rounded-md px-2 py-1">Reject</button>
                      <button onClick={() => setExplainLine(r)} className="bg-slate-900 text-white rounded-md px-2 py-1">Explain</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && <tr><td colSpan={15} className="px-3 py-6 text-center text-slate-600">No lines match these filters.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center gap-3 text-sm">
        <button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="border border-slate-300 rounded-md px-3 py-1 bg-white disabled:opacity-50">Previous</button>
        <span>Rows {rows.length ? offset + 1 : 0}–{offset + rows.length}{loading ? " (loading…)" : ""}</span>
        <button disabled={rows.length < PAGE || loading} onClick={() => setOffset(offset + PAGE)} className="border border-slate-300 rounded-md px-3 py-1 bg-white disabled:opacity-50">Next</button>
      </div>

      {explainLine && <ExplainPanel line={explainLine} onClose={() => setExplainLine(null)} />}
    </main>
  );
}