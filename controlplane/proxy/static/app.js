/* ControlPlane · The Tower — dashboard app.
   Framework-free SPA: hash router, live SSE feed, poll-based job progress with ETA, and canvas data-viz.
   Wired entirely to the oversight API in controlplane/proxy/app.py. */
"use strict";
const CP = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const el = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; };
  const ACT = { pass: "#3fb950", annotate: "#58a6ff", auto_repair: "#bc8cff", escalate: "#d9a221", block: "#f85149" };
  const AXC = { performance: "#58a6ff", responsibility: "#f85149", cost: "#3fb950" };
  const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const usd = (n) => (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(n && Math.abs(n) < 0.01 ? 5 : 2);
  const worst = (r) => { let a = null, p = -1; for (const [k, o] of Object.entries(r.per_axis || {})) if (o.p_fail > p) { p = o.p_fail; a = k; } return [a, Math.max(p, 0)]; };
  const fmtEta = (s) => s == null ? "—" : s < 1 ? "<1s" : s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;

  const state = { receipts: [], byId: {}, net: [], summary: {}, view: "overview" };

  /* ---- toasts ---------------------------------------------------------------------------------- */
  function toast(title, msg, kind = "") {
    const t = el(`<div class="toast ${kind}"><div class="t">${esc(title)}</div>${msg ? `<div class="m">${esc(msg)}</div>` : ""}</div>`);
    $("#toasts").appendChild(t); setTimeout(() => t.remove(), 4200);
  }

  /* ---- data ------------------------------------------------------------------------------------ */
  async function jget(u) { const r = await fetch(u); if (!r.ok) throw new Error(await r.text()); return r.json(); }
  async function jpost(u) { const r = await fetch(u, { method: "POST" }); if (!r.ok) throw new Error(await r.text()); return r.json(); }

  function addReceipt(r) {
    if (state.byId[r.request_id]) return;
    state.byId[r.request_id] = r; state.receipts.unshift(r);
    state.net.push((state.net.at(-1) || 0) + r.pnl.net_usd);
    if (LIVE.has(state.view)) render();
  }
  function applySummary(s) {
    state.summary = s;
    $("#upstream").textContent = s.upstream || "sim";
    const m = s.models || {}; $("#models").textContent = `${m.groundedness || "?"} · judge:${m.judge || "off"}`;
    $("#foot-status").innerHTML = `<span class="dot ${s.chain_valid ? "ok" : "bad"}"></span> chain ${s.chain_valid ? "verified" : "broken"} · ${s.requests} decisions`;
    const inc = (s.by_action?.block || 0) + (s.by_action?.escalate || 0);
    const pip = $("#nav-incidents"); pip.style.display = inc ? "" : "none"; pip.textContent = inc;
    const sel = $("#policy");
    if (!sel.dataset.filled && s.policies) { sel.dataset.filled = "1"; sel.innerHTML = Object.entries(s.policies).map(([k, v]) => `<option value="${k}">${v}</option>`).join(""); sel.onchange = () => jpost(`/v1/oversight/policy`, { policy: sel.value }); sel.onchange = () => fetch("/v1/oversight/policy", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ policy: sel.value }) }).then(() => toast("Policy switched", sel.options[sel.selectedIndex].text, "ok")); }
    if (LIVE.has(state.view)) render();
  }

  /* ---- charts (canvas) ------------------------------------------------------------------------- */
  function spark(cvs, series) {
    if (!cvs) return; const dpr = devicePixelRatio || 1, W = cvs.width = cvs.clientWidth * dpr, H = cvs.height = 64 * dpr, c = cvs.getContext("2d");
    c.clearRect(0, 0, W, H); if (series.length < 2) return;
    const mn = Math.min(0, ...series), mx = Math.max(0, ...series), sp = (mx - mn) || 1;
    const X = (i) => i / (series.length - 1) * W, Y = (v) => H - (v - mn) / sp * H;
    c.strokeStyle = "#233"; c.lineWidth = dpr; c.beginPath(); c.moveTo(0, Y(0)); c.lineTo(W, Y(0)); c.stroke();
    const g = c.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#3fb95055"); g.addColorStop(1, "#3fb95000");
    c.beginPath(); c.moveTo(0, Y(0)); series.forEach((v, i) => c.lineTo(X(i), Y(v))); c.lineTo(W, Y(0)); c.fillStyle = g; c.fill();
    c.beginPath(); series.forEach((v, i) => i ? c.lineTo(X(i), Y(v)) : c.moveTo(X(i), Y(v))); c.strokeStyle = "#3fb950"; c.lineWidth = 2 * dpr; c.stroke();
  }
  function quad(cvs) {
    if (!cvs) return; const dpr = devicePixelRatio || 1, W = cvs.width = cvs.clientWidth * dpr, H = cvs.height = 340 * dpr, c = cvs.getContext("2d"), p = 30 * dpr;
    c.clearRect(0, 0, W, H);
    c.fillStyle = "#f8514915"; c.fillRect(p, p, (W - 2 * p) / 2, (H - 2 * p) / 2);
    c.strokeStyle = "#1b232e"; c.lineWidth = dpr; c.strokeRect(p, p, W - 2 * p, H - 2 * p);
    c.beginPath(); c.moveTo(W / 2, p); c.lineTo(W / 2, H - p); c.moveTo(p, H / 2); c.lineTo(W - p, H / 2); c.stroke();
    c.fillStyle = "#f85149"; c.font = `${12 * dpr}px sans-serif`; c.fillText("⚠ confidently wrong", p + 8 * dpr, p + 16 * dpr);
    c.fillStyle = "#6b7684"; c.fillText("correct & confident", W - p - 150 * dpr, H - p - 8 * dpr);
    const X = (v) => p + v * (W - 2 * p), Y = (v) => H - p - v * (H - 2 * p);
    for (const r of state.receipts.slice(0, 150)) {
      const perf = r.per_axis?.performance?.p_fail || 0, oc = (r.signals || []).find((s) => s.name === "overconfidence");
      const conf = oc ? oc.score : 1 - perf * 0.5;
      c.beginPath(); c.arc(X(1 - perf), Y(conf), 4.5 * dpr, 0, 7); c.fillStyle = ACT[r.action] || "#888"; c.globalAlpha = .85; c.fill(); c.globalAlpha = 1;
    }
  }
  function bars(cvs, rows, valKey, fmt) {
    if (!cvs) return; const dpr = devicePixelRatio || 1, W = cvs.width = cvs.clientWidth * dpr, H = cvs.height = (rows.length * 34 + 10) * dpr, c = cvs.getContext("2d");
    c.clearRect(0, 0, W, H); const mx = Math.max(...rows.map((r) => Math.abs(r[valKey])), 1e-9), lab = 150 * dpr;
    rows.forEach((r, i) => { const y = (i * 34 + 8) * dpr, bw = (W - lab - 90 * dpr) * (Math.abs(r[valKey]) / mx);
      c.fillStyle = "#93a1b1"; c.font = `${12 * dpr}px sans-serif`; c.fillText(r.name, 0, y + 16 * dpr);
      c.fillStyle = r[valKey] < 0 ? "#3fb950" : "#46d9e6"; c.fillRect(lab, y, bw, 16 * dpr);
      c.fillStyle = "#e8eef5"; c.fillText(fmt(r[valKey]), lab + bw + 8 * dpr, y + 16 * dpr); });
  }

  /* ---- job runner (progress + ETA) ------------------------------------------------------------- */
  async function runJob(startUrl, wrapId, onDone) {
    const wrap = $("#" + wrapId); wrap.classList.add("on");
    const bar = $(".progress > div", wrap), meta = $(".progress-meta", wrap);
    try {
      const j = await jpost(startUrl); let s = j;
      while (s.status === "running") {
        await new Promise((r) => setTimeout(r, 350));
        s = await jget(`/v1/oversight/jobs/${j.id}`);
        bar.style.width = (s.progress * 100).toFixed(1) + "%";
        meta.innerHTML = `<span>${esc(s.message || s.kind)}</span><span>${(s.progress * 100).toFixed(0)}% · ETA ${fmtEta(s.eta_seconds)}</span>`;
      }
      if (s.status === "error") { toast("Job failed", s.error, "err"); }
      else { bar.style.width = "100%"; meta.innerHTML = `<span>done in ${s.elapsed_seconds}s</span><span>100%</span>`; onDone(s.result); }
    } catch (e) { toast("Job failed", String(e), "err"); }
  }

  /* ---- receipt drawer -------------------------------------------------------------------------- */
  function openDrawer(r) {
    const axes = Object.entries(r.per_axis || {}).map(([a, o]) =>
      `<div style="margin:6px 0"><div style="display:flex;justify-content:space-between"><span>${a}</span><b class="num">${o.p_fail.toFixed(3)}</b></div><div class="axis-bar"><div style="width:${(o.p_fail * 100).toFixed(0)}%;background:${AXC[a]}"></div></div></div>`).join("");
    const trace = (r.trace || []).filter((s) => s.tier > 0).map((s) =>
      `${s.ran ? "RAN " : "SKIP"} T${s.tier} ${s.detector.padEnd(20)} voi=${(s.voi || 0).toFixed(5)} vs cost=${(s.check_cost || 0).toFixed(5)}  (${s.reason})`).join("\n") || "all resolved at T0 — no higher-tier check was worth its cost";
    const opps = (r.cost_opportunities || []).filter((o) => o.recommendation !== "none").map((o) => `${o.recommendation} via ${o.name} → saved $${(o.estimated_savings_usd || 0).toFixed(5)}`).join("<br>") || "—";
    $("#drawer-body").innerHTML = `
      <h3>${r.request_id} <span class="badge b-${r.action}">${r.action.replace("_", "-")}</span></h3>
      <div class="faint" style="margin-bottom:12px">${r.use_case} · ${r.policy_id}</div>
      <div class="kv"><span class="k">stopping reason</span><span>${esc(r.stopping_reason)}</span>
        <span class="k">expected loss</span><span class="num">${(r.expected_loss_before||0).toFixed(4)} → ${(r.expected_loss_after||0).toFixed(4)}</span>
        <span class="k">P&amp;L</span><span class="num">saved ${usd(r.pnl.cost_saved_usd)} · spend ${usd(r.pnl.safety_spend_usd)} · <b class="${r.pnl.net_usd<0?"neg":"pos"}">net ${usd(r.pnl.net_usd)}</b></span></div>
      <h4 style="margin:16px 0 6px">Per-axis verdict</h4>${axes}
      <h4 style="margin:16px 0 6px">Value-of-information trace <span class="info" title="Which checks ran vs were skipped, and why — the audit of the economic decision">i</span></h4><div class="trace">${esc(trace)}</div>
      <h4 style="margin:16px 0 6px">Cost opportunities</h4><div class="muted">${opps}</div>
      ${r.repaired_output ? `<h4 style="margin:16px 0 6px">Delivered to user</h4><div class="trace">${esc(r.repaired_output)}</div>` : ""}
      <h4 style="margin:16px 0 6px">Tamper-evident chain</h4><div class="hash">self ${r.hash_self}<br>prev ${r.hash_prev || "genesis"}</div>`;
    $("#drawer").classList.add("on"); $("#overlay").classList.add("on");
  }
  function closeDrawer() { $("#drawer").classList.remove("on"); $("#overlay").classList.remove("on"); }

  /* ---- views ----------------------------------------------------------------------------------- */
  const kpi = (k, v, cls = "", foot = "", info = "") => `<div class="kpi"><div class="k">${k}${info ? ` <span class="info" title="${esc(info)}">i</span>` : ""}</div><div class="v ${cls}">${v}</div>${foot ? `<div class="foot">${foot}</div>` : ""}</div>`;
  const feedRow = (r) => { const [ax, p] = worst(r); return `<div class="rowitem" data-id="${r.request_id}"><span class="badge b-${r.action}">${r.action.replace("_", "-")}</span><div style="min-width:0"><div>${(r.use_case||"").replace("_"," ")} · ${ax||"—"} <span class="num">${p.toFixed(2)}</span></div><div class="rid">${r.request_id} · ${esc(r.stopping_reason||"")}</div></div><div class="num ${r.pnl.net_usd<0?"neg":"pos"}">${usd(r.pnl.net_usd)}</div></div>`; };

  const VIEWS = {
    overview: { title: "Overview", sub: "One verdict across performance, cost, and responsibility — in real time", render(v) {
      const s = state.summary, net = s.net_usd || 0;
      v.innerHTML = `
        <div class="kpis">
          ${kpi("Decisions", s.requests || 0, "", "overseen inline")}
          ${kpi("Net oversight P&amp;L", usd(net), net < 0 ? "good" : "bad", net < 0 ? "self-funding" : "safety > savings", "Safety spend minus cost saved. Negative = oversight pays for itself.")}
          ${kpi("Cleared at T0", (s.cleared_at_t0_pct ?? 100) + "%", "", "free tier, ~0ms", "Share resolved by free checks — the fast path.")}
          ${kpi("Scrutiny", (s.scrutiny ?? 1).toFixed(2) + "×", "", "adaptive thermostat", "Auto-scales verification with recent risk.")}
          ${kpi("Escalations", s.by_action?.escalate || 0, "", "to a human")}
          ${kpi("Blocks", s.by_action?.block || 0, "", "unsafe / leaks")}
        </div>
        <div class="grid cols-2" style="margin-top:16px">
          <div class="card"><h3>Cumulative oversight P&amp;L</h3><p class="desc">Every point is a decision; below zero means the cost-axis savings are paying for the safety checks.</p><canvas class="spark" id="ov-spark"></canvas></div>
          <div class="card"><h3>Recent decisions</h3><p class="desc">Newest first — click any row for the full receipt.</p><div id="ov-feed" style="display:flex;flex-direction:column;gap:8px;max-height:250px;overflow:auto"></div></div>
        </div>
        <div class="explain" style="margin-top:16px"><h4>What am I looking at?</h4>
          ControlPlane sits in front of any model. For every response it decides <b>how much verification that response is worth</b> — buying the cheapest signal that could change the decision first, and letting cost-axis savings pay for the safety checks. Most responses clear instantly at the free tier; only the uncertain, high-stakes tail climbs to costly checks or a human. New here? Open <b>Getting started</b> in the sidebar.</div>`;
      spark($("#ov-spark", v), state.net);
      const f = $("#ov-feed", v); f.innerHTML = state.receipts.slice(0, 12).map(feedRow).join("") || `<div class="empty">No traffic yet — click “Send demo traffic”.</div>`;
    }},
    feed: { title: "Live feed", sub: "Every decision, as it happens — the audit trail behind each response", render(v) {
      v.innerHTML = `<div class="card"><div style="display:flex;gap:8px;margin-bottom:12px"><select id="f-action"><option value="">all actions</option>${["pass","annotate","auto_repair","escalate","block"].map(a=>`<option>${a}</option>`).join("")}</select><span class="grow"></span><span class="muted">click a row for the receipt</span></div><div id="feed-list" style="display:flex;flex-direction:column;gap:8px"></div></div>`;
      const draw = () => { const fa = $("#f-action", v).value; const rows = state.receipts.filter(r => !fa || r.action === fa); $("#feed-list", v).innerHTML = rows.slice(0, 200).map(feedRow).join("") || `<div class="empty">Nothing yet.</div>`; };
      $("#f-action", v).onchange = draw; draw();
    }},
    quadrant: { title: "Confidently-wrong map", sub: "The danger zone we exist to catch: sure of itself and wrong", render(v) {
      v.innerHTML = `<div class="card"><p class="desc">Each dot is a response, placed by estimated correctness (x) and model confidence (y), coloured by action. The shaded top-left — high confidence, low correctness — is where hallucinations do damage.</p><canvas id="q" style="width:100%"></canvas>
      <div class="legend">${Object.entries(ACT).map(([k,c])=>`<span><i class="sw" style="background:${c}"></i>${k.replace("_","-")}</span>`).join("")}<span style="margin-left:auto">x → correctness · y → confidence</span></div></div>`;
      quad($("#q", v));
    }},
    pnl: { title: "Oversight P&L", sub: "Safer AND cheaper — a negative price tag, measured not asserted", render(v) {
      const s = state.summary;
      v.innerHTML = `<div class="kpis" style="grid-template-columns:repeat(3,1fr)">
          ${kpi("Cost saved", usd(s.cost_saved_usd||0), "good", "route-down + cache")}
          ${kpi("Safety spend", usd(s.safety_spend_usd||0), "", "checks that ran")}
          ${kpi("Net", usd(s.net_usd||0), (s.net_usd||0)<0?"good":"bad", (s.net_usd||0)<0?"self-funding":"")}
        </div>
        <div class="card" style="margin-top:16px"><h3>Cumulative net</h3><canvas class="spark" id="pnl-spark"></canvas></div>
        <div class="explain" style="margin-top:16px"><h4>Why can oversight be cheaper than nothing?</h4>
          The same layer that catches errors also finds cheaper paths to the same answer — routing an easy question to a small model, serving a repeat from cache. Those savings are booked against what the safety checks cost. When savings win, the net goes negative: you get safety <i>and</i> a lower bill. Prices are sourced (see docs/EVIDENCE.md).</div>`;
      spark($("#pnl-spark", v), state.net);
    }},
    benchmark: { title: "Latency & scale", sub: "Does oversight slow the model down? Measure it.", render(v) {
      v.innerHTML = `<div class="card"><h3>Latency / throughput benchmark</h3><p class="desc">Runs N requests through the local cascade and measures the wall-clock oversight <i>adds</i> per request (the model call is excluded). The T2 judge is off here — it fires only on the uncertain tail.</p>
        <div style="display:flex;gap:8px;align-items:center"><label class="muted">requests</label><select id="b-n"><option>1000</option><option selected>2000</option><option>5000</option></select><label class="muted">weekly volume</label><select id="b-w"><option>10000</option><option selected>50000</option><option>250000</option></select><button class="primary" id="b-run">Run benchmark</button></div>
        <div class="progress-wrap" id="b-prog"><div class="progress"><div></div></div><div class="progress-meta"></div></div>
        <div id="b-out" style="margin-top:16px"></div></div>`;
      $("#b-run", v).onclick = () => { const n = $("#b-n", v).value, w = $("#b-w", v).value; $("#b-out", v).innerHTML = "";
        runJob(`/v1/oversight/jobs/benchmark?n=${n}&weekly_volume=${w}`, "b-prog", (r) => {
          const L = r.added_latency_ms, S = r.at_scale;
          $("#b-out", v).innerHTML = `<div class="kpis" style="grid-template-columns:repeat(4,1fr)">
            ${kpi("p50 added", L.p50 + " ms", "good")}${kpi("p95 added", L.p95 + " ms", "good")}${kpi("p99 added", L.p99 + " ms")}${kpi("throughput", r.throughput_rps.toLocaleString() + " rps")}</div>
            <div class="grid cols-2" style="margin-top:14px"><div class="card"><h3>At enterprise scale</h3><p class="desc">Extrapolated from the measured per-request economics — simulated traffic at sourced prices, not billing.</p>
              <div class="kv"><span class="k">weekly volume</span><span class="num">${S.weekly_volume.toLocaleString()}</span><span class="k">weekly net</span><span class="num ${S.weekly_net_usd<0?"neg":"pos"}">${usd(S.weekly_net_usd)}</span><span class="k">annual net</span><span class="num ${S.annual_net_usd<0?"neg":"pos"}">${usd(S.annual_net_usd)}</span><span class="k">cleared @ T0</span><span class="num">${r.pct_cleared_at_t0}%</span></div></div>
              <div class="explain"><h4>Reading</h4>Sub-millisecond added latency on the common path and ${r.pct_cleared_at_t0}% cleared at the free tier means the safe majority is never slowed. ${esc(r.judge_note)}.</div></div>`;
          toast("Benchmark complete", `p95 ${L.p95}ms · ${r.throughput_rps} rps`, "ok");
        }); };
    }},
    replay: { title: "What-If replay", sub: "Re-run the same workload under different risk appetites — the proof engine", render(v) {
      v.innerHTML = `<div class="card"><p class="desc">Oversight-off carries the full risk at zero savings; each ControlPlane policy trades escalations for lower residual risk — and every one is net-negative.</p><button class="primary" id="r-run">Run replay</button><div id="r-out" style="margin-top:16px"></div></div>`;
      $("#r-run", v).onclick = async () => { $("#r-out", v).innerHTML = `<div class="empty">Running…</div>`;
        try { const d = await jpost("/v1/oversight/replay"); const rows = d.scenarios;
          $("#r-out", v).innerHTML = `<table class="tbl"><thead><tr><th>scenario</th><th class="num">residual risk</th><th class="num">risk ↓</th><th class="num">net $</th><th class="num">escalations</th></tr></thead><tbody>${rows.map(s=>`<tr><td>${s.name}${s.self_funding?' <span class="badge b-pass">self-funding</span>':""}</td><td class="num">${s.residual_risk.toFixed(4)}</td><td class="num">${s.risk_reduction_pct.toFixed(0)}%</td><td class="num ${s.net_usd<0?"neg":"pos"}">${usd(s.net_usd)}</td><td class="num">${(s.escalation_rate*100).toFixed(0)}%</td></tr>`).join("")}</tbody></table>`;
          toast("Replay complete", `${rows.length} scenarios`, "ok");
        } catch (e) { toast("Replay failed", String(e), "err"); } };
    }},
    agents: { title: "Agent oversight", sub: "Catching compounding risk across a multi-step agent", render(v) {
      v.innerHTML = `<div class="card"><p class="desc">A support agent hallucinates a “365-day premium refund” no source supports, then loops to confirm its own invention. The auditor watches risk compound step-by-step and aborts before the wrong answer reaches the user — saving the wasted steps.</p><button class="primary" id="a-run">Run agent trajectory</button><div id="a-out" style="margin-top:16px"></div></div>`;
      $("#a-run", v).onclick = async () => { $("#a-out", v).innerHTML = `<div class="empty">Running…</div>`;
        try { const r = await jpost("/v1/oversight/agent-demo"); const AC = { continue: ["#3fb950","CONTINUE"], escalate: ["#d9a221","FLAG"], abort: ["#f85149","ABORT"] };
          $("#a-out", v).innerHTML = `<div class="faint" style="margin-bottom:8px">TASK · ${esc(r.task)}</div><div class="steps">${r.verdicts.map(x=>{const [c,l]=AC[x.action]||["#888",x.action]; const loop=x.loop_repeat>=2?` · loop x${x.loop_repeat}`:"";return `<div class="step" style="border-left-color:${c}"><span class="badge" style="background:${c}22;color:${c}">${l}</span><div><b>step ${x.index}</b> · risk <span class="num">${x.step_risk.toFixed(2)}</span> · cumulative <span class="num">${x.cumulative_risk.toFixed(2)}</span>${loop}<div class="rid">${esc(x.reason)}</div></div><div class="rid">${x.receipt_id}</div></div>`;}).join("")}</div>
          <div class="explain" style="margin-top:14px"><h4 style="color:${r.aborted_at!=null?"#d9a221":"#3fb950"}">${r.final_action.toUpperCase()}</h4>${esc(r.summary)}. Executed ${r.n_steps_executed}/${r.n_steps_planned} steps · ${r.wasted_usd>0?`saved ${usd(r.wasted_usd)} in avoided agent spend`:""} · the wrong answer never reached the user.</div>`;
          toast("Agent trajectory audited", r.final_action, "ok");
        } catch (e) { toast("Agent demo failed", String(e), "err"); } };
    }},
    compliance: { title: "Compliance", sub: "Receipts → EU AI Act / ISO 42001 / NIST AI RMF evidence", render(v) {
      v.innerHTML = `<div class="card"><p class="desc">Governance stays policy-as-config; auditor-ready evidence is generated on demand from the tamper-evident receipts. An evidence aid, not a legal certification.</p><button class="primary" id="c-run">Generate evidence pack</button> <a class="btn" href="/v1/oversight/compliance.md" target="_blank">⬇ download Markdown</a><div id="c-out" style="margin-top:16px"></div></div>`;
      $("#c-run", v).onclick = async () => { try { const p = await jget("/v1/oversight/compliance");
        $("#c-out", v).innerHTML = `<table class="tbl"><thead><tr><th>framework</th><th>control</th><th>evidence</th><th>status</th></tr></thead><tbody>${p.controls.map(c=>`<tr><td>${c.framework}</td><td>${c.control}</td><td class="muted" style="font-size:12px">${esc(c.evidence)}</td><td><span class="badge ${c.status==="evidenced"?"b-pass":"b-escalate"}">${c.status}</span></td></tr>`).join("")}</tbody></table>`;
        toast("Compliance pack generated", `${p.decisions} decisions covered`, "ok"); } catch (e) { toast("Failed", String(e), "err"); } };
    }},
    detectors: { title: "Detectors & models", sub: "The tiered stack: cheap first, model on the tail", render(v) {
      const m = state.summary.models || {};
      v.innerHTML = `<div class="kpis" style="grid-template-columns:repeat(3,1fr)">
          ${kpi("Groundedness", m.groundedness || "—", m.groundedness?.includes("hhem")?"good":"", "performance axis")}
          ${kpi("PII", m.pii || "—", m.pii?.includes("presidio")?"good":"", "responsibility axis")}
          ${kpi("Judge (T2)", m.judge || "disabled", m.judge && m.judge!=="disabled"?"good":"", "uncertain tail only")}</div>
        <div class="card" style="margin-top:16px"><h3>Tiered cascade</h3><table class="tbl"><thead><tr><th>tier</th><th>axis</th><th>detector</th><th>upgrade path</th></tr></thead><tbody>
          <tr><td>T0</td><td>performance</td><td>overconfidence, lexical groundedness, self-consistency</td><td>SEP / semantic entropy</td></tr>
          <tr><td>T1</td><td>performance</td><td>HHEM-2.1 groundedness <span class="tag">model</span></td><td>MiniCheck / Lynx</td></tr>
          <tr><td>T2</td><td>performance</td><td>LLM-as-judge <span class="tag">VoI-gated</span></td><td>hosted or local (Ollama)</td></tr>
          <tr><td>T0</td><td>responsibility</td><td>regex/Luhn PII, prompt-injection, unsafe-content</td><td>Presidio · PromptGuard-2 · Llama Guard 4</td></tr>
          <tr><td>T0</td><td>cost</td><td>model-overkill (route-down), semantic cache</td><td>learned router · embedding cache</td></tr>
        </tbody></table><p class="desc" style="margin-top:12px">On real HaluEval data the cheap lexical check scores F1 0.30; the VoI cascade climbing to HHEM on the uncertain tail reaches F1 0.76 (see docs/EVIDENCE.md). Enable models with the <span class="tag">[ml]</span> extra or a judge backend.</p></div>`;
    }},
    help: { title: "Getting started", sub: "What this is and how to read it", render(v) {
      v.innerHTML = `<div class="grid cols-2">
        <div class="card"><h3>The one-line integration</h3><p class="desc">Point any OpenAI client at The Tower — nothing else changes:</p>
          <div class="trace">client = OpenAI(\n  base_url="http://localhost:8000/v1",\n  api_key="anything",\n)</div>
          <p class="desc" style="margin-top:10px">Every response is then overseen inline: passed, annotated, auto-repaired from source, escalated to a human, or blocked — each with a signed receipt.</p></div>
        <div class="card"><h3>The three coupled risks</h3>
          <div class="kv"><span class="k" style="color:${AXC.performance}">performance</span><span>wrong, or confidently wrong</span><span class="k" style="color:${AXC.cost}">cost</span><span>a cheaper path to the same quality (this funds the rest)</span><span class="k" style="color:${AXC.responsibility}">responsibility</span><span>unsafe, biased, or leaking data</span></div>
          <p class="desc" style="margin-top:10px">One verdict across all three — not three separate tools.</p></div>
        <div class="card"><h3>Glossary</h3><div class="kv">
          <span class="k">VoI</span><span>value of information — run a check only if it could change the decision</span>
          <span class="k">Net P&amp;L</span><span>safety spend − cost saved; negative = self-funding</span>
          <span class="k">Cleared @ T0</span><span>resolved by free checks (the fast path)</span>
          <span class="k">Escalate</span><span>held for a human — the uncertain, high-stakes tail</span>
          <span class="k">Receipt</span><span>the hash-chained audit record of one decision</span></div></div>
        <div class="card"><h3>A 60-second tour</h3><ol class="desc" style="margin:0;padding-left:18px;line-height:1.9">
          <li>Click <b>Send demo traffic</b> (top right).</li>
          <li><b>Overview</b>: watch the P&amp;L go negative.</li>
          <li><b>Live feed</b>: click a row → see the VoI trace.</li>
          <li><b>Latency &amp; scale</b>: run the benchmark.</li>
          <li><b>Agent oversight</b>: watch a looping agent get stopped.</li>
          <li><b>Compliance</b>: generate the evidence pack.</li></ol></div></div>`;
    }},
  };
  const LIVE = new Set(["overview", "feed", "quadrant", "pnl"]);

  /* ---- router --------------------------------------------------------------------------------- */
  function render() { const V = VIEWS[state.view] || VIEWS.overview; $("#view-title").textContent = V.title; $("#view-sub").textContent = V.sub; V.render($("#view")); bindRows(); }
  function bindRows() { document.querySelectorAll(".rowitem[data-id]").forEach((r) => r.onclick = () => openDrawer(state.byId[r.dataset.id])); }
  function go(view) { state.view = view; document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === view)); location.hash = view; render(); }

  /* ---- live stream ---------------------------------------------------------------------------- */
  function connect() { const es = new EventSource("/v1/oversight/stream");
    es.onmessage = (e) => { if (e.data.startsWith(":")) return; const m = JSON.parse(e.data); if (m.type === "receipt") addReceipt(m.receipt); else if (m.type === "summary") applySummary(m.summary); };
    es.onerror = () => { es.close(); setTimeout(connect, 2000); };
  }

  function init() {
    document.querySelectorAll(".nav-item").forEach((n) => n.onclick = () => go(n.dataset.view));
    $("#overlay").onclick = closeDrawer;
    $("#btn-traffic").onclick = async () => { const b = $("#btn-traffic"); b.disabled = true; b.textContent = "running…"; try { await jpost("/v1/oversight/simulate"); toast("Demo traffic sent", "9 requests overseen", "ok"); } catch (e) { toast("Failed", String(e), "err"); } b.disabled = false; b.textContent = "▶ Send demo traffic"; };
    jget("/healthz").then((h) => { state.summary.upstream = h.upstream; }).catch(() => {});
    jget("/v1/oversight/summary").then((s) => applySummary({ ...s, upstream: state.summary.upstream })).catch(() => {});
    jget("/v1/oversight/receipts?limit=80").then((d) => { d.receipts.slice().reverse().forEach(addReceipt); render(); }).catch(() => {});
    go((location.hash || "#overview").slice(1) in VIEWS ? (location.hash).slice(1) : "overview");
    connect();
    window.addEventListener("resize", () => { if (LIVE.has(state.view)) render(); });
  }
  document.addEventListener("DOMContentLoaded", init);
  return { closeDrawer };
})();
