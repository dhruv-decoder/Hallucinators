"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Landing } from "./Landing";
import { Auth } from "./Auth";
import Dashboard from "./Dashboard";

// One page, three surfaces: marketing landing, the auth gate, and the live app, switched by the URL hash
// (#app). Keeping it a single route means the static export is one index.html, clean to serve from FastAPI.
export default function Site() {
  // The hash is "#app", optionally with a panel: "#app/playground". That lets the architecture diagram on
  // the landing page open the exact panel a component corresponds to, rather than dropping the visitor on
  // the overview to find it themselves.
  const [route, setRoute] = useState<{ launched: boolean; view: string | null }>({ launched: false, view: null });
  const auth = useAuth();
  useEffect(() => {
    const sync = () => {
      const hash = typeof location !== "undefined" ? location.hash.replace(/^#/, "") : "";
      const [root, view] = hash.split("/");
      setRoute({ launched: root === "app", view: view || null });
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const { launched, view } = route;

  if (!launched) return <Landing onLaunch={(v?: string) => { location.hash = v ? `app/${v}` : "app"; }} />;
  const authed = !!auth.token || auth.guest;
  if (!authed) return <Auth onHome={() => { location.hash = ""; }} />;
  // Remount the dashboard when the active workspace changes so its live feed + P&L reload cleanly for the
  // newly-selected (isolated) workspace.
  return <Dashboard key={auth.workspace ?? "guest"} initialView={view} onHome={() => { location.hash = ""; }} />;
}
