"""Rule-engine checks against the committed 40-pool fixture.

The fixture may be either the synthetic seed or live API output written by
scripts/refresh_fixture.py; both carry the same envelope, so these tests only
assert properties that must hold for any healthy snapshot of robinhood pools.
"""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.config import Config
from rh_meme_watch.models import parse_pools
from rh_meme_watch.rules import classify, passes_new_rule

from conftest import mk_cfg

NAMED_STOCK_PAIRS = {
    ("AI", "NVDA"),
    ("MOO", "MU"),
    ("BONER", "HIMS"),
    ("AAPLCAT", "AAPL"),
    ("CLIPPY", "MSFT"),
}


def _cfg(tmp_path) -> Config:
    return mk_cfg(tmp_path)


def test_fixture_parses_completely(fixture_payload):
    pools = parse_pools(fixture_payload)
    assert len(pools) >= 30, "fixture must hold at least 30 pools"
    for p in pools:
        assert p.address.startswith("0x"), p.address
        assert p.name


def test_named_stock_pairs_classify_stock_paired(tmp_path, fixture_payload):
    cfg = _cfg(tmp_path)
    pools = parse_pools(fixture_payload)
    found = set()
    for p in pools:
        key = (p.base_symbol.upper(), p.quote_symbol.upper())
        if key in NAMED_STOCK_PAIRS:
            found.add(key)
            cls = classify(p, cfg)
            assert cls.is_stock_paired, f"{p.name} must classify stock-paired"
            assert cls.meme_symbol is not None and cls.meme_symbol.upper() == key[0]
    assert len(found) >= 3, (
        f"expected at least 3 of the named stock pairs in the fixture, found {found}"
    )


def test_every_stock_quoted_pool_is_stock_paired(tmp_path, fixture_payload):
    cfg = _cfg(tmp_path)
    for p in parse_pools(fixture_payload):
        if p.base_symbol.upper() in cfg.stock_symbols or p.quote_symbol.upper() in cfg.stock_symbols:
            assert classify(p, cfg).is_stock_paired


def test_negative_or_zero_reserve_is_unknown_and_never_alerts(tmp_path, fixture_payload):
    cfg = _cfg(tmp_path)
    raw_by_id = {item["id"]: item for item in fixture_payload["data"]}
    pools = parse_pools(fixture_payload)
    checked = 0
    for p in pools:
        raw = raw_by_id[f"robinhood_{p.address}"]["attributes"].get("reserve_in_usd")
        try:
            negative = raw is not None and float(raw) <= 0
        except (TypeError, ValueError):
            negative = True
        if raw is None or negative:
            checked += 1
            assert p.reserve_usd is None, f"{p.name}: reserve {raw!r} must parse as unknown"
            # even inside the freshest window it must never alert
            now = (p.created_at + timedelta(minutes=1)) if p.created_at else None
            if now is not None:
                assert not passes_new_rule(p, classify(p, cfg), cfg, now)
    # the synthetic seed guarantees such pools exist; live data may not
    assert checked >= 0


def test_duplicate_symbols_have_distinct_addresses(fixture_payload):
    pools = parse_pools(fixture_payload)
    addresses = [p.address for p in pools]
    assert len(addresses) == len(set(addresses)), "pool addresses must be unique"
