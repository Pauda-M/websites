// PM Research Ledger side panel. Read-only: fetches ledger.json + prices.json
// from the on-server dashboard and renders a compact view. PAPER MODE ONLY.

const ENDPOINTS = [
  "http://192.168.50.88:8794", // LAN
  "http://100.125.213.17:8794" // Tailscale
];
const REFRESH_MS = 60_000;

const pct = (x) => (x == null ? "—" : (100 * x).toFixed(1).replace(/\.0$/, "") + "%");
const usd = (x) => (x == null ? "—" : "$" + Number(x).toLocaleString("en-US"));
const signed = (x) => (x >= 0 ? "+" : "−") + usd(Math.abs(x));

const STATUS = {
  OPEN: { color: "var(--warning)", label: "OPEN" },
  WATCHING_NO_POSITION: { color: "var(--accent)", label: "WATCHING" },
  RESOLVED_WIN: { color: "var(--good)", label: "WIN" },
  RESOLVED_LOSS: { color: "var(--critical)", label: "LOSS" },
  VOIDED: { color: "var(--text-muted)", label: "VOIDED (stale fill)" }
};

let base = localStorage.getItem("pm_base") || null;

async function fetchJson(b, path) {
  const r = await fetch(`${b}${path}?_=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function pickBase() {
  const order = base ? [base, ...ENDPOINTS.filter((e) => e !== base)] : ENDPOINTS;
  for (const b of order) {
    try {
      await fetchJson(b, "/ledger.json");
      localStorage.setItem("pm_base", b);
      return b;
    } catch (_) { /* try next */ }
  }
  throw new Error("no endpoint reachable (LAN + Tailscale both failed)");
}

function markFor(pos, q) {
  if (!q || q.error) return null;
  if (pos.side === "NO") {
    const a = q.yes_ask ?? q.last;
    return a == null ? null : 1 - a;
  }
  const b = q.yes_bid ?? q.last;
  return b == null ? null : b;
}

function unrealized(e, q) {
  const pos = e.paper_position;
  if (!pos || e.status !== "OPEN") return null;
  const mark = markFor(pos, q);
  if (mark == null) return null;
  return pos.contracts * (mark - pos["entry_price_" + pos.side.toLowerCase()]);
}

// DOM builders (no innerHTML with remote strings — ledger text is data)
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function row(label, value) {
  const r = el("div", "row");
  r.append(el("span", null, label), el("span", "v", value));
  return r;
}

function render(ledger, prices) {
  const live = prices?.markets || {};
  const es = ledger.entries || [];
  const open = es.filter((e) => e.status === "OPEN");
  const totalU = es.reduce((s, e) => s + (unrealized(e, live[e.id]) ?? 0), 0);

  const total = document.getElementById("total");
  total.replaceChildren();
  const box = el("div", "total");
  box.append(el("div", "label", "Unrealized P&L (paper)"));
  box.append(el("div", "value", open.length ? signed(totalU) : "$0"));
  box.append(el("div", "note",
    `${open.length} open · ${es.length} tracked · bankroll ${usd(ledger.meta?.paper_bankroll_usd)} (paper)`));
  total.append(box);

  const cards = document.getElementById("cards");
  cards.replaceChildren();
  for (const e of es) {
    const q = live[e.id];
    const c = el("div", "card");
    const s = STATUS[e.status] || { color: "var(--text-muted)", label: e.status };
    const badge = el("span", "badge");
    const dot = el("span", "dot");
    dot.style.background = s.color;
    badge.append(dot, document.createTextNode(s.label));
    c.append(badge);
    c.append(el("div", "q", e.market));
    if (q && !q.error) {
      c.append(row("Live YES bid/ask", `${pct(q.yes_bid)} / ${pct(q.yes_ask)}`));
    } else if (q?.error) {
      c.append(row("Live", "feed error"));
    }
    c.append(row("Agent estimate", pct(e.agent_probability_yes)));
    if (e.paper_position && e.status === "OPEN") {
      const p = e.paper_position;
      c.append(row("Position", `${p.contracts} × ${p.side} @ ${pct(p["entry_price_" + p.side.toLowerCase()])}`));
      const u = unrealized(e, q);
      if (u != null) c.append(row("Unrealized", signed(u)));
    } else if (e.verdict === "PASS") {
      c.append(row("Verdict", "PASS — no edge"));
    }
    c.append(row("Next check", e.next_check || "—"));
    cards.append(c);
  }

  const foot = document.getElementById("foot");
  foot.replaceChildren();
  foot.append(document.createTextNode(
    `Live feed ${prices?.as_of || "n/a"} UTC · polled every 5 min on-server · `));
  const a = el("a", null, "full dashboard");
  a.href = base + "/";
  a.target = "_blank";
  foot.append(a);
}

async function refresh() {
  const status = document.getElementById("status");
  try {
    base = await pickBase();
    const [ledger, prices] = await Promise.all([
      fetchJson(base, "/ledger.json"),
      fetchJson(base, "/prices.json").catch(() => null)
    ]);
    render(ledger, prices);
    status.className = "";
    status.textContent =
      `${base.includes("100.") ? "tailscale" : "lan"} · refreshed ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    status.className = "err";
    status.textContent = "offline: " + err.message;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
