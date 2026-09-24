"""Premium dashboard skin for rh-meme-watch.

The watcher/rules/storage remain untouched.  This module only replaces the HTML
renderer and delegates HTTP serving/API/health routes to the proven dashboard
module, so alerting behaviour cannot be affected by presentation changes.
"""
from __future__ import annotations

import html
from datetime import datetime

from . import dashboard as legacy
from .config import Config
from .fmt import fmt_age, fmt_int, fmt_pct, fmt_usd
from .socials import platform_of

FOMO_URL = "https://fomo.family/"
GECKO_BASE = "https://www.geckoterminal.com/robinhood/pools/"


def _money(value: float | None) -> str:
    return fmt_usd(value)


def _age(ts: str | None, now: datetime) -> str:
    parsed = legacy._parse_ts(ts)
    if parsed is None:
        return "—"
    return fmt_age((now - parsed).total_seconds() / 60)


def _spark(values: list[float], width: int = 180, height: int = 54) -> str:
    if len(values) < 2:
        return (
            f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" aria-label="no history yet">'
            f'<path d="M3 {height - 8} H{width - 3}" stroke="rgba(255,255,255,.12)" stroke-width="2"/></svg>'
        )
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    points: list[str] = []
    for i, value in enumerate(values):
        x = 3 + i * (width - 6) / (len(values) - 1)
        y = height - 6 - (value - lo) / span * (height - 12)
        points.append(f"{x:.1f},{y:.1f}")
    line = " ".join(points)
    area = f"3,{height - 4} {line} {width - 3},{height - 4}"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" aria-label="24 hour liquidity">'
        '<defs><linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#5b8cff" stop-opacity=".32"/>'
        '<stop offset="1" stop-color="#5b8cff" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#sparkFill)"/>'
        f'<polyline points="{line}" fill="none" stroke="#79a3ff" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


_SOCIAL_LABELS = {
    "x": "\U0001d54f",
    "telegram": "TG",
    "discord": "DC",
    "farcaster": "FC",
    "zora": "ZORA",
}


def _social_links(pool: dict) -> str:
    """Clickable chips for the pool's socials, so the hype source is one click away.

    These URLs come from a third party, so only http(s) is rendered - a
    ``javascript:`` or ``data:`` href reaching the page would be an injection.
    """
    links = pool.get("socials") or []
    chips: list[str] = []
    for url in links:
        text = str(url).strip()
        if not text.lower().startswith(("http://", "https://")):
            continue
        platform = platform_of(text)
        label = _SOCIAL_LABELS.get(platform, platform[:4].upper() or "LINK")
        href = html.escape(text, quote=True)
        chips.append(
            f'<a class="social" href="{href}" target="_blank" '
            f'rel="noopener noreferrer nofollow" title="{href}">{html.escape(label)}</a>'
        )
    if chips:
        return "".join(chips)
    # "Nobody looked" and "looked, found nothing" are different claims, and only
    # the second is a finding. Showing NO SOCIAL for both told the operator the
    # whole board had been examined and rejected when most of it never had.
    if pool.get("socials_checked"):
        return '<span class="social social-none">NO SOCIAL</span>'
    return '<span class="social social-unknown">SOCIAL ?</span>'


def _mcap_since_detection(pool: dict) -> tuple[str, str, str]:
    """(at detection, now, multiple) - the "what has it done since I found it"
    number. Both readings are the meme side's FDV, so the multiple is real."""
    first = pool.get("first_mcap")
    last = pool.get("last_mcap")
    mult = pool.get("mcap_mult")
    if mult is None:
        mult_txt = "\u2014"
    elif mult >= 1:
        mult_txt = f"{mult:.2f}x"
    else:
        mult_txt = f"{mult:.2f}x"
    return fmt_usd(first), fmt_usd(last), mult_txt


def _mcap_block(pool: dict) -> str:
    at, now_, mult = _mcap_since_detection(pool)
    value = pool.get("mcap_mult")
    cls = "positive" if value and value >= 1 else ("negative" if value else "")
    return (
        f'<span class="mcap-leg"><i>MCAP AT ALERT</i><b>{html.escape(at)}</b></span>'
        f'<span class="mcap-arrow">\u2192</span>'
        f'<span class="mcap-leg"><i>NOW</i><b>{html.escape(now_)}</b></span>'
        f'<span class="mcap-mult {cls}">{html.escape(mult)}</span>'
    )


