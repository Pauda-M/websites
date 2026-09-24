"""Main polling loop wiring rules, store, GeckoTerminal and Telegram."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from . import messages, rules
from .config import Config
from .gecko import GeckoClient, GeckoUnavailable
from .models import Pool, parse_pools
from .store import Store
from .telegram import TelegramClient, TelegramError

log = logging.getLogger("rh_meme_watch.app")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_address(token_id: str | None) -> str | None:
    """"robinhood_0xabc..." -> "0xabc...". Token ids carry a network prefix."""
    if not token_id:
        return None
    addr = token_id.split("_", 1)[1] if "_" in token_id else token_id
    return addr if addr.startswith("0x") else None


def _snap_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except ValueError:
        return None


class App:
    def __init__(
        self,
        cfg: Config,
        gecko: GeckoClient | None = None,
        telegram: TelegramClient | None = None,
        store: Store | None = None,
        onchain=None,
        now_fn: Callable[[], datetime] = utc_now,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = cfg
        self.now_fn = now_fn
        self.sleep_fn = sleep_fn
        self.gecko = gecko or GeckoClient(
            sleep=sleep_fn,
            social_lookups_per_cycle=cfg.social_lookups_per_cycle,
            social_cache_ttl_sec=cfg.social_cache_ttl_sec,
            social_miss_ttl_sec=cfg.social_miss_ttl_sec,
        )
        self.telegram = telegram or TelegramClient(cfg.telegram_bot_token, cfg.telegram_chat_id)
        self.store = store or Store(cfg.db_path)
        self.fdv = rules.FdvResolver(self.gecko.search_pools, cfg, now_fn)
        self.onchain = onchain
        if self.onchain is None and cfg.rpc_url:
            from .onchain import OnchainVerifier, RpcClient

            self.onchain = OnchainVerifier(
                RpcClient(cfg.rpc_url), dict(cfg.lp_custodians)
            )
        self.tzinfo = ZoneInfo(cfg.tz)

    # -- lifecycle -----------------------------------------------------------

    def startup(self) -> None:
        """Verify Telegram credentials and announce start. Raises on auth failure."""
        me = self.telegram.verify()
        bot = (me.get("result") or {}).get("username", "?")
        log.info("telegram auth ok (bot @%s)", bot)
        self.telegram.send(messages.build_startup(self.cfg))

    def run(self) -> None:
        if self.cfg.dashboard_port:
            from .dashboard_ui import start_dashboard

            start_dashboard(self.cfg)
        log.info(
            "watching robinhood pools: floor=%s stock_floor=%s window=%smin poll=%ss",
            self.cfg.liq_floor,
            self.cfg.liq_floor_stock,
            self.cfg.new_window_min,
            self.cfg.poll_sec,
        )
        while True:
            started = time.monotonic()
            self.run_cycle_safe()
            elapsed = time.monotonic() - started
            self.sleep_fn(max(0.0, self.cfg.poll_sec - elapsed))

    def run_cycle_safe(self) -> bool:
        """One poll cycle; never raises, returns True when the cycle succeeded."""
        try:
            self.run_cycle()
            return True
        except GeckoUnavailable as exc:
            log.warning("cycle skipped, API unavailable: %s", exc)
        except TelegramError as exc:
            log.error("cycle hit a Telegram error: %s", exc)
        except Exception:
            log.exception("cycle failed unexpectedly")
        return False

    # -- one cycle -----------------------------------------------------------

    def run_cycle(self) -> None:
        now = self.now_fn()
        self.fdv.new_cycle()

        new_items = self.gecko.new_pools()
        top_items = self.gecko.top_pools()
        pools = self._dedupe(parse_pools({"data": new_items}) + parse_pools({"data": top_items}))

        # Discovery only surfaces pools inside the new-pool and top-pool windows,
        # so an alerted pool falls out of view within minutes and stops being
        # observed. Re-read the watchlist explicitly: without it no pool ever
        # accumulates the history a retention verdict needs, and escalations are
        # blind to anything that has dropped out of the rankings.
        seen = {p.address for p in pools}
        stale = [a for a in self.store.watchlist(self.cfg.watchlist_size) if a not in seen]
        if stale:
            refreshed = parse_pools({"data": self.gecko.pools_by_address(stale)})
            pools = pools + self._dedupe(refreshed)
            log.debug("watchlist refresh: %d stale, %d returned", len(stale), len(refreshed))

        alerted_now: set[str] = set()
        for pool in pools:
            cls = rules.classify(pool, self.cfg)
            self.store.upsert_seen(
                pool.address,
                cls.meme_symbol or pool.base_symbol,
                cls.stock_symbol or pool.quote_symbol,
                pool.dex,
                pool.created_at,
                now,
                pool.reserve_usd,
                pool.vol_h1,
                socials=rules.meme_socials(pool, cls),
                mcap=rules.meme_mcap(pool, cls),
            )
            if self._maybe_new_alert(pool, cls, now):
                alerted_now.add(pool.address)
            if self.store.was_alerted(pool.address):
                self.store.record_snapshot(
                    pool.address,
                    now,
                    pool.reserve_usd,
                    pool.vol_h1,
                    pool.buys_h1,
                    pool.sells_h1,
                    pool.buyers_h1,
                    pool.sellers_h1,
                    pool.price_change_h1,
                )

        for pool in pools:
            if pool.address in alerted_now:
                continue
            self._maybe_escalate(pool, now)

        self._verify_onchain(pools, now)
        self._maybe_digest(pools, now)
        self._heartbeat(now)

    def _dedupe(self, pools: list[Pool]) -> list[Pool]:
        seen: dict[str, Pool] = {}
        for p in pools:
            if p.address and p.address not in seen:
                seen[p.address] = p
        return list(seen.values())

    def _maybe_new_alert(self, pool: Pool, cls: rules.Classification, now: datetime) -> bool:
        if not rules.passes_new_rule(pool, cls, self.cfg, now):
            return False
        if self.store.was_alerted(pool.address):
            return False
        last_symbol_ts = self.store.last_symbol_alert_ts(cls.meme_symbol or "")
        if last_symbol_ts is not None and now - last_symbol_ts < timedelta(
            hours=self.cfg.symbol_cooldown_h
        ):
            log.info(
                "suppressing %s (%s): symbol cooldown active since %s",
                pool.name,
                pool.address,
                last_symbol_ts.isoformat(),
            )
            return False

        # Resolve the meme side's FDV before gating: pool.fdv_usd belongs to the
        # base token, which on a stock-as-base pool is the tokenized stock.
        fdv_meme = self.fdv.fdv_for(pool, cls)
        quality = rules.quality_verdict(pool, self.cfg, fdv_meme)
        if not quality.passes:
            log.info(
                "filtered out %s (%s): %s", pool.name, pool.address, quality.reason
            )
            return False

        text = messages.build_new_alert(pool, cls, fdv_meme, now)
        self.telegram.send(text)
        # fdv_meme was resolved just above; it is the detection baseline.
        self.store.mark_alerted(pool.address, now, pool.reserve_usd, fdv_meme)
        kind = "new_stock" if cls.is_stock_paired else "new"
        self.store.record_alert(
            pool.address,
            kind,
            now,
            {
                "name": pool.name,
                "reserve_usd": pool.reserve_usd,
                "fdv_meme": fdv_meme,
                "vol_h1": pool.vol_h1,
                "dex": pool.dex,
            },
        )
        log.info("NEW alert sent: %s (%s)", pool.name, pool.address)
        return True

    def _lock_for(self, pool: Pool, now: datetime) -> rules.LockVerdict:
        """Liquidity-lock proxy from this pool's recorded reserve history."""
        rows = self.store.snapshots(pool.address, now - timedelta(hours=24))
        history = [(_snap_ts(r["ts"]), r["reserve"]) for r in rows]
        history = [(ts, res) for ts, res in history if ts is not None]
        return rules.lock_verdict(history, self.cfg, pool.reserve_usd)

    def _maybe_escalate(self, pool: Pool, now: datetime) -> None:
        row = self.store.get_pool(pool.address)
        if row is None or not row["first_alert_ts"]:
            return
        lock = self._lock_for(pool, now)
        verdict = rules.escalation_verdict(
            pool,
            row["first_liq"],
            self.store.escalated_ts(pool.address),
            self.cfg,
            now,
            lock=lock,
        )
        if not verdict.fire:
            if (
                self.cfg.require_liq_lock
                and not lock.locked
                and pool.reserve_usd is not None
                and pool.reserve_usd >= self.cfg.min_liq
            ):
                log.debug(
                    "escalation held back for %s: liquidity lock %s (drawdown=%s)",
                    pool.name,
                    lock.label,
                    lock.drawdown,
                )
            return
        cls = rules.classify(pool, self.cfg)
        warnings = rules.dump_warnings(pool, row["first_liq"])
        fdv_meme = self.fdv.fdv_for(pool, cls)
        text = messages.build_escalation(
            pool, cls, fdv_meme, now, verdict.reason or "", verdict.liq_mult, warnings
        )
        self.telegram.send(text)
        self.store.mark_escalated(pool.address, now)
        self.store.record_alert(
            pool.address,
            "escalate",
            now,
            {
                "name": pool.name,
                "reason": verdict.reason,
                "liq_mult": verdict.liq_mult,
                "reserve_usd": pool.reserve_usd,
                "vol_h1": pool.vol_h1,
                "warnings": warnings,
            },
        )
        log.info("ESCALATE alert sent: %s (%s)", pool.name, pool.address)

    def _verify_onchain(self, pools: list[Pool], now: datetime) -> None:
        """Read LP custody + true reserves from the chain, cheapest-first.

        The due list comes from the store, not from this cycle's API response: a
        pool that has dropped out of the API windows is exactly when its LP is
        most likely to be pulled, and custody is a pure chain read. Reserve
        verification additionally needs the quote token and its price, so it only
        runs for pools present in this cycle's response.
        """
        if self.onchain is None:
            return
        cutoff = now - timedelta(seconds=self.cfg.onchain_cache_ttl_sec)
        due = self.store.onchain_due(cutoff, self.cfg.onchain_lookups_per_cycle)
        if not due:
            return
        visible = {p.address: p for p in pools}

        for row in due:
            address = row["address"]
            pool = visible.get(address)
            try:
                custody = self.onchain.custody(address)
                reserve_usd = None
                if pool is not None:
                    reserve = self.onchain.reserve(
                        address,
                        pool.quote_token_price_usd,
                        _token_address(pool.quote_token_id),
                    )
                    reserve_usd = reserve.reserve_usd
            except Exception:
                log.exception("on-chain verification failed for %s", address)
                continue
            previous = self.store.get_onchain(address)
            self.store.upsert_onchain(
                address,
                now,
                custody.kind,
                custody.total_supply,
                custody.holder,
                custody.holder_units,
                custody.holder_pct,
                custody.burned_pct,
                reserve_usd,
                custody.note,
            )
            self._maybe_lp_moved_alert(row, pool, previous, custody, now)

    def _maybe_lp_moved_alert(self, row, pool, previous, custody, now: datetime) -> None:
        if previous is None or custody.holder is None or custody.holder_units is None:
            return
        if (previous["holder"] or "").lower() != custody.holder.lower():
            return
        try:
            before = int(previous["holder_units"] or 0)
        except (TypeError, ValueError):
            return
        if before <= 0:
            return
        dropped_pct = 100.0 * (before - custody.holder_units) / before
        if dropped_pct < self.cfg.custody_drop_pct:
            return
        address = row["address"]
        name = pool.name if pool is not None else f"{row['symbol']} / {row['quote']}"
        text = messages.build_lp_moved(
            name,
            address,
            custody.holder,
            previous["holder_pct"],
            custody.holder_pct,
            before,
            custody.holder_units,
            custody.note or "",
            pool.reserve_usd if pool is not None else row["last_liq"],
            pool.vol_h1 if pool is not None else row["last_vol_h1"],
        )
        self.telegram.send(text)
        self.store.record_alert(
            address,
            "lp_moved",
            now,
            {
                "name": name,
                "holder": custody.holder,
                "units_before": str(before),
                "units_after": str(custody.holder_units),
                "dropped_pct": round(dropped_pct, 2),
            },
        )
        log.warning(
            "LP MOVED alert sent: %s (%s) custodian %s dropped %.1f%%",
            name,
            address,
            custody.holder,
            dropped_pct,
        )

    def _maybe_digest(self, pools: list[Pool], now: datetime) -> None:
        local = now.astimezone(self.tzinfo)
        if local.hour < self.cfg.digest_hour:
            return
        last = self.store.last_alert_ts("digest")
        if last is not None and last.astimezone(self.tzinfo).date() >= local.date():
            return
        candidates = rules.digest_pools(
            pools, now, limit=100, min_liq=self.cfg.min_liq
        )
        if self.cfg.require_liq_lock:
            candidates = [p for p in candidates if self._lock_for(p, now).locked]
        top = candidates[:10]
        entries = []
        for pool in top:
            cls = rules.classify(pool, self.cfg)
            row = self.store.get_pool(pool.address)
            first_liq = row["first_liq"] if row is not None else None
            entries.append((pool, cls, rules.dump_warnings(pool, first_liq)))
        self.telegram.send(messages.build_digest(entries, now))
        self.store.record_alert(
            "", "digest", now, {"pools": [p.address for p in top]}
        )
        self.store.prune_snapshots(now - timedelta(days=self.cfg.snapshot_keep_days))
        log.info("daily digest sent (%d pools)", len(top))

    def _heartbeat(self, now: datetime) -> None:
        """Written only at the end of a fully successful cycle."""
        self.cfg.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.heartbeat_path.write_text(now.isoformat())
