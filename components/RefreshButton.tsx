"use client";

import { useState } from "react";

export function RefreshButton() {
  const [token, setToken] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "busy" | "ok" | "error"; msg?: string }>({ kind: "idle" });

  async function trigger(e: React.FormEvent) {
    e.preventDefault();
    setState({ kind: "busy" });
    try {
      const res = await fetch("/api/admin/refresh", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`);
      setState({ kind: "ok", msg: body.message });
    } catch (err) {
      setState({ kind: "error", msg: (err as Error).message });
    }
  }

  return (
    <form onSubmit={trigger} className="flex flex-col gap-3">
      <label htmlFor="admin-token" className="text-sm font-medium text-slate-700">
        Admin token
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="admin-token"
          type="password"
          autoComplete="off"
          required
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="h-10 flex-1 rounded-md border border-slate-300 px-3 text-sm"
        />
        <button
          type="submit"
          disabled={state.kind === "busy" || !token}
          className="h-10 rounded-md bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {state.kind === "busy" ? "Starting…" : "Run refresh now"}
        </button>
      </div>
      <p aria-live="polite" className={`text-sm ${state.kind === "error" ? "text-red-700" : "text-slate-600"}`}>
        {state.msg}
      </p>
    </form>
  );
}
