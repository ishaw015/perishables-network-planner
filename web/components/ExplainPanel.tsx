"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Explanation, StoreLine } from "@/lib/types";

const QUICK = [
  "Why does the plan order this quantity for this store and product?",
  "Is this store at risk of running out of stock today, and why?",
  "Is any stock at this store expected to expire?",
  "Why can't the full order be shipped to this store?",
];

export default function ExplainPanel({ line, onClose }: { line: StoreLine; onClose: () => void }) {
  const [question, setQuestion] = useState(QUICK[0]);
  const [result, setResult] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { setResult(null); setErr(""); }, [line.id]);

  async function ask(q: string) {
    setQuestion(q); setBusy(true); setErr(""); setResult(null);
    try {
      setResult(await api<Explanation>(`/store-lines/${line.id}/explain`,
        { method: "POST", body: JSON.stringify({ question: q }) }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not get an explanation");
    } finally { setBusy(false); }
  }

  return (
    <aside className="fixed right-0 top-0 h-full w-full max-w-md bg-white border-l border-slate-200 shadow-xl p-5 overflow-y-auto z-20 text-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Explain this line</h2>
          <p className="text-sm text-slate-600">Store {line.store_id} · Product {line.product_id} · City {line.city_id} · {line.status}</p>
        </div>
        <button onClick={onClose} className="text-sm border border-slate-300 rounded-md px-2 py-1">Close</button>
      </div>

      <p className="mt-3 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-md p-2">
        The order quantity comes from the planning policy. This explanation never changes it.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button key={q} onClick={() => ask(q)} disabled={busy}
                  className="text-left text-xs border border-slate-300 rounded-md px-2 py-1 hover:bg-slate-50 disabled:opacity-50">{q}</button>
        ))}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); ask(question); }} className="mt-4 space-y-2">
        <label className="block text-sm">Your question
          <textarea value={question} maxLength={300} rows={3} onChange={(e) => setQuestion(e.target.value)}
                    className="mt-1 w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </label>
        <button disabled={busy || question.trim().length < 3} className="bg-slate-900 text-white rounded-md px-3 py-2 text-sm disabled:opacity-50">
          {busy ? "Checking the plan data…" : "Ask"}
        </button>
      </form>

      {err && <p role="alert" className="mt-4 text-sm text-red-700">{err}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-relaxed">{result.answer}</p>
          <p className="text-xs">
            {result.source === "gemini"
              ? <span className="inline-block rounded-full bg-green-100 text-green-900 px-2 py-0.5">Verified: every number matches the plan data</span>
              : <span className="inline-block rounded-full bg-amber-100 text-amber-900 px-2 py-0.5">Standard template: the AI answer was unavailable or failed the checks</span>}
            {result.cannot_answer && <span className="ml-2 inline-block rounded-full bg-slate-100 text-slate-800 px-2 py-0.5">Not available in the plan data</span>}
          </p>
          {result.used_facts.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-700">Sources used</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {result.used_facts.map((k) => <code key={k} className="text-xs bg-slate-100 rounded px-1.5 py-0.5">{k}</code>)}
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}