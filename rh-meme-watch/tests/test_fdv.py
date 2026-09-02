"""FDV(meme) resolution: base-side direct, quote-side via cached /search/pools."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import FdvResolver, classify

from conftest import NOW, Clock, FakeGecko, api_item, mk_app, mk_cfg


def test_base_side_meme_uses_pool_fdv_directly(tmp_path):
    cfg = mk_cfg(tmp_path)
    calls: list[str] = []

    def search(q: str) -> list[dict]:
        calls.append(q)
        return []

    resolver = FdvResolver(search, cfg, Clock())
    pool = Pool.from_api(api_item(name="AAPLDOG / AAPL", fdv="440000"))
    assert resolver.fdv_for(pool, classify(pool, cfg)) == 440_000.0
    assert calls == [], "base-side meme must not trigger a search"


def test_quote_side_meme_resolved_via_search_and_cached(tmp_path):
    cfg = mk_cfg(tmp_path)
    clock = Clock()
    calls: list[str] = []

    def search(q: str) -> list[dict]:
        calls.append(q)
        return [api_item(name="WADDLES / USDG", fdv="1900000")]

    resolver = FdvResolver(search, cfg, clock)
    pool = Pool.from_api(api_item(name="AMZN / WADDLES", fdv="245000000000"))
    cls = classify(pool, cfg)

    resolver.new_cycle()
    assert resolver.fdv_for(pool, cls) == 1_900_000.0
    assert calls == ["WADDLES"]

    # cached within the 10-minute TTL, across cycles
    resolver.new_cycle()
    assert resolver.fdv_for(pool, cls) == 1_900_000.0
    assert calls == ["WADDLES"]

    # TTL expiry -> one fresh lookup
    clock.advance(seconds=cfg.fdv_cache_ttl_sec + 1)
    resolver.new_cycle()
    assert resolver.fdv_for(pool, cls) == 1_900_000.0
    assert calls == ["WADDLES", "WADDLES"]


def test_unresolvable_quote_side_meme_returns_none(tmp_path):
    cfg = mk_cfg(tmp_path)
    resolver = FdvResolver(lambda q: [], cfg, Clock())
    pool = Pool.from_api(api_item(name="AMZN / WADDLES"))
    resolver.new_cycle()
    assert resolver.fdv_for(pool, classify(pool, cfg)) is None


def test_per_cycle_lookup_budget(tmp_path):
    cfg = mk_cfg(tmp_path)  # fdv_lookups_per_cycle = 3
    calls: list[str] = []

    def search(q: str) -> list[dict]:
        calls.append(q)
        return []

    resolver = FdvResolver(search, cfg, Clock())
    resolver.new_cycle()
    for i, name in enumerate(["AMZN / M1", "TSLA / M2", "NVDA / M3", "META / M4"]):
        pool = Pool.from_api(api_item(name=name))
        resolver.fdv_for(pool, classify(pool, cfg))
    assert calls == ["M1", "M2", "M3"], "4th lookup in a cycle must be skipped"


def test_alert_message_shows_resolved_quote_side_fdv(tmp_path):
    search_results = {"WADDLES": [api_item(name="WADDLES / USDG", fdv="1900000")]}
    gecko = FakeGecko(
        new_items=[
            api_item(
                name="AMZN / WADDLES",
                reserve="241000",
                created_at=NOW - timedelta(minutes=30),
                fdv="245000000000",  # the base (AMZN) FDV: must NOT be shown as meme FDV
            )
        ],
        search_results=search_results,
    )
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert len(telegram.sent) == 1
    plain = telegram.sent[0].replace("\\", "")
    assert "FDV(meme) $1.9M" in plain
    assert gecko.search_calls == ["WADDLES"]
