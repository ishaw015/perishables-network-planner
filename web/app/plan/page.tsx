"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ExplainPanel from "@/components/ExplainPanel";
import FulfilmentBar from "@/components/FulfilmentBar";
import WhatIfPanel from "@/components/WhatIfPanel";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import type { PlanRun, StoreLine, Summary } from "@/lib/types";

const PAGE = 25;
const n = (x: number, d = 0) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: d });
const prettyDate = (s: string) =>
  new Date(`${s}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

type Filters = { status: string; city: string; stockout: string; expiring: boolean; undecided: boolean; sort: string };
const INITIAL: Filters = { status: "", city: "", stockout: "", expiring: false, undecided: false, sort: "order_qty" };

const STATUS: Record<string, { dot: string; label: string }> = {
  order: { dot: "bg-[#1226A9]", label: "Order" },
  "warehouse short": { dot: "bg-amber-500", label: "Warehouse short" },
  hold: { dot: "bg-slate-400", label: "Hold" },
};
const DECISION: Record<string, string> = {
  approve: "bg-emerald-50 text-emerald-800",
  edit: "bg-blue-50 text-blue-800",
  reject: "bg-red-50 text-red-700",
};

const COLUMNS: { label: string; right?: boolean; hint?: string }[] = [
  { label: "Store" }, { label: "Product" }, { label: "City" }, { label: "Status" },
  { label: "On hand", right: true, hint: "Units in the store now" },
  { label: "Forecast / P90", right: true, hint: "Expected demand today, and the high-demand (P90) estimate" },
  { label: "Target", right: true, hint: "Stock level the order tops the store up to" },
  { label: "Order", right: true, hint: "Units the store needs to order" },
  { label: "Ship", right: true, hint: "Units the city warehouse can send today" },
  { label: "Short", right: true, hint: "Units the warehouse cannot send today" },
  { label: "Expiring", right: true, hint: "Units expected to expire before they sell" },
  { label: "Risk", hint: "Whether stock is below today's forecast" },
  { label: "Decision" }, { label: "Actions" },
];

const btn = "rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-800 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-[#1226A9]";

export default function PlanPage() {
  const router = useRouter();
  const [view, setView] = useState<"plan" | "whatif">("plan");
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

  const quick = summary ? [
    { label: "Warehouse short", count: summary.warehouse_short, active: f.status === "warehouse short",
      toggle: () => change("status", f.status === "warehouse short" ? "" : "warehouse short") },
    { label: "Stockout likely", count: summary.stockout_likely, active: f.stockout === "likely",
      toggle: () => change("stockout", f.stockout === "likely" ? "" : "likely") },
    { label: "Expiring stock", count: summary.expiring_series, active: f.expiring,
      toggle: () => change("expiring", !f.expiring) },
    { label: "Not decided yet", count: summary.lines - summary.decided_lines, active: f.undecided,
      toggle: () => change("undecided", !f.undecided) },
  ] : [];

  const stats: { label: string; value: number; tone?: string }[] = summary ? [
    { label: "Store lines", value: summary.lines },
    { label: "To order", value: summary.orders },
    { label: "Warehouse short", value: summary.warehouse_short, tone: "text-amber-700" },
    { label: "Hold", value: summary.holds },
    { label: "Stockout likely", value: summary.stockout_likely, tone: "text-red-700" },
    { label: "Expiring units", value: summary.expiring_units, tone: "text-amber-700" },
    { label: "Decided", value: summary.decided_lines, tone: "text-emerald-700" },
  ] : [];

  const filtersActive = JSON.stringify(f) !== JSON.stringify(INITIAL);

  return (
    <div className="min-h-screen bg-[#F3F6FB] text-slate-900">
      <header className="bg-[#0B1D45] text-white">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-4 pt-3 md:px-6">
          <h1 className="text-lg font-semibold tracking-tight">Perishables Network Planner</h1>
          <button onClick={() => { setToken(null); router.replace("/login"); }}
                  className="rounded-lg border border-white/25 px-3 py-1.5 text-sm hover:bg-white/10">Sign out</button>
        </div>
        <nav aria-label="Sections" className="mx-auto mt-2 flex max-w-[1500px] gap-1 px-4 md:px-6">
          {([["plan", "Daily plan"], ["whatif", "What-if"]] as const).map(([key, label]) => (
            <button key={key} role="tab" aria-selected={view === key} onClick={() => setView(key)}
                    className={`border-b-[3px] px-4 pb-2.5 pt-2 text-sm font-medium transition ${
                      view === key ? "border-[#2AAAE2] text-white" : "border-transparent text-white/65 hover:text-white"}`}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6">
        {run?.note && (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
            <span className="font-semibold">Demo data. </span>{run.note}
          </p>
        )}

        {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">{error}</p>}

        {view === "whatif" && run && <WhatIfPanel runId={run.id} />}

        {view === "plan" && (
          <>
            {/* hero: today's plan and how much of it can ship */}
            <section aria-label="Plan overview" className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6">
              <div className="grid gap-6 lg:grid-cols-[1fr_28rem] lg:items-center">
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-[#0B1D45]">
                    {run ? `Plan for ${prettyDate(run.plan_date)}` : "Loading plan…"}
                  </h2>
                  {run && (
                    <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
                      <div className="flex gap-1.5"><dt>Shelf life</dt><dd className="font-medium text-slate-900">{run.shelf_life_days} days</dd></div>
                      <div className="flex gap-1.5"><dt>Safety factor κ</dt><dd className="font-medium text-slate-900">{run.kappa}</dd></div>
                    </dl>
                  )}
                  {summary && (
                    <p className="mt-3 max-w-prose text-sm text-slate-700">
                      Stores asked for <b>{n(summary.ordered_units)}</b> units. Warehouses can ship <b>{n(summary.shipped_units)}</b>;
                      {" "}<b>{n(summary.short_units)}</b> units are short across <b>{n(summary.warehouse_short)}</b> store lines.
                      Review those first.
                    </p>
                  )}
                </div>
                {summary && <FulfilmentBar emphasis label="Shipping rate" shipped={summary.shipped_units} ordered={summary.ordered_units} short={summary.short_units} />}
              </div>

              <dl className="mt-6 grid grid-cols-2 divide-slate-200 overflow-hidden rounded-xl border border-slate-200 sm:grid-cols-4 lg:grid-cols-7 lg:divide-x">
                {stats.map((s) => (
                  <div key={s.label} className="border-b border-slate-100 px-4 py-3 lg:border-b-0">
                    <dt className="text-xs text-slate-600">{s.label}</dt>
                    <dd className={`text-xl font-semibold tabular-nums ${s.tone ?? "text-slate-900"}`}>{n(s.value)}</dd>
                  </div>
                ))}
              </dl>
            </section>

            {/* filters */}
            <section aria-label="Filters" className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-sm font-medium text-slate-800">Focus on</span>
                {quick.map((c) => (
                  <button key={c.label} onClick={c.toggle} aria-pressed={c.active}
                          className={`rounded-full border px-3 py-1 text-sm transition ${
                            c.active ? "border-[#0B1D45] bg-[#0B1D45] text-white"
                                     : "border-slate-300 bg-white text-slate-800 hover:border-[#1226A9]"}`}>
                    {c.label} <span className={`ml-1 tabular-nums ${c.active ? "text-white/80" : "text-slate-500"}`}>{n(c.count)}</span>
                  </button>
                ))}
                <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
                  <label className="flex items-center gap-2 text-slate-700">City
                    <select value={f.city} onChange={(e) => change("city", e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1">
                      <option value="">All</option><option value="3">City 3</option><option value="12">City 12</option><option value="16">City 16</option>
                    </select></label>
                  <label className="flex items-center gap-2 text-slate-700">Sort by
                    <select value={f.sort} onChange={(e) => change("sort", e.target.value)} className="rounded-lg border border-slate-300 bg-white px-2 py-1">
                      <option value="order_qty">Order quantity</option><option value="short_qty">Short quantity</option>
                      <option value="expiring_units">Expiring units</option><option value="on_hand">Stock on hand</option>
                      <option value="target">Target</option>
                    </select></label>
                  {filtersActive && <button onClick={() => { setF(INITIAL); setOffset(0); }} className="text-sm font-medium text-[#1226A9] hover:underline">Clear filters</button>}
                </div>
              </div>
            </section>

            {/* table */}
            <section aria-label="Store lines" className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
              <div className="max-h-[70vh] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-50 text-xs text-slate-600 shadow-[0_1px_0_#e2e8f0]">
                    <tr>{COLUMNS.map((c) => (
                      <th key={c.label} title={c.hint} scope="col"
                          className={`whitespace-nowrap px-3 py-2.5 font-medium ${c.right ? "text-right" : "text-left"}`}>
                        {c.label}{c.hint && <span className="ml-1 text-slate-400" aria-hidden="true">ⓘ</span>}
                      </th>))}</tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const st = STATUS[r.status] ?? { dot: "bg-slate-400", label: r.status };
                      return (
                        <tr key={r.id} className="border-t border-slate-100 align-middle transition hover:bg-slate-50">
                          <td className="px-3 py-2.5 tabular-nums">{r.store_id}</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.product_id}</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.city_id}</td>
                          <td className="whitespace-nowrap px-3 py-2.5">
                            <span className="inline-flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${st.dot}`} />{st.label}</span>
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{n(r.on_hand, 1)}</td>
                          <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">{n(r.forecast_today, 1)} <span className="text-slate-400">/ {n(r.p90_today, 1)}</span></td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{n(r.target)}</td>
                          <td className="px-3 py-2.5 text-right text-base font-semibold tabular-nums text-[#0B1D45]">{n(r.order_qty, 1)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{n(r.ship_qty, 1)}</td>
                          <td className={`px-3 py-2.5 text-right tabular-nums ${r.short_qty > 0.5 ? "font-semibold text-amber-700" : "text-slate-500"}`}>{n(r.short_qty, 1)}</td>
                          <td className={`px-3 py-2.5 text-right tabular-nums ${r.expiring_units > 0.5 ? "font-semibold text-amber-700" : "text-slate-500"}`}>{n(r.expiring_units, 1)}</td>
                          <td className="whitespace-nowrap px-3 py-2.5">
                            {r.stockout_likely ? <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">Likely</span>
                              : r.stockout_possible ? <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">Possible</span>
                              : <span className="text-slate-400">None</span>}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2.5">
                            {r.decision_action
                              ? <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DECISION[r.decision_action] ?? "bg-slate-100"}`}>
                                  {r.decision_action === "approve" ? "Approved" : r.decision_action === "reject" ? "Rejected" : "Edited"}
                                  {r.decision_action === "edit" && r.decision_qty != null ? ` to ${n(r.decision_qty)}` : ""}</span>
                              : <span className="text-slate-400">Not decided</span>}
                          </td>
                          <td className="px-3 py-2.5">
                            {editing?.id === r.id ? (
                              <div className="flex gap-1">
                                <input aria-label="New quantity" type="number" min={0} value={editing.value}
                                       onChange={(e) => setEditing({ id: r.id, value: e.target.value })}
                                       className="w-20 rounded-lg border border-slate-300 px-2 py-1 text-xs" />
                                <button onClick={() => decide(r, "edit", Number(editing.value))} disabled={editing.value === ""}
                                        className={`${btn} disabled:opacity-50`}>Save</button>
                                <button onClick={() => setEditing(null)} className={btn}>Cancel</button>
                              </div>
                            ) : (
                              <div className="flex flex-wrap gap-1">
                                <button onClick={() => decide(r, "approve")} className={`${btn} border-emerald-300 text-emerald-800 hover:bg-emerald-50`}>Approve</button>
                                <button onClick={() => setEditing({ id: r.id, value: String(Math.round(r.order_qty)) })} className={btn}>Edit</button>
                                <button onClick={() => decide(r, "reject")} className={`${btn} text-red-700 hover:bg-red-50`}>Reject</button>
                                <button onClick={() => setExplainLine(r)} className="rounded-lg bg-[#0B1D45] px-2.5 py-1 text-xs font-medium text-white transition hover:bg-[#1226A9]">Explain</button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {!loading && rows.length === 0 && (
                      <tr><td colSpan={COLUMNS.length} className="px-3 py-10 text-center text-slate-600">
                        No store lines match these filters. <button onClick={() => { setF(INITIAL); setOffset(0); }} className="font-medium text-[#1226A9] hover:underline">Clear filters</button>
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-700">
                <button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))} className={`${btn} disabled:opacity-50`}>Previous</button>
                <span className="tabular-nums">Showing {rows.length ? offset + 1 : 0} to {offset + rows.length}{loading ? " (loading…)" : ""}</span>
                <button disabled={rows.length < PAGE || loading} onClick={() => setOffset(offset + PAGE)} className={`${btn} disabled:opacity-50`}>Next</button>
              </div>
            </section>
          </>
        )}
      </main>

      {explainLine && <ExplainPanel line={explainLine} onClose={() => setExplainLine(null)} />}
    </div>
  );
}