def _risk_badges(pool: dict) -> str:
    badges: list[str] = []
    status = str(pool.get("status") or "seen")
    if status == "escalated":
        badges.append('<span class="pill pill-amber">ESCALATED</span>')
    elif status == "alerted":
        badges.append('<span class="pill pill-green">TRACKING</span>')
    else:
        badges.append('<span class="pill">SEEN</span>')

    lock = str(pool.get("liq_lock") or "unproven")
    if lock == "locked":
        badges.append('<span class="pill pill-green">LIQ HELD</span>')
    elif lock == "pulling":
        badges.append('<span class="pill pill-red">LIQ PULL</span>')
    else:
        badges.append('<span class="pill">LIQ UNPROVEN</span>')

    custody = str(pool.get("custody") or "unchecked")
    if custody == "single custodian":
        badges.append('<span class="pill pill-red">1 CUSTODIAN</span>')
    elif custody == "burned":
        badges.append('<span class="pill pill-green">LP BURNED</span>')
    elif custody == "dispersed":
        badges.append('<span class="pill pill-green">DISPERSED</span>')

    momentum = str(pool.get("momentum") or "unproven")
    if momentum == "accelerating":
        change = pool.get("vol_change_pct")
        suffix = f" {change:+.0f}%" if change is not None else ""
        badges.append(f'<span class="pill pill-green">ACCELERATING{suffix}</span>')
    elif momentum == "fading":
        badges.append('<span class="pill pill-amber">FADING</span>')

    if pool.get("dump_flag"):
        badges.append('<span class="pill pill-red">RUG RISK</span>')
    return "".join(badges)


def _heat_class(heat: int) -> str:
    if heat >= legacy.BURNING_THRESHOLD:
        return "hot"
    if heat >= legacy.HOT_THRESHOLD:
        return "warm"
    return "cool"


def _initials(symbol: str) -> str:
    """Escape after slicing; slicing the escaped string would halve an entity."""
    return html.escape(symbol[:2] or "?")


def _hero_card(pool: dict, now: datetime, rank: int) -> str:
    raw_symbol = str(pool.get("symbol") or "?")
    symbol = html.escape(raw_symbol)
    quote = html.escape(str(pool.get("quote") or "?"))
    address = html.escape(str(pool.get("address") or ""), quote=True)
    gecko = html.escape(GECKO_BASE + str(pool.get("address") or ""), quote=True)
    heat = int(pool.get("heat") or 0)
    buyers = int(pool.get("buyers_h1") or 0)
    sellers = int(pool.get("sellers_h1") or 0)
    flow = buyers / max(sellers, 1)
    change = pool.get("pct_h1")
    change_txt = fmt_pct(change)
    change_cls = "positive" if (change or 0) >= 0 else "negative"
    return f"""
<article class="opportunity {_heat_class(heat)}">
  <div class="op-top">
    <span class="rank">#{rank}</span>
    <div class="token-mark">{_initials(raw_symbol)}</div>
    <div class="op-name"><strong>{symbol}</strong><span>/{quote} · {html.escape(str(pool.get('dex') or ''))}</span></div>
    <div class="heat-ring" style="--heat:{heat}"><b>{heat}</b><small>HEAT</small></div>
  </div>
  <div class="op-badges">{_risk_badges(pool)}</div>
  <div class="socials">{_social_links(pool)}</div>
  <div class="op-grid">
    <div><span>Liquidity</span><b>{html.escape(_money(pool.get('last_liq')))}</b><small>{html.escape(str(pool.get('liq_mult') or '—'))}x vs alert</small></div>
    <div><span>Volume 1h</span><b>{html.escape(_money(pool.get('vol_h1')))}</b><small>{buyers}/{sellers} buyers/sellers</small></div>
    <div><span>Move 1h</span><b class="{change_cls}">{html.escape(change_txt)}</b><small>flow {flow:.2f}x</small></div>
  </div>
  <div class="mcap-row">{_mcap_block(pool)}</div>
  <div class="mini-chart">{_spark(pool.get('spark') or [])}</div>
  <div class="actions">
    <a class="btn btn-primary" href="{FOMO_URL}" target="_blank" rel="noopener noreferrer">Open Fomo ↗</a>
    <a class="btn" href="{gecko}" target="_blank" rel="noopener noreferrer">Chart</a>
    <button class="btn copy" data-copy="{address}" title="Copy pool contract address">Copy pool CA</button>
  </div>
  <div class="op-foot"><span>alerted {_age(pool.get('first_alert_ts'), now)}</span><span>Fomo opens the trading app; use token search there if no direct deep link is available.</span></div>
</article>"""


