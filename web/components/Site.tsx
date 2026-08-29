"use client";
import { useEffect, useState } from "react";
import { Landing } from "./Landing";
import Dashboard from "./Dashboard";

// One page, two surfaces: the marketing landing and the live app, switched by the URL hash (#app). Keeping
// it a single route means the static export is one index.html, clean to serve from FastAPI as one service.
export default function Site() {
  const [launched, setLaunched] = useState(false);
  useEffect(() => {
    const sync = () => setLaunched(typeof location !== "undefined" && location.hash === "#app");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  return launched ? (
    <Dashboard onHome={() => { location.hash = ""; }} />
  ) : (
    <Landing onLaunch={() => { location.hash = "app"; }} />
  );
}
