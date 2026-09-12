"""Read-only web dashboard: detected pools ranked by heat.

Served by the watcher container itself (stdlib only). The page is a ranked
table of every pool that ever alerted, with a transparent 0-100 heat score,
a 24h liquidity sparkline per pool (from the snapshots table), and summary
tiles. Routes: "/" (HTML), "/api/pools" (JSON), "/healthz".

The server opens its own read-only SQLite connections per request (WAL allows
concurrent reads while the poll loop writes), so it never blocks alerting.
"""

from __future__ import annotations

import html
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import Config
from .fmt import fmt_age, fmt_int, fmt_pct, fmt_usd

log = logging.getLogger("rh_meme_watch.dashboard")

# Committed dark look (validated palette, dark steps).
_SURFACE = "#1a1a19"
_PANEL = "#232322"
_BORDER = "#383835"
_TEXT = "#ffffff"
_TEXT_2 = "#c3c2b7"
_ACCENT = "#3987e5"  # sequential blue (dark step): sparklines + heat bar fill
_STATUS = {
    "alerted": ("#0ca30c", "tracking"),
    "escalated": ("#fab219", "escalated"),
    "seen": ("#c3c2b7", "seen"),
}
_DUMP_COLOR = "#d03b3b"

# Thermal ramp for the heat bar: blue (cold) -> neutral -> burning red (hot).
_HEAT_COLD = (0x39, 0x87, 0xE5)
_HEAT_MID = (0x8A, 0x89, 0x84)
_HEAT_HOT = (0xE3, 0x49, 0x48)

HOT_THRESHOLD = 60
BURNING_THRESHOLD = 80


def thermal_color(heat: int) -> str:
    """Interpolated heat color: 0 = blue, 50 = neutral gray, 100 = burning red."""
    h = min(max(heat, 0), 100)
    if h <= 50:
        a, b, t = _HEAT_COLD, _HEAT_MID, h / 50.0
    else:
        a, b, t = _HEAT_MID, _HEAT_HOT, (h - 50) / 50.0
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def heat_score(
    vol_h1: float | None,
    buyers_h1: int | None,
    sellers_h1: int | None,
    liq_mult: float | None,
    esc_vol_h1: float,
) -> int:
    """Transparent 0-100 blend: 45% h1 volume vs the escalation threshold,
    25% buyer/seller flow (ratio 2 caps), 30% liquidity multiple since the
    first alert (0.5x floor, 3x caps)."""
    vol_c = min(max(vol_h1 or 0.0, 0.0) / esc_vol_h1, 1.0) if esc_vol_h1 > 0 else 0.0
    buyers = buyers_h1 or 0
    sellers = sellers_h1 or 0
    if buyers <= 0 and sellers <= 0:
        flow_c = 0.0
    else:
        ratio = buyers / sellers if sellers > 0 else 2.0
        flow_c = min(ratio, 2.0) / 2.0
    mult = liq_mult if liq_mult is not None else 1.0
    liq_c = min(max((mult - 0.5) / 2.5, 0.0), 1.0)
    return round(100 * (0.45 * vol_c + 0.25 * flow_c + 0.30 * liq_c))


def _ro_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except ValueError:
        return None


def collect(db_path: Path, cfg: Config, now: datetime) -> dict:
    """All dashboard data as plain values (also the /api/pools payload)."""
    pools: list[dict] = []
    counts = {"alerts_24h": 0, "escalations_24h": 0}
    try:
        conn = _ro_conn(db_path)
    except sqlite3.OperationalError:
        return {"generated_at": now.isoformat(), "pools": [], **counts}
    try:
        since = (now - timedelta(hours=24)).isoformat()
        for row in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM alerts WHERE ts >= ? GROUP BY kind", (since,)
        ):
            if row["kind"] in ("new", "new_stock"):
                counts["alerts_24h"] += row["n"]
            elif row["kind"] == "escalate":
                counts["escalations_24h"] += row["n"]

        for row in conn.execute(
            "SELECT * FROM pools WHERE first_alert_ts IS NOT NULL "
            "ORDER BY first_alert_ts DESC LIMIT 200"
        ):
            snaps = conn.execute(
                "SELECT ts, reserve, vol_h1, buys, sells, buyers, sellers, pct_h1 "
                "FROM snapshots WHERE address = ? AND ts >= ? ORDER BY ts",
                (row["address"], since),
            ).fetchall()
            latest = snaps[-1] if snaps else None
            first_liq = row["first_liq"]
            last_liq = latest["reserve"] if latest else row["last_liq"]
            liq_mult = (
                last_liq / first_liq if first_liq and first_liq > 0 and last_liq else None
            )
            vol_h1 = latest["vol_h1"] if latest else row["last_vol_h1"]
            buyers = latest["buyers"] if latest else None
            sellers = latest["sellers"] if latest else None
            dump = bool(
                buyers is not None
                and sellers
                and sellers > 0
                and buyers / sellers < 0.7
            ) or bool(first_liq and last_liq is not None and last_liq < 0.5 * first_liq)
            pools.append(
                {
                    "address": row["address"],
                    "symbol": row["symbol"],
                    "quote": row["quote"],
                    "dex": row["dex"],
                    "status": row["status"],
                    "first_alert_ts": row["first_alert_ts"],
                    "first_liq": first_liq,
                    "last_liq": last_liq,
                    "liq_mult": round(liq_mult, 2) if liq_mult is not None else None,
                    "vol_h1": vol_h1,
                    "buyers_h1": buyers,
                    "sellers_h1": sellers,
                    "pct_h1": latest["pct_h1"] if latest else None,
                    "dump_flag": dump,
                    "heat": heat_score(vol_h1, buyers, sellers, liq_mult, cfg.esc_vol_h1),
                    "spark": [s["reserve"] for s in snaps if s["reserve"] is not None],
                }
            )
    finally:
        conn.close()
    pools.sort(key=lambda p: p["heat"], reverse=True)
    return {"generated_at": now.isoformat(), **counts, "pools": pools}


