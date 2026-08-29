"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Landing } from "./Landing";
import { Auth } from "./Auth";
import Dashboard from "./Dashboard";

// One page, three surfaces: marketing landing, the auth gate, and the live app, switched by the URL hash
// (#app). Keeping it a single route means the static export is one index.html, clean to serve from FastAPI.
export default function Site() {
  const [launched, setLaunched] = useState(false);
  const auth = useAuth();
  useEffect(() => {
    const sync = () => setLaunched(typeof location !== "undefined" && location.hash === "#app");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  if (!launched) return <Landing onLaunch={() => { location.hash = "app"; }} />;
  const authed = !!auth.token || auth.guest;
  if (!authed) return <Auth onHome={() => { location.hash = ""; }} />;
  // Remount the dashboard when the active workspace changes so its live feed + P&L reload cleanly for the
  // newly-selected (isolated) workspace.
  return <Dashboard key={auth.workspace ?? "guest"} onHome={() => { location.hash = ""; }} />;
}
