import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ControlPlane · The Tower",
  description: "Real-time AI oversight as a value-of-information decision under a latency budget.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
