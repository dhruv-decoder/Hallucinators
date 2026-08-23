import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ControlPlane · The Tower",
  description: "Real-time AI oversight as a value-of-information decision under a latency budget — safer AND cheaper.",
};

// Set the saved theme before paint to avoid a flash of the wrong theme.
const THEME_INIT = `(function(){try{var t=localStorage.getItem('cp-theme')||'dark';document.documentElement.classList.add(t);}catch(e){document.documentElement.classList.add('dark');}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_INIT }} /></head>
      <body>{children}</body>
    </html>
  );
}
