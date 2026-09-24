"""R1 NEW / R2 STOCK-PAIRED floor and window behavior."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import classify, liquidity_floor, passes_new_rule

from conftest import NOW, api_item, mk_cfg


def _pool(name: str, reserve, age_min: int) -> Pool:
    created = NOW - timedelta(minutes=age_min)
    return Pool.from_api(api_item(name=name, reserve=reserve, created_at=created))


# These verify floor BEHAVIOUR, so they set their own floors rather than
# inheriting whatever the defaults are. Pinning defaults here made an ordered
# change to them present as a broken test.
TEST_FLOOR = 150_000.0
TEST_FLOOR_STOCK = 75_000.0


def _passes(tmp_path, name, reserve, age_min, **over):
    cfg = mk_cfg(
        tmp_path,
        liq_floor=TEST_FLOOR,
        liq_floor_stock=TEST_FLOOR_STOCK,
        **over,
    )
    pool = _pool(name, reserve, age_min)
    return passes_new_rule(pool, classify(pool, cfg), cfg, NOW)


def test_meme_pool_passes_at_regular_floor(tmp_path):
    assert _passes(tmp_path, "PEPE / WETH", "150000", 30)


def test_meme_pool_below_regular_floor_fails(tmp_path):
    assert not _passes(tmp_path, "PEPE / WETH", "149999", 30)


def test_stock_paired_uses_lower_floor(tmp_path):
    # 118k: above the stock floor, below the regular one
    assert _passes(tmp_path, "AAPLDOG / AAPL", "118000", 41)
    assert not _passes(tmp_path, "PLAINMEME / WETH", "118000", 41)


def test_stock_paired_below_stock_floor_fails(tmp_path):
    assert not _passes(tmp_path, "AAPLDOG / AAPL", "74999", 41)


def test_age_window_limits(tmp_path):
    assert _passes(tmp_path, "PEPE / WETH", "200000", 179)
    assert not _passes(tmp_path, "PEPE / WETH", "200000", 181)


def test_unknown_created_at_never_passes(tmp_path):
    cfg = mk_cfg(tmp_path, liq_floor=TEST_FLOOR, liq_floor_stock=TEST_FLOOR_STOCK)
    pool = Pool.from_api(api_item(name="PEPE / WETH", reserve="200000", created_at=None))
    assert not passes_new_rule(pool, classify(pool, cfg), cfg, NOW)


def test_negative_reserve_never_passes(tmp_path):
    assert not _passes(tmp_path, "BNKRDOG / WETH", "-3421.77", 10)


def test_zero_and_null_reserve_never_pass(tmp_path):
    assert not _passes(tmp_path, "X / WETH", "0", 10)
    assert not _passes(tmp_path, "Y / WETH", None, 10)


def test_stock_vs_stable_never_passes(tmp_path):
    # no meme side -> nothing to alert on, however liquid
    assert not _passes(tmp_path, "AMZN / USDG", "5000000", 30)


def test_floor_selection(tmp_path):
    cfg = mk_cfg(tmp_path)
    stock = classify(Pool.from_api(api_item(name="AAPLDOG / AAPL")), cfg)
    plain = classify(Pool.from_api(api_item(name="PEPE / WETH")), cfg)
    # Explicit values: this asserts which floor gets picked, not what the
    # defaults happen to be. Pinning defaults here made an ordered change to
    # them look like a broken test.
    assert liquidity_floor(stock, cfg) == cfg.liq_floor_stock
    assert liquidity_floor(plain, cfg) == cfg.liq_floor
