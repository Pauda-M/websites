"""NEW-token qualification requires socials AND liquidity, never either alone."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import classify, meme_socials, passes_new_rule

from conftest import NOW, api_item, mk_cfg


def test_social_without_liquidity_is_rejected(tmp_path):
    cfg = mk_cfg(tmp_path, liq_floor=150_000.0, liq_floor_stock=75_000.0)
    pool = Pool.from_api(
        api_item(name="SOCIAL / WETH", created_at=NOW, reserve="2500", socials=True)
    )
    cls = classify(pool, cfg)
    assert pool.reserve_usd == 2500.0
    assert meme_socials(pool, cls)
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_liquidity_without_social_is_rejected(tmp_path):
    cfg = mk_cfg(tmp_path)
    pool = Pool.from_api(
        api_item(name="NOSOCIAL / WETH", created_at=NOW, reserve="500000", socials=False)
    )
    cls = classify(pool, cfg)
    assert pool.reserve_usd == 500_000.0
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_social_and_liquidity_together_pass(tmp_path):
    cfg = mk_cfg(tmp_path, liq_floor=150_000.0)
    pool = Pool.from_api(
        api_item(
            name="GOOD / WETH",
            created_at=NOW - timedelta(minutes=30),
            reserve="500000",
            socials=True,
        )
    )
    cls = classify(pool, cfg)
    assert passes_new_rule(pool, cls, cfg, NOW)


def test_social_must_belong_to_meme_side(tmp_path):
    """A stock-paired pool must not inherit the tokenized stock's socials."""
    cfg = mk_cfg(tmp_path)
    item = api_item(name="AAPL / MEME", created_at=NOW, reserve="500000", socials=False)
    base_id = item["relationships"]["base_token"]["data"]["id"]
    item["_socials_by_token"] = {base_id: ["https://x.com/aapl"]}
    pool = Pool.from_api(item)
    cls = classify(pool, cfg)
    assert cls.meme_symbol == "MEME"
    assert not cls.meme_is_base
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_stock_paired_meme_side_social_passes(tmp_path):
    cfg = mk_cfg(tmp_path, liq_floor_stock=75_000.0)
    item = api_item(
        name="AAPL / MEME",
        created_at=NOW - timedelta(minutes=30),
        reserve="100000",
        socials=False,
    )
    quote_id = item["relationships"]["quote_token"]["data"]["id"]
    item["_socials_by_token"] = {quote_id: ["https://t.me/memechat"]}
    pool = Pool.from_api(item)
    cls = classify(pool, cfg)
    assert cls.is_stock_paired
    assert passes_new_rule(pool, cls, cfg, NOW)


def test_missing_social_metadata_fails_closed(tmp_path):
    """An info-endpoint outage must not silently open the gate."""
    cfg = mk_cfg(tmp_path)
    item = api_item(name="OUTAGE / WETH", created_at=NOW, reserve="500000", socials=True)
    item.pop("_socials_by_token")
    pool = Pool.from_api(item)
    cls = classify(pool, cfg)
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_kill_switch_drops_the_social_requirement_but_not_liquidity(tmp_path):
    """REQUIRE_SOCIALS=0 is an outage escape hatch, not a liquidity bypass."""
    cfg = mk_cfg(tmp_path, require_socials=False, liq_floor=150_000.0)
    aged = NOW - timedelta(minutes=30)

    funded = Pool.from_api(
        api_item(name="NOSOC / WETH", created_at=aged, reserve="500000", socials=False)
    )
    assert passes_new_rule(funded, classify(funded, cfg), cfg, NOW)

    thin = Pool.from_api(
        api_item(name="THIN / WETH", created_at=aged, reserve="2500", socials=False)
    )
    assert not passes_new_rule(thin, classify(thin, cfg), cfg, NOW)
