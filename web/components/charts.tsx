"use client";
import {
  Area, AreaChart, Bar, BarChart, Cell, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, XAxis, YAxis, ZAxis,
} from "recharts";
import { ACTION_COLOR } from "@/lib/format";
import type { Receipt } from "@/lib/api";

export function Sparkline({ series }: { series: number[] }) {
  const data = series.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={70}>
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="pnlgrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3fb950" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#3fb950" stopOpacity={0} />
          </linearGradient>
        </defs>
        <ReferenceLine y={0} stroke="#233" />
        <Area type="monotone" dataKey="v" stroke="#3fb950" strokeWidth={2} fill="url(#pnlgrad)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function QuadrantChart({ receipts }: { receipts: Receipt[] }) {
  const pts = receipts.slice(0, 150).map((r) => {
    const perf = r.per_axis.performance?.p_fail ?? 0;
    const oc = r.signals.find((s) => s.name === "overconfidence");
    return { x: 1 - perf, y: oc ? oc.score : 1 - perf * 0.5, color: ACTION_COLOR[r.action] };
  });
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 12, right: 16, bottom: 16, left: 0 }}>
        <ReferenceArea x1={0} x2={0.5} y1={0.5} y2={1} fill="#f85149" fillOpacity={0.08} />
        <ReferenceLine x={0.5} stroke="#1b232e" /><ReferenceLine y={0.5} stroke="#1b232e" />
        <XAxis type="number" dataKey="x" domain={[0, 1]} tick={{ fill: "#6b7684", fontSize: 11 }}
          label={{ value: "estimated correctness →", position: "insideBottom", offset: -6, fill: "#6b7684", fontSize: 11 }} />
        <YAxis type="number" dataKey="y" domain={[0, 1]} tick={{ fill: "#6b7684", fontSize: 11 }}
          label={{ value: "confidence →", angle: -90, position: "insideLeft", fill: "#6b7684", fontSize: 11 }} />
        <ZAxis range={[50, 50]} />
        <Scatter data={pts} isAnimationActive={false}>
          {pts.map((p, i) => <Cell key={i} fill={p.color} fillOpacity={0.85} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function Bars({ rows }: { rows: { name: string; value: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={rows.length * 40 + 20}>
      <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 40 }}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" width={120} tick={{ fill: "#93a1b1", fontSize: 12 }} />
        <Bar dataKey="value" radius={4} isAnimationActive={false}>
          {rows.map((r, i) => <Cell key={i} fill={r.value < 0 ? "#3fb950" : "#46d9e6"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
