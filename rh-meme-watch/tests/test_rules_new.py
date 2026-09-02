"""R1 NEW / R2 STOCK-PAIRED floor and window behavior."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import classify, liquidity_floor, passes_new_rule

from conftest import NOW, api_item, mk_cfg


def _pool(name: str, reserve, age_min: int) -> Pool:
    created = NOW - timedelta(minutes=age_min)
    return Pool.from_api(api_item(name=name, reserve=reserve, created_at=created))


def _passes(tmp_path, name, reserve, age_min):
    cfg = mk_cfg(tmp_path)
    pool = _pool(name, reserve, age_min)
    return passes_new_rule(pool, classify(pool, cfg), cfg, NOW)


def test_meme_pool_passes_at_regular_floor(tmp_path):
    assert _passes(tmp_path, "PEPE / WETH", "150000", 30)


def test_meme_pool_below_regular_floor_fails(tmp_path):
    assert not _passes(tmp_path, "PEPE / WETH", "149999", 30)


def test_stock_paired_uses_lower_floor(tmp_path):
    # 118k: above the 75k stock floor, below the 150k regular floor
    assert _passes(tmp_path, "AAPLDOG / AAPL", "118000", 41)
    assert not _passes(tmp_path, "PLAINMEME / WETH", "118000", 41)


def test_stock_paired_below_stock_floor_fails(tmp_path):
    assert not _passes(tmp_path, "AAPLDOG / AAPL", "74999", 41)


def test_age_window_limits(tmp_path):
    assert _passes(tmp_path, "PEPE / WETH", "200000", 179)
    assert not _passes(tmp_path, "PEPE / WETH", "200000", 181)


def test_unknown_created_at_never_passes(tmp_path):
    cfg = mk_cfg(tmp_path)
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
    assert liquidity_floor(stock, cfg) == cfg.liq_floor_stock == 75_000
    assert liquidity_floor(plain, cfg) == cfg.liq_floor == 150_000