def _table_row(pool: dict, now: datetime) -> str:
    raw_symbol = str(pool.get("symbol") or "?")
    symbol = html.escape(raw_symbol)
    quote = html.escape(str(pool.get("quote") or "?"))
    address = html.escape(str(pool.get("address") or ""), quote=True)
    gecko = html.escape(GECKO_BASE + str(pool.get("address") or ""), quote=True)
    heat = int(pool.get("heat") or 0)
    buyers = int(pool.get("buyers_h1") or 0)
    sellers = int(pool.get("sellers_h1") or 0)
    change = pool.get("pct_h1")
    change_cls = "positive" if (change or 0) >= 0 else "negative"
    mult = f"{pool['liq_mult']:.2f}x" if pool.get("liq_mult") is not None else "—"
    return f"""
<tr>
  <td>
    <div class="asset"><span class="token-mark small">{_initials(raw_symbol)}</span><div><strong>{symbol}</strong><span>/{quote} · {html.escape(str(pool.get('dex') or ''))}</span></div></div>
  </td>
  <td><div class="badges">{_risk_badges(pool)}</div><div class="socials">{_social_links(pool)}</div></td>
  <td class="mono">{html.escape(_age(pool.get('first_alert_ts'), now))}</td>
  <td class="mono"><strong>{html.escape(_money(pool.get('last_liq')))}</strong><span class="secondary">{mult} vs alert</span></td>
  <td class="mono"><strong>{html.escape(_money(pool.get('last_mcap')))}</strong><span class="secondary">{html.escape(_money(pool.get('first_mcap')))} at alert \u00b7 {html.escape(_mcap_since_detection(pool)[2])}</span></td>
  <td class="mono"><strong>{html.escape(_money(pool.get('vol_h1')))}</strong><span class="secondary">{buyers}/{sellers}</span></td>
  <td class="mono {change_cls}">{html.escape(fmt_pct(change))}</td>
  <td>{_spark(pool.get('spark') or [], 130, 42)}</td>
  <td><div class="heat-cell"><span>{heat}</span><div><i style="width:{heat}%"></i></div></div></td>
  <td><div class="row-actions"><a href="{FOMO_URL}" target="_blank" rel="noopener noreferrer">Fomo ↗</a><a href="{gecko}" target="_blank" rel="noopener noreferrer">Chart</a><button class="copy-icon" data-copy="{address}" title="Copy pool CA">CA</button></div></td>
</tr>"""


def render_html(db_path, cfg: Config, now: datetime, show_all: bool = False) -> str:
    data = legacy.collect(db_path, cfg, now)
    all_pools = data["pools"]
    passing = [pool for pool in all_pools if legacy.qualifies(pool, cfg)]
    shown = all_pools if show_all else passing
    heartbeat = legacy._heartbeat_age(cfg, now)
    heartbeat_ok = heartbeat is not None and heartbeat < 300
    heartbeat_text = f"{heartbeat:.0f}s" if heartbeat is not None else "never"
    hot = sum(1 for pool in shown if pool["heat"] >= legacy.HOT_THRESHOLD)
    top_heat = max((int(pool["heat"]) for pool in shown), default=0)
    best = shown[:3]

    hero = "".join(_hero_card(pool, now, rank + 1) for rank, pool in enumerate(best))
    if not hero:
        hero = '<div class="zero">No pool passes the active safety filters right now.</div>'

    rows = "".join(_table_row(pool, now) for pool in shown)
    if not rows:
        rows = '<tr><td colspan="10" class="zero">No qualifying pools. Switch to All tracked to inspect the full watchlist.</td></tr>'

    mode_href = "/" if show_all else "/?all=1"
    mode_text = "Filtered radar" if show_all else f"All tracked ({len(all_pools)})"
    generated = html.escape(now.strftime("%Y-%m-%d %H:%M:%S UTC"))
    min_liq = html.escape(fmt_usd(cfg.min_liq))
    esc_vol = html.escape(fmt_usd(cfg.esc_vol_h1))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>rh-meme-watch · Robinhood Chain Radar</title>
