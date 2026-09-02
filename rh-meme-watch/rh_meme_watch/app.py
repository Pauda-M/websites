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


class App:
    def __init__(
        self,
        cfg: Config,
        gecko: GeckoClient | None = None,
        telegram: TelegramClient | None = None,
        store: Store | None = None,
        now_fn: Callable[[], datetime] = utc_now,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = cfg
        self.now_fn = now_fn
        self.sleep_fn = sleep_fn
        self.gecko = gecko or GeckoClient(sleep=sleep_fn)
        self.telegram = telegram or TelegramClient(cfg.telegram_bot_token, cfg.telegram_chat_id)
        self.store = store or Store(cfg.db_path)
        self.fdv = rules.FdvResolver(self.gecko.search_pools, cfg, now_fn)
        self.tzinfo = ZoneInfo(cfg.tz)

    # -- lifecycle -----------------------------------------------------------

    def startup(self) -> None:
        """Verify Telegram credentials and announce start. Raises on auth failure."""
        me = self.telegram.verify()
        bot = (me.get("result") or {}).get("username", "?")
        log.info("telegram auth ok (bot @%s)", bot)
        self.telegram.send(messages.build_startup(self.cfg))

    def run(self) -> None:
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
            )
            if self._maybe_new_alert(pool, cls, now):
                alerted_now.add(pool.address)

        for pool in pools:
            if pool.address in alerted_now:
                continue
            self._maybe_escalate(pool, now)

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

        fdv_meme = self.fdv.fdv_for(pool, cls)
        text = messages.build_new_alert(pool, cls, fdv_meme, now)
        self.telegram.send(text)
        self.store.mark_alerted(pool.address, now, pool.reserve_usd)
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

    def _maybe_escalate(self, pool: Pool, now: datetime) -> None:
        row = self.store.get_pool(pool.address)
        if row is None or not row["first_alert_ts"]:
            return
        verdict = rules.escalation_verdict(
            pool,
            row["first_liq"],
            self.store.escalated_ts(pool.address),
            self.cfg,
            now,
        )
        if not verdict.fire:
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

    def _maybe_digest(self, pools: list[Pool], now: datetime) -> None:
        local = now.astimezone(self.tzinfo)
        if local.hour < self.cfg.digest_hour:
            return
        last = self.store.last_alert_ts("digest")
        if last is not None and last.astimezone(self.tzinfo).date() >= local.date():
            return
        top = rules.digest_pools(pools, now)
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
        log.info("daily digest sent (%d pools)", len(top))

    def _heartbeat(self, now: datetime) -> None:
        """Written only at the end of a fully successful cycle."""
        self.cfg.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.heartbeat_path.write_text(now.isoformat())
