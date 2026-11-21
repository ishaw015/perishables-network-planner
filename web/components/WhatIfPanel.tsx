"use client";
import { useState } from "react";
import FulfilmentBar from "@/components/FulfilmentBar";
import { api } from "@/lib/api";
import type { Totals, WhatIfResult } from "@/lib/types";

const EXAMPLES = [
  { title: "A warehouse loses stock", text: "The city 12 warehouse lost half its stock", hint: "Shipments to every store in that city shrink." },
  { title: "Demand jumps", text: "Demand for product 191 in city 12 is 30 percent higher than forecast", hint: "Stores ask for more than the forecast expected." },
  { title: "Demand drops", text: "Demand in city 16 is 20 percent lower than forecast", hint: "Stores need less, so fewer units are short." },
];

const TYPE_LABEL: Record<string, string> = {
  warehouse_stock_cut: "Warehouse stock lost",
  demand_change: "Demand change",
  inbound_shortfall: "Stock on its way does not arrive",
};

const SIZE_LABEL: Record<string, (p: number) => string> = {
  warehouse_stock_cut: (p) => `${p}% of stock lost`,
  demand_change: (p) => `Demand ${p > 0 ? "+" : "−"}${Math.abs(p)}% vs forecast`,
  inbound_shortfall: (p) => `${p}% of incoming stock missing`,
};

type Row = { key: keyof Totals; label: string; worseWhen: "up" | "down" | "none" };
const ROWS: Row[] = [
  { key: "ordered_units", label: "Units stores ask for", worseWhen: "none" },
  { key: "shipped_units", label: "Units shipped to stores", worseWhen: "down" },
  { key: "short_units", label: "Units warehouses cannot ship", worseWhen: "up" },
  { key: "lines_short", label: "Store lines marked warehouse short", worseWhen: "up" },
  { key: "stockout_likely", label: "Store lines likely to stock out today", worseWhen: "up" },
];

const n = (x: number) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: 0 });

