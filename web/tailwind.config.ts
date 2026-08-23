import type { Config } from "tailwindcss";

// Control-tower palette: near-black slate, one signal-cyan accent, aviation status colours.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#0a0c10", 2: "#0e1117" },
        panel: { DEFAULT: "#12161d", 2: "#161b23" },
        line: { DEFAULT: "#222a35", 2: "#2b3543" },
        ink: "#e8eef5",
        muted: "#93a1b1",
        faint: "#6b7684",
        accent: { DEFAULT: "#46d9e6", dim: "#1c3a41" },
        pass: "#3fb950",
        annotate: "#58a6ff",
        repair: "#bc8cff",
        escalate: "#d9a221",
        block: "#f85149",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Inter", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "JetBrains Mono", "Menlo", "monospace"],
      },
      borderRadius: { xl: "12px" },
      keyframes: {
        slidein: { from: { transform: "translateY(8px)", opacity: "0" }, to: { transform: "translateY(0)", opacity: "1" } },
      },
      animation: { slidein: "slidein 0.2s ease-out" },
    },
  },
  plugins: [],
};
export default config;
