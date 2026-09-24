"""Daily digest at 07:00 Europe/Zurich: top 10 by h24 volume, created < 24 h."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import mk_cfg_optional as _mk_opt, Clock, FakeGecko, api_item, mk_app, mk_cfg

# 2026-09-02 is CEST (UTC+2): 05:01 UTC == 07:01 in Zurich.
BEFORE_SEVEN = datetime(2026, 9, 2, 4, 59, tzinfo=timezone.utc)
AFTER_SEVEN = datetime(2026, 9, 2, 5, 1, tzinfo=timezone.utc)


def _pools(now: datetime) -> list[dict]:
    items = []
    for i in range(12):  # 12 fresh pools -> digest must cap at 10
        items.append(
            api_item(
                name=f"MEME{i} / WETH",
                address=f"0x{i:040x}",
                reserve="50000",  # under this test's own floor -> no NEW alerts interfering
                vol_h24=str(1000 * (i + 1)),
                created_at=now - timedelta(hours=2),
            )
        )
    items.append(
        api_item(
            name="OLDIE / WETH",
            address="0x" + "f" * 40,
            reserve="50000",
            vol_h24="99999999",
            created_at=now - timedelta(hours=30),  # too old for the digest
        )
    )
    return items


def _mk(tmp_path, start: datetime):
    clock = Clock(start)
    gecko = FakeGecko(top_items=_pools(start))
    # real digest_hour=7; the liquidity-lock gate is covered in test_liq_lock.py
    cfg = _mk_opt(tmp_path, require_liq_lock=False, liq_floor=150_000.0)
    return mk_app(tmp_path, gecko, clock=clock, cfg=cfg)


def test_no_digest_before_seven_local(tmp_path):
    app, telegram, clock = _mk(tmp_path, BEFORE_SEVEN)
    app.run_cycle()
    assert telegram.sent == []


def test_digest_after_seven_local_top10_fresh_only(tmp_path):
    app, telegram, clock = _mk(tmp_path, AFTER_SEVEN)
    app.run_cycle()
    assert len(telegram.sent) == 1
    digest = telegram.sent[0]
    assert "daily digest" in digest
    assert "MEME11" in digest  # highest fresh h24 volume
    assert "OLDIE" not in digest  # created > 24h ago
    assert "10\\." in digest and "11\\." not in digest  # capped at ten entries


def test_digest_sent_once_per_day(tmp_path):
    app, telegram, clock = _mk(tmp_path, AFTER_SEVEN)
    app.run_cycle()
    assert len(telegram.sent) == 1

    clock.advance(minutes=60)  # same local day
    app.run_cycle()
    assert len(telegram.sent) == 1

    clock.advance(hours=24)  # 07:01 next local day
    app.run_cycle()
    assert len(telegram.sent) == 2


def test_digest_excludes_dust_and_unknown_liquidity(tmp_path):
    """MIN_LIQ gate: wash-volume dust pools never reach the digest."""
    from datetime import timedelta

    clock = Clock(AFTER_SEVEN)
    items = _pools(AFTER_SEVEN)  # 12 fresh pools at $50k liq + OLDIE
    items.append(
        api_item(
            name="DUSTY / WETH",
            address="0x" + "d" * 40,
            reserve="812",  # decoy-sized liquidity
            vol_h24="88888888",  # but the loudest volume of all
            created_at=AFTER_SEVEN - timedelta(hours=1),
        )
    )
    items.append(
        api_item(
            name="NEGRES / USDG",
            address="0x" + "e" * 40,
            reserve="-500",  # unknown liquidity
            vol_h24="77777777",
            created_at=AFTER_SEVEN - timedelta(hours=1),
        )
    )
    gecko = FakeGecko(top_items=items)
    app, telegram, _ = mk_app(
        tmp_path, gecko, clock=clock, cfg=_mk_opt(tmp_path, require_liq_lock=False, liq_floor=150_000.0)
    )
    app.run_cycle()
    assert len(telegram.sent) == 1
    digest = telegram.sent[0]
    assert "DUSTY" not in digest
    assert "NEGRES" not in digest
    assert "MEME11" in digest