function Change({ before, after, worseWhen }: { before: number; after: number; worseWhen: Row["worseWhen"] }) {
  const d = after - before;
  if (d === 0) return <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">No change</span>;
  const worse = worseWhen === "none" ? null : (worseWhen === "up" ? d > 0 : d < 0);
  const tone = worse === null ? "bg-slate-100 text-slate-700" : worse ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ${tone}`}>
      {d > 0 ? "+" : "−"}{n(Math.abs(d))}
    </span>
  );
}

export default function WhatIfPanel({ runId }: { runId: number }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function preview(q: string) {
    setText(q); setBusy(true); setErr(""); setResult(null);
    try {
      setResult(await api<WhatIfResult>(`/plan-runs/${runId}/what-if`,
        { method: "POST", body: JSON.stringify({ text: q }) }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not run the preview. Try again.");
    } finally { setBusy(false); }
  }

  const sc = result?.scenario;
  const scenarioParts = sc ? [
    TYPE_LABEL[sc.type] ?? sc.type,
    sc.city_id != null ? `City ${sc.city_id}` : null,
    sc.product_id != null ? `Product ${sc.product_id}` : null,
    SIZE_LABEL[sc.type]?.(sc.percent) ?? `${sc.percent}%`,
  ].filter(Boolean) as string[] : [];

  const ok = result?.status === "ok" && result.before && result.after;

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      {/* ---------- left: describe the disruption ---------- */}
      <section aria-label="Describe a disruption" className="self-start rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-900">What happened?</h2>
        <p className="mt-1 text-sm text-slate-600">
          Describe a disruption in your own words. You will see how it changes shipments before anything is decided.
        </p>

        <form onSubmit={(e) => { e.preventDefault(); preview(text); }} className="mt-4">
          <label htmlFor="whatif-text" className="sr-only">Describe the disruption</label>
          <textarea id="whatif-text" value={text} maxLength={300} rows={3} onChange={(e) => setText(e.target.value)}
                    placeholder="For example: the city 12 warehouse lost half its stock"
                    className="w-full resize-none rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-[#1226A9] focus:ring-2 focus:ring-[#1226A9]/20" />
          <button disabled={busy || text.trim().length < 3}
                  className="mt-2 w-full rounded-xl bg-[#0B1D45] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#1226A9] disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? "Re-planning…" : "Preview impact"}
          </button>
        </form>

        <p className="mt-5 text-sm font-medium text-slate-900">Or try an example</p>
        <ul className="mt-2 space-y-2">
          {EXAMPLES.map((e) => (
            <li key={e.title}>
              <button onClick={() => preview(e.text)} disabled={busy}
                      className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-left transition hover:border-[#1226A9] hover:bg-slate-50 disabled:opacity-50">
                <span className="block text-sm font-medium text-slate-900">{e.title}</span>
                <span className="block text-xs text-slate-600">{e.hint}</span>
              </button>
            </li>
          ))}
        </ul>

        <p className="mt-5 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Preview only. The approved plan does not change, and the AI never decides quantities.
        </p>
      </section>

      {/* ---------- right: result ---------- */}
      <section aria-label="Preview result" aria-live="polite" className="min-w-0">
        {!result && !busy && !err && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8">
            <h2 className="text-base font-semibold text-slate-900">Your preview appears here</h2>
            <p className="mt-2 max-w-prose text-sm text-slate-600">
              The planning code re-runs today&apos;s plan with your disruption and compares it with the current plan.
              You will see how much of the stores&apos; orders can still ship, which measures get worse, and which store lines are hit hardest.
            </p>
          </div>
        )}

        {busy && (
          <div className="space-y-4" aria-busy="true">
            <div className="h-24 animate-pulse rounded-2xl bg-slate-200/70" />
            <div className="h-40 animate-pulse rounded-2xl bg-slate-200/70" />
          </div>
        )}

        {err && <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{err}</p>}

        {result && result.status !== "ok" && (
          <div role="status" className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
            <p className="font-medium">{result.status === "unsupported" ? "This cannot be previewed" : "One more detail needed"}</p>
            <p className="mt-1">{result.message}</p>
          </div>
        )}

        {ok && result.before && result.after && (
          <div className="space-y-5">
            {/* what was simulated + the verified explanation */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex flex-wrap items-center gap-2">
                {scenarioParts.map((p) => (
                  <span key={p} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-800">{p}</span>
                ))}
                <span className="text-xs text-slate-600">
                  {n(result.lines_in_scope ?? 0)} store lines affected, {n(result.lines_changed ?? 0)} change
                </span>
              </div>

              {result.explanation && (
                <>
                  <p className="mt-3 max-w-prose text-base leading-relaxed text-slate-900">{result.explanation.answer}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                    {result.explanation.source === "gemini"
                      ? <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 font-medium text-emerald-800">Verified: every number matches the computed preview</span>
                      : <span className="rounded-full bg-amber-50 px-2.5 py-0.5 font-medium text-amber-900">Standard template: the AI summary was unavailable or failed its checks</span>}
                    <span className="text-slate-500">Preview only</span>
                  </div>
                </>
              )}

              {result.lines_changed === 0 && (
                <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  This disruption would not change any shipment in today&apos;s plan.
                </p>
              )}
            </div>

            {/* shipping rate: the one thing to look at first */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="text-sm font-semibold text-slate-900">How much of the stores&apos; orders can ship</h3>
              <div className="mt-4 grid gap-6 md:grid-cols-2">
                <FulfilmentBar label="Current plan" shipped={result.before.shipped_units} ordered={result.before.ordered_units} short={result.before.short_units} />
                <FulfilmentBar label="In this scenario" emphasis shipped={result.after.shipped_units} ordered={result.after.ordered_units} short={result.after.short_units} />
              </div>
            </div>

            {/* what changed */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
              <table className="w-full text-sm">
                <caption className="sr-only">Current plan compared with the scenario</caption>
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-600">
                    <th scope="col" className="px-5 py-2.5 font-medium">Measure</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Current plan</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Scenario</th>
                    <th scope="col" className="px-5 py-2.5 text-right font-medium">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {ROWS.filter((r) => result.before![r.key] !== undefined && result.after![r.key] !== undefined).map((r) => (
                    <tr key={r.key} className="border-b border-slate-100 last:border-0">
                      <th scope="row" className="px-5 py-3 text-left font-normal text-slate-800">{r.label}</th>
                      <td className="px-3 py-3 text-right tabular-nums text-slate-600">{n(result.before![r.key]!)}</td>
                      <td className="px-3 py-3 text-right tabular-nums font-semibold text-slate-900">{n(result.after![r.key]!)}</td>
                      <td className="px-5 py-3 text-right"><Change before={result.before![r.key]!} after={result.after![r.key]!} worseWhen={r.worseWhen} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* most affected lines */}
            {result.top_lines && result.top_lines.length > 0 && (
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h3 className="text-sm font-semibold text-slate-900">Store lines hit hardest</h3>
                <p className="text-xs text-slate-600">Units shipped today, current plan and scenario.</p>
                <ul className="mt-3 divide-y divide-slate-100 text-sm">
                  {result.top_lines.map((t) => (
                    <li key={`${t.store_id}-${t.product_id}`} className="flex items-center justify-between gap-3 py-2">
                      <span className="text-slate-800">Store {t.store_id}, product {t.product_id}, city {t.city_id}</span>
                      <span className="tabular-nums text-slate-600">
                        {n(t.shipped_before)} <span aria-label="to">→</span> <span className="font-semibold text-slate-900">{n(t.shipped_after)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* how it was calculated */}
            {result.explanation && (
              <details className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm">
                <summary className="cursor-pointer font-medium text-slate-800">How this was calculated</summary>
                <p className="mt-2 max-w-prose text-slate-600">
                  The planning code re-ran the plan with the same rules as the daily plan. The AI only wrote the summary,
                  and a checker confirmed every number in it against the figures above.
                </p>
                {result.explanation.used_facts.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {result.explanation.used_facts.map((k) => <code key={k} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{k}</code>)}
                  </div>
                )}
              </details>
            )}
          </div>
        )}
      </section>
    </div>
  );
}