def _spark_svg(values: list[float], width: int = 120, height: int = 26) -> str:
    if len(values) < 2:
        return (
            f'<svg width="{width}" height="{height}" role="img" aria-label="no history yet">'
            f'<line x1="0" y1="{height - 3}" x2="{width}" y2="{height - 3}" '
            f'stroke="{_BORDER}" stroke-width="2"/></svg>'
        )
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = []
    for i, v in enumerate(values):
        x = i * (width - 4) / (len(values) - 1) + 2
        y = height - 3 - (v - lo) / span * (height - 6)
        pts.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg width="{width}" height="{height}" role="img" aria-label="liquidity 24h">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{_ACCENT}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def _heartbeat_age(cfg: Config, now: datetime) -> float | None:
    try:
        mtime = cfg.heartbeat_path.stat().st_mtime
    except OSError:
        return None
    return now.timestamp() - mtime


def render_html(db_path: Path, cfg: Config, now: datetime) -> str:
    data = collect(db_path, cfg, now)
    hb = _heartbeat_age(cfg, now)
    hb_text = f"{hb:.0f}s ago" if hb is not None else "never"
    hb_ok = hb is not None and hb < 300
    hot = sum(1 for p in data["pools"] if p["heat"] >= HOT_THRESHOLD)

    def tile(label: str, value: str) -> str:
        return (
            f'<div class="tile"><div class="tile-v">{html.escape(value)}</div>'
            f'<div class="tile-l">{html.escape(label)}</div></div>'
        )

    rows_html = []
    for p in data["pools"]:
        name = html.escape(f"{p['symbol'] or '?'} / {p['quote'] or '?'}")
        url = html.escape(
            f"https://www.geckoterminal.com/robinhood/pools/{p['address']}", quote=True
        )
        color, label = _STATUS.get(p["status"], _STATUS["seen"])
        status = (
            f'<span class="dot" style="background:{color}"></span>{html.escape(label)}'
        )
        if p["dump_flag"]:
            status += ' <span class="rug">\U0001f4a3 rug risk</span>'
        alert_dt = _parse_ts(p["first_alert_ts"])
        age = fmt_age((now - alert_dt).total_seconds() / 60 if alert_dt else None)
        mult = f'x{p["liq_mult"]}' if p["liq_mult"] is not None else "n/a"
        heat = p["heat"]
        heat_color = thermal_color(heat)
        fire = " \U0001f525" if heat >= BURNING_THRESHOLD else ""
        rows_html.append(
            "<tr>"
            f'<td class="sym"><a href="{url}" target="_blank" rel="noopener">{name}</a>'
            f'<span class="dex">{html.escape(p["dex"] or "")}</span></td>'
            f"<td>{status}</td>"
            f"<td>{html.escape(age)}</td>"
            f'<td class="num">{html.escape(fmt_usd(p["first_liq"]))} &rarr; '
            f'{html.escape(fmt_usd(p["last_liq"]))} ({html.escape(mult)})</td>'
            f'<td class="num">{html.escape(fmt_usd(p["vol_h1"]))}</td>'
            f'<td class="num">{html.escape(fmt_int(p["buyers_h1"]))}/'
            f'{html.escape(fmt_int(p["sellers_h1"]))}</td>'
            f'<td class="num">{html.escape(fmt_pct(p["pct_h1"]))}</td>'
            f"<td>{_spark_svg(p['spark'])}</td>"
            f'<td class="heat"><div class="bar"><div class="fill" '
            f'style="width:{heat}%;background:{heat_color}"></div></div>'
            f'<span class="score">{heat}{fire}</span></td>'
            "</tr>"
        )
    if not rows_html:
        rows_html.append(
            '<tr><td colspan="9" class="empty">no alerted pools yet - '
            "rows appear after the first NEW alert</td></tr>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>rh-meme-watch</title>
<style>
  body {{ background:{_SURFACE}; color:{_TEXT}; margin:0; padding:20px 16px;
         font:14px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .sub {{ color:{_TEXT_2}; font-size:12px; margin-bottom:16px; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:18px; }}
  .tile {{ background:{_PANEL}; border:1px solid {_BORDER}; border-radius:8px;
           padding:10px 16px; min-width:110px; }}
  .tile-v {{ font-size:22px; font-weight:600; }}
  .tile-l {{ color:{_TEXT_2}; font-size:12px; }}
  .twrap {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; min-width:900px; }}
  th {{ text-align:left; color:{_TEXT_2}; font-weight:500; font-size:12px;
        border-bottom:1px solid {_BORDER}; padding:6px 10px; }}
  td {{ border-bottom:1px solid {_BORDER}; padding:7px 10px; vertical-align:middle; }}
  td.num {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .sym a {{ color:{_TEXT}; font-weight:600; text-decoration:none; }}
  .sym a:hover {{ text-decoration:underline; }}
  .dex {{ display:block; color:{_TEXT_2}; font-size:11px; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%;
          margin-right:5px; }}
  .heat {{ white-space:nowrap; }}
  .bar {{ display:inline-block; width:90px; height:8px; background:{_BORDER};
          border-radius:4px; overflow:hidden; vertical-align:middle; }}
  .fill {{ height:100%; border-radius:4px; }}
  .rug {{ color:{_DUMP_COLOR}; font-weight:600; white-space:nowrap; }}
  .score {{ margin-left:8px; font-variant-numeric:tabular-nums; }}
  .empty {{ color:{_TEXT_2}; text-align:center; padding:24px; }}
  .foot {{ color:{_TEXT_2}; font-size:12px; margin-top:14px; }}
</style></head><body>
<h1>rh-meme-watch</h1>
<div class="sub">robinhood chain pool radar &middot; heat = 45% vol1h/{html.escape(fmt_usd(cfg.esc_vol_h1))}
 + 25% buyer flow + 30% liq multiple &middot; bar color: blue = cooling &rarr; red = burning
 &middot; \U0001f4a3 rug risk = buyers/sellers &lt; 0.7 or liq &minus;50% vs first alert
 &middot; auto-refresh 60s</div>
<div class="tiles">
{tile("tracked pools", str(len(data["pools"])))}
{tile("alerts 24h", str(data["alerts_24h"]))}
{tile("escalations 24h", str(data["escalations_24h"]))}
{tile("hot now (heat >= " + str(HOT_THRESHOLD) + ")", str(hot))}
{tile("last cycle", hb_text if hb_ok else hb_text + " (stale)")}
</div>
<div class="twrap"><table>
<thead><tr><th>pool</th><th>status</th><th>alerted</th><th>liquidity first &rarr; now</th>
<th>vol 1h</th><th>buyers/sellers 1h</th><th>&Delta;1h</th><th>liq 24h</th><th>heat</th></tr></thead>
<tbody>{"".join(rows_html)}</tbody>
</table></div>
<div class="foot">generated {html.escape(now.strftime("%Y-%m-%d %H:%M:%S UTC"))} &middot;
snapshots kept 14 days &middot; <a style="color:{_ACCENT}" href="/api/pools">/api/pools</a></div>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "rh-meme-watch"

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        cfg: Config = self.server.cfg  # type: ignore[attr-defined]
        now = datetime.now(timezone.utc)
        try:
            if self.path.startswith("/api/pools"):
                payload = collect(cfg.db_path, cfg, now)
                self._send(
                    200, "application/json", json.dumps(payload, default=str).encode()
                )
            elif self.path.startswith("/healthz"):
                age = _heartbeat_age(cfg, now)
                ok = age is not None and age < 300
                body = json.dumps({"ok": ok, "heartbeat_age_sec": age}).encode()
                self._send(200 if ok else 503, "application/json", body)
            elif self.path == "/" or self.path.startswith("/index"):
                self._send(200, "text/html; charset=utf-8", render_html(cfg.db_path, cfg, now).encode())
            else:
                self._send(404, "text/plain", b"not found")
        except BrokenPipeError:
            pass
        except Exception:
            log.exception("dashboard request failed: %s", self.path)
            try:
                self._send(500, "text/plain", b"internal error")
            except Exception:
                pass

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        log.debug("http %s", fmt % args)


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_dashboard(cfg: Config, port: int | None = None) -> DashboardServer:
    """Start the dashboard HTTP server on a daemon thread and return it."""
    server = DashboardServer(("0.0.0.0", port if port is not None else cfg.dashboard_port), _Handler)
    server.cfg = cfg  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="dashboard", daemon=True)
    thread.start()
    log.info("dashboard listening on :%d", server.server_address[1])
    return server
