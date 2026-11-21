const n = (x: number) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: 0 });

/** Share of what stores asked for that the warehouses can actually ship. */
export function shipRate(shipped: number, ordered: number) {
  return ordered > 0 ? Math.min(100, (shipped / ordered) * 100) : 100;
}

export default function FulfilmentBar({ shipped, ordered, short, label, emphasis = false }: {
  shipped: number; ordered: number; short: number; label?: string; emphasis?: boolean;
}) {
  const pct = shipRate(shipped, ordered);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        {label && <span className="text-sm font-medium text-slate-700">{label}</span>}
        <span className={`tabular-nums font-semibold ${emphasis ? "text-2xl text-[#0B1D45]" : "text-base text-slate-900"}`}>
          {pct.toFixed(1)}%<span className="ml-1 text-xs font-normal text-slate-500">of orders can ship</span>
        </span>
      </div>
      <div className="mt-1.5 flex h-3 w-full overflow-hidden rounded-full bg-amber-300"
           role="img" aria-label={`${pct.toFixed(1)} percent of ordered units can be shipped`}>
        <div className="h-full bg-[#1226A9] transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-xs tabular-nums text-slate-600">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#1226A9] align-middle" />Ships {n(shipped)} units</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-amber-300 align-middle" />Short {n(short)} units</span>
      </div>
    </div>
  );
}