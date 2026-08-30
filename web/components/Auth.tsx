"use client";
import { useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { continueAsGuest, login, loginDemo, signup } from "@/lib/auth";
import { BrandMark } from "./ui";
import { ThemeToggle } from "./theme";

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark size={32} />
      <div className="leading-tight"><b className="text-[16px]">ControlPlane</b><span className="block text-[11px] text-faint">The Tower</span></div>
    </div>
  );
}

export function Auth({ onHome }: { onHome?: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e) { setErr(String(e instanceof Error ? e.message : e)); }
    setBusy(false);
  };
  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(() => (mode === "login" ? login(email, password) : signup(email, password, name)));
  };

  return (
    <div className="grid min-h-screen place-items-center px-4 py-20 sm:px-6">
      <nav className="glass fixed left-0 right-0 top-0 flex items-center gap-4 border-b border-line px-4 py-3 sm:px-6">
        <button onClick={onHome} className="text-left"><Logo /></button>
        <span className="flex-1" /><ThemeToggle />
      </nav>

      <div className="grid w-full max-w-[920px] grid-cols-[1.1fr_1fr] gap-8 rounded-2xl max-md:grid-cols-1">
        {/* pitch side */}
        <div className="flex flex-col justify-center max-md:hidden">
          <div className="mb-4 inline-flex w-fit items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted">
            <span className="h-1.5 w-1.5 animate-pulseglow rounded-full" style={{ background: "var(--accent)" }} /> Multi-tenant control tower
          </div>
          <h1 className="text-3xl font-bold leading-tight tracking-tight">Every use case, kept apart.</h1>
          <p className="mt-3 max-w-[380px] text-muted">Sign in to manage your workspaces. Each one, support bot, internal copilot, agentic ops, gets its own isolated policy set, audit log, and oversight P&L. Nothing bleeds across cases.</p>
          <div className="mt-6 flex flex-col gap-2.5 text-[13px] text-muted">
            {["Isolated policies + hash-chained audit log per workspace", "Self-funding oversight P&L, scoped to each case", "Drop-in OpenAI-compatible gateway"].map((t) => (
              <div key={t} className="flex items-center gap-2"><ShieldCheck size={15} style={{ color: "var(--accent)" }} />{t}</div>
            ))}
          </div>
        </div>

        {/* form side */}
        <div className="card p-6">
          <div className="mb-4 flex rounded-lg border border-line p-1 text-sm">
            {(["login", "signup"] as const).map((m) => (
              <button key={m} onClick={() => { setMode(m); setErr(null); }}
                className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${mode === m ? "bg-accent-dim text-ink" : "text-muted hover:text-ink"}`}>
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            {mode === "signup" && (
              <label className="block"><div className="mb-1 text-[12px] font-medium text-muted">Name</div>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" className="w-full rounded-lg border border-line bg-bg-2 p-2.5 text-sm outline-none focus:border-accent" /></label>
            )}
            <label className="block"><div className="mb-1 text-[12px] font-medium text-muted">Email</div>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="w-full rounded-lg border border-line bg-bg-2 p-2.5 text-sm outline-none focus:border-accent" /></label>
            <label className="block"><div className="mb-1 text-[12px] font-medium text-muted">Password</div>
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="at least 6 characters" className="w-full rounded-lg border border-line bg-bg-2 p-2.5 text-sm outline-none focus:border-accent" /></label>
            {err && <div className="rounded-lg border border-block/40 bg-block/5 p-2.5 text-[13px] text-block">{err}</div>}
            <button type="submit" disabled={busy} className="btn-primary inline-flex items-center justify-center gap-1.5">
              {busy ? "…" : mode === "login" ? "Sign in" : "Create account"} <ArrowRight size={15} />
            </button>
          </form>
          <div className="my-3 flex items-center gap-3 text-[11px] text-faint"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
          <div className="flex flex-col gap-2">
            <button className="btn" disabled={busy} onClick={() => submit(loginDemo)}>Try the demo account</button>
            <button className="btn" disabled={busy} onClick={continueAsGuest}>Continue as guest</button>
          </div>
          <p className="mt-3 text-center text-[11px] text-faint">Demo: demo@controlplane.ai · demo1234</p>
        </div>
      </div>
    </div>
  );
}
