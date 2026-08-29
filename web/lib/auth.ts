"use client";
// Client-side auth + workspace state. Tokens live in localStorage (the backend is stateless JWT), and every
// data request carries Authorization + X-Workspace headers (see api.ts). A tiny pub/sub lets the shell
// re-render on login/logout/workspace-switch without a state library.
import { useEffect, useState } from "react";
import { API_BASE } from "./config";

export interface Workspace { id: string; name: string; use_case: string }
export interface AuthUser { id: string; email: string; name: string }
export interface Session { token: string; user: AuthUser; workspaces: Workspace[] }

const K = { token: "cp_token", ws: "cp_workspace", user: "cp_user", wss: "cp_workspaces", guest: "cp_guest" };

const subs = new Set<() => void>();
export function subscribe(f: () => void) { subs.add(f); return () => { subs.delete(f); }; }
function emit() { subs.forEach((f) => f()); }

function lget(k: string): string | null { try { return localStorage.getItem(k); } catch { return null; } }
function lset(k: string, v: string | null) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} }

export interface AuthState { token: string | null; user: AuthUser | null; workspaces: Workspace[]; workspace: string | null; guest: boolean }
export function getState(): AuthState {
  const userRaw = lget(K.user); const wssRaw = lget(K.wss);
  return {
    token: lget(K.token),
    user: userRaw ? JSON.parse(userRaw) : null,
    workspaces: wssRaw ? JSON.parse(wssRaw) : [],
    workspace: lget(K.ws),
    guest: lget(K.guest) === "1",
  };
}
export function isAuthed(): boolean { const s = getState(); return !!s.token || s.guest; }

export function authHeaders(): Record<string, string> {
  const s = getState(); const h: Record<string, string> = {};
  if (s.token) h["Authorization"] = `Bearer ${s.token}`;
  if (s.workspace) h["X-Workspace"] = s.workspace;
  return h;
}
export function streamAuthParams(): string {
  const s = getState(); const p = new URLSearchParams();
  if (s.token) p.set("token", s.token);
  if (s.workspace) p.set("workspace", s.workspace);
  const q = p.toString(); return q ? `?${q}` : "";
}

function persistSession(s: Session) {
  lset(K.token, s.token); lset(K.user, JSON.stringify(s.user)); lset(K.wss, JSON.stringify(s.workspaces));
  lset(K.ws, s.workspaces[0]?.id ?? null); lset(K.guest, null); emit();
}
export function continueAsGuest() { lset(K.guest, "1"); [K.token, K.user, K.wss, K.ws].forEach((k) => lset(k, null)); emit(); }
export function logout() { [K.token, K.user, K.wss, K.ws, K.guest].forEach((k) => lset(k, null)); emit(); }
export function setWorkspace(id: string) { lset(K.ws, id); emit(); }

async function authPost(path: string, body: unknown): Promise<any> {
  const r = await fetch(`${API_BASE}${path}`, { method: "POST", headers: { "content-type": "application/json", ...authHeaders() }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${r.status}`);
  return data;
}
export async function login(email: string, password: string): Promise<Session> { const s = await authPost("/auth/login", { email, password }); persistSession(s); return s; }
export async function signup(email: string, password: string, name: string): Promise<Session> { const s = await authPost("/auth/signup", { email, password, name }); persistSession(s); return s; }
export async function loginDemo(): Promise<Session> { return login("demo@controlplane.ai", "demo1234"); }

export async function createWorkspace(name: string, use_case: string): Promise<Workspace> {
  const w: Workspace = await authPost("/auth/workspaces", { name, use_case });
  const s = getState(); lset(K.wss, JSON.stringify([...s.workspaces, w])); lset(K.ws, w.id); emit(); return w;
}
export async function deleteWorkspace(id: string): Promise<void> {
  await fetch(`${API_BASE}/auth/workspaces/${id}`, { method: "DELETE", headers: authHeaders() });
  const s = getState(); const wss = s.workspaces.filter((w) => w.id !== id);
  lset(K.wss, JSON.stringify(wss)); if (s.workspace === id) lset(K.ws, wss[0]?.id ?? null); emit();
}

// React binding: re-render on any auth change.
export function useAuth(): AuthState {
  const [, bump] = useState(0);
  useEffect(() => subscribe(() => bump((n) => n + 1)), []);
  return getState();
}