<style>
:root{{--bg:#07090d;--panel:#0e1219;--panel2:#121824;--line:#202938;--text:#f7f8fb;--muted:#8994a6;--blue:#6d91ff;--cyan:#42d3ff;--green:#47d18c;--amber:#ffbf5a;--red:#ff626d;--shadow:0 18px 60px rgba(0,0,0,.38)}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 18% -10%,rgba(74,106,255,.16),transparent 33%),radial-gradient(circle at 90% 10%,rgba(66,211,255,.08),transparent 26%),var(--bg);color:var(--text);font:13px/1.45 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:inherit}} .shell{{max-width:1760px;margin:auto;padding:26px 28px 36px}}
.topbar{{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:22px}} .brand{{display:flex;gap:13px;align-items:center}} .logo{{width:42px;height:42px;border-radius:12px;background:linear-gradient(145deg,#7599ff,#4058d9);display:grid;place-items:center;font-weight:900;box-shadow:0 10px 30px rgba(79,106,255,.28)}}
h1{{font-size:22px;letter-spacing:-.02em;margin:0}} .kicker{{color:var(--muted);margin-top:2px}} .live{{display:inline-flex;align-items:center;gap:7px;border:1px solid rgba(71,209,140,.24);color:var(--green);background:rgba(71,209,140,.08);padding:7px 10px;border-radius:999px;font-weight:700}} .live:before{{content:"";width:7px;height:7px;background:currentColor;border-radius:50%;box-shadow:0 0 0 5px rgba(71,209,140,.08)}}
.stats{{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin-bottom:22px}} .stat{{background:linear-gradient(180deg,rgba(18,24,36,.94),rgba(12,16,23,.94));border:1px solid var(--line);border-radius:14px;padding:14px 15px;box-shadow:0 8px 28px rgba(0,0,0,.16)}} .stat span{{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.12em}} .stat strong{{display:block;font-size:23px;margin-top:4px;letter-spacing:-.03em}} .stat small{{color:var(--muted)}}
.section-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:24px 0 12px}} .section-head h2{{font-size:15px;margin:0}} .section-head p{{margin:3px 0 0;color:var(--muted)}} .toggle{{text-decoration:none;border:1px solid var(--line);background:var(--panel);padding:8px 11px;border-radius:9px;color:#c7d0de}}
.op-grid-wrap{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}} .opportunity{{position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(17,23,34,.98),rgba(10,14,21,.98));border:1px solid var(--line);border-radius:18px;padding:16px;box-shadow:var(--shadow)}} .opportunity:before{{content:"";position:absolute;left:0;right:0;top:0;height:2px;background:var(--blue);opacity:.8}} .opportunity.warm:before{{background:var(--amber)}} .opportunity.hot:before{{background:var(--red);box-shadow:0 0 24px var(--red)}} .op-top{{display:flex;align-items:center;gap:10px}} .rank{{color:var(--muted);font-weight:800}} .token-mark{{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,#26334a,#182132);display:grid;place-items:center;color:#dce6ff;font-weight:800;border:1px solid #32405a}} .token-mark.small{{width:30px;height:30px;border-radius:9px;font-size:11px}} .op-name{{min-width:0;flex:1}} .op-name strong{{font-size:17px}} .op-name span,.asset span{{display:block;color:var(--muted);font-size:10px}} .heat-ring{{--heat:0;width:54px;height:54px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--red) calc(var(--heat)*1%),#202938 0);position:relative}} .heat-ring:after{{content:"";position:absolute;inset:5px;background:#0c1119;border-radius:50%}} .heat-ring b,.heat-ring small{{z-index:1;position:absolute}} .heat-ring b{{font-size:16px;top:10px}} .heat-ring small{{font-size:7px;bottom:9px;color:var(--muted);letter-spacing:.12em}}
.op-badges,.badges{{display:flex;flex-wrap:wrap;gap:5px;margin:12px 0}} .pill{{border:1px solid #2d3646;color:#9ba7b8;background:#151b25;border-radius:999px;padding:3px 7px;font-size:8px;font-weight:800;letter-spacing:.06em}} .pill-green{{color:var(--green);border-color:rgba(71,209,140,.25);background:rgba(71,209,140,.07)}} .pill-amber{{color:var(--amber);border-color:rgba(255,191,90,.25);background:rgba(255,191,90,.07)}} .pill-red{{color:var(--red);border-color:rgba(255,98,109,.25);background:rgba(255,98,109,.07)}}
.socials{{display:flex;flex-wrap:wrap;gap:5px;margin:-6px 0 10px}} .social{{display:inline-flex;align-items:center;justify-content:center;min-width:26px;height:20px;padding:0 6px;border:1px solid #2f3a4c;border-radius:6px;background:#141b26;color:#c3d0e2;font-size:9px;font-weight:800;text-decoration:none;letter-spacing:.04em}} .social:hover{{border-color:var(--blue);color:#fff}} .social-none{{color:var(--red);border-color:rgba(255,98,109,.3);background:rgba(255,98,109,.06)}} .social-unknown{{color:var(--muted);border-style:dashed}}
.mcap-row{{display:flex;align-items:center;gap:8px;margin-top:8px;padding:8px 10px;background:#0a0e15;border:1px solid #1c2533;border-radius:11px}} .mcap-leg{{display:flex;flex-direction:column;min-width:0}} .mcap-leg i{{font-style:normal;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.09em}} .mcap-leg b{{font-size:13px;margin-top:2px}} .mcap-arrow{{color:var(--muted)}} .mcap-mult{{margin-left:auto;font-weight:800;font-size:13px}}
.op-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}} .op-grid>div{{background:#0a0e15;border:1px solid #1c2533;border-radius:11px;padding:9px}} .op-grid span{{display:block;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.07em}} .op-grid b{{display:block;margin-top:3px;font-size:14px}} .op-grid small{{color:var(--muted);font-size:9px}} .positive{{color:var(--green)!important}} .negative{{color:var(--red)!important}} .mini-chart{{height:58px;margin:10px 0 6px}} .spark{{width:100%;height:100%;display:block}}
.actions{{display:flex;gap:7px}} .btn,.row-actions a,.copy-icon{{appearance:none;text-decoration:none;border:1px solid var(--line);background:#111722;color:#dbe3ef;border-radius:8px;padding:8px 10px;font:inherit;font-weight:700;cursor:pointer}} .btn-primary{{background:linear-gradient(135deg,#6f8fff,#4763df);border-color:#6f8fff;color:white;flex:1;text-align:center}} .op-foot{{display:flex;justify-content:space-between;gap:12px;margin-top:9px;color:var(--muted);font-size:9px}}
.table-card{{background:rgba(11,15,22,.92);border:1px solid var(--line);border-radius:16px;overflow:hidden}} .table-scroll{{overflow:auto}} table{{border-collapse:collapse;width:100%;min-width:1180px}} th{{text-align:left;padding:10px 12px;color:#788499;font-size:9px;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid var(--line);background:#0b1018;position:sticky;top:0}} td{{padding:10px 12px;border-bottom:1px solid rgba(32,41,56,.72);vertical-align:middle}} tbody tr:hover{{background:rgba(92,126,255,.055)}} .asset{{display:flex;align-items:center;gap:8px}} .asset strong{{font-size:12px}} .mono{{font-variant-numeric:tabular-nums;white-space:nowrap}} .secondary{{display:block;color:var(--muted);font-size:9px;margin-top:2px}} .heat-cell{{display:flex;align-items:center;gap:7px}} .heat-cell>span{{font-weight:800;width:22px}} .heat-cell>div{{width:72px;height:6px;border-radius:9px;background:#202938;overflow:hidden}} .heat-cell i{{display:block;height:100%;background:linear-gradient(90deg,#5f8aff,#ffbf5a,#ff626d)}} .row-actions{{display:flex;gap:5px}} .row-actions a,.copy-icon{{padding:5px 7px;font-size:10px}}
.zero{{padding:28px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);text-align:center;grid-column:1/-1}} .meta{{margin-top:12px;color:var(--muted);font-size:10px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}} .toast{{position:fixed;right:22px;bottom:22px;background:#151d29;border:1px solid #34425b;padding:10px 13px;border-radius:10px;opacity:0;transform:translateY(8px);transition:.2s;pointer-events:none}} .toast.show{{opacity:1;transform:none}}
@media(max-width:1050px){{.stats{{grid-template-columns:repeat(3,1fr)}}.op-grid-wrap{{grid-template-columns:1fr}}}} @media(max-width:650px){{.shell{{padding:18px 12px 28px}}.stats{{grid-template-columns:repeat(2,1fr)}}.topbar{{flex-direction:column}}.op-grid{{grid-template-columns:1fr 1fr}}.op-foot{{flex-direction:column}}}}
</style></head><body><div class="shell">
<header class="topbar"><div class="brand"><div class="logo">RH</div><div><h1>meme watch</h1><div class="kicker">Robinhood Chain · opportunity radar · 60s refresh</div></div></div><div class="live">{('LIVE · '+heartbeat_text) if heartbeat_ok else ('STALE · '+heartbeat_text)}</div></header>
<section class="stats">
<div class="stat"><span>Passing filters</span><strong>{len(passing)}</strong><small>liq held + ≥ {min_liq}</small></div>
<div class="stat"><span>Tracked pools</span><strong>{len(all_pools)}</strong><small>200 max in radar</small></div>
<div class="stat"><span>Alerts 24h</span><strong>{data['alerts_24h']}</strong><small>new pool detections</small></div>
<div class="stat"><span>Escalations 24h</span><strong>{data['escalations_24h']}</strong><small>growth confirmations</small></div>
<div class="stat"><span>Hot now</span><strong>{hot}</strong><small>heat ≥ {legacy.HOT_THRESHOLD}</small></div>
<div class="stat"><span>Top heat</span><strong>{top_heat}</strong><small>vol threshold {esc_vol}</small></div>
</section>
<div class="section-head"><div><h2>Top opportunities</h2><p>Highest heat among pools that pass the active liquidity controls.</p></div><a class="toggle" href="{mode_href}">{mode_text}</a></div>
<section class="op-grid-wrap">{hero}</section>
<div class="section-head"><div><h2>Radar</h2><p>Heat blends 45% volume, 25% buyer flow and 30% liquidity expansion. Red risk badges are warnings, not trade signals.</p></div></div>
<section class="table-card"><div class="table-scroll"><table><thead><tr><th>Asset</th><th>State & risk</th><th>Age</th><th>Liquidity</th><th>Market cap</th><th>Volume / flow</th><th>1h</th><th>Liquidity 24h</th><th>Heat</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<div class="meta"><span>Generated {generated} · snapshots kept 14 days · <a href="/api/pools">JSON API</a></span><span>Fomo supports Robinhood Chain; the button opens Fomo Web because no stable public token deep-link format is documented.</span></div>
</div><div id="toast" class="toast">Pool address copied</div>
<script>
const toast=document.getElementById('toast');
document.addEventListener('click',async(e)=>{{const b=e.target.closest('[data-copy]');if(!b)return;try{{await navigator.clipboard.writeText(b.dataset.copy);toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1300)}}catch(_e){{}}}});
</script></body></html>"""


def start_dashboard(cfg: Config, port: int | None = None):
    """Install the UI renderer and delegate the server to the proven implementation."""
    legacy.render_html = render_html
    return legacy.start_dashboard(cfg, port=port)
