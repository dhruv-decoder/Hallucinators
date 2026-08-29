// Shared API base so both the data client (api.ts) and the auth client (auth.ts) agree without a cycle.
// Dev: "/api" is rewritten to the FastAPI backend (see next.config). Prod: build with NEXT_PUBLIC_API_BASE=""
// so the statically-exported app calls the backend same-origin.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
