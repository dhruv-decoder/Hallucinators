import type { Config } from "tailwindcss";

// Colors resolve to CSS variables (defined in globals.css) so the same classes work in dark + light.
const v = (name: string) => `var(--${name})`;

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  // The verdict badge builds its class from the action name at runtime (`badge-${action}`), so the scanner
  // cannot see it. Without this, `badge-auto_repair` is purged and auto-repaired responses render with an
  // unstyled badge, which is the one verdict a reviewer most needs to spot.
  safelist: ["badge-pass", "badge-annotate", "badge-auto_repair", "badge-escalate", "badge-block", "btn-reveal"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: v("bg"), 2: v("bg-2") },
        panel: { DEFAULT: v("panel"), 2: v("panel-2") },
        line: { DEFAULT: v("line"), 2: v("line-2") },
        ink: v("ink"),
        muted: v("muted"),
        faint: v("faint"),
        accent: { DEFAULT: v("accent"), dim: v("accent-dim"), ink: v("accent-ink") },
        pass: v("pass"),
        annotate: v("annotate"),
        repair: v("repair"),
        escalate: v("escalate"),
        block: v("block"),
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "JetBrains Mono", "Menlo", "monospace"],
      },
      borderRadius: { xl: "12px" },
      keyframes: {
        slidein: { from: { transform: "translateY(8px)", opacity: "0" }, to: { transform: "translateY(0)", opacity: "1" } },
        fadeup: { from: { transform: "translateY(14px)", opacity: "0" }, to: { transform: "translateY(0)", opacity: "1" } },
        pulseglow: { "0%,100%": { opacity: "0.6" }, "50%": { opacity: "1" } },
      },
      animation: {
        slidein: "slidein .2s ease-out",
        fadeup: "fadeup .5s cubic-bezier(.2,.7,.2,1) both",
        pulseglow: "pulseglow 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
