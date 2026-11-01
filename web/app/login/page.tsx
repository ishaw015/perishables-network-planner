"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try { await login(email, password); router.push("/plan"); }
    catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
    finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-xl p-6 space-y-4 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold">Perishables Network Planner</h1>
          <p className="text-sm text-slate-600">Sign in to review today&apos;s plan</p>
        </div>
        <label className="block text-sm">Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                 className="mt-1 w-full border border-slate-300 rounded-md px-3 py-2" />
        </label>
        <label className="block text-sm">Password
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                 className="mt-1 w-full border border-slate-300 rounded-md px-3 py-2" />
        </label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button disabled={busy} className="w-full bg-slate-900 text-white rounded-md py-2 disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}