/** @type {import('next').NextConfig} */
// Two modes:
//  - dev (default): a rewrite proxies /api/* to the FastAPI backend, so the browser has no CORS hop.
//  - export (NEXT_OUTPUT=export): a fully static build (web/out) that FastAPI serves itself -> ONE service.
//    In that mode the frontend calls the API same-origin, so build with NEXT_PUBLIC_API_BASE="".
const isExport = process.env.NEXT_OUTPUT === "export";

const nextConfig = {
  reactStrictMode: true,
  ...(isExport
    ? { output: "export", images: { unoptimized: true } }
    : {
        async rewrites() {
          const backend = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";
          return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
        },
      }),
};
export default nextConfig;
