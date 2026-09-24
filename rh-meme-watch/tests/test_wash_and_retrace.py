"""Authenticity gates: forged volume, unbacked valuation, and rolled-over pumps.

Volume and transaction counts are both purchasable with fees, so neither alone
proves a pool is real. Distinct wallets are the expensive part. These gates were
calibrated against the recorded live sample, where genuine meme pools run 2.1-5.1
trades per buyer and one decoy ran 1402 on a single buyer with volume identical
across every window.
"""

from __future__ import annotations

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import quality_verdict

from conftest import mk_cfg_optional as _mk_opt, api_item, mk_cfg

GOOD = dict(
    name="MEME / WETH",
    reserve="200000",
    fdv="2000000",
    vol_h1="10000",
    vol_h24="50000",
    pct_h1="10.0",
    pct_m15="2.0",
    tx_h1={"buys": 120, "sells": 60, "buyers": 80, "sellers": 40},
)


def _pool(**over) -> Pool:
    return Pool.from_api(api_item(**{**GOOD, **over}))


def _fdv(p: Pool) -> float:
    return p.fdv_usd or 0.0


def test_baseline_pool_passes_every_new_gate(tmp_path):
    cfg = _mk_opt(tmp_path)
    assert quality_verdict(_pool(), cfg, _fdv(_pool())).passes


# --- wash trading -----------------------------------------------------------

def test_one_wallet_round_tripping_itself_is_rejected(tmp_path):
    """The live COBIE decoy: 1402 trades, one buyer, forged volume."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(tx_h1={"buys": 701, "sells": 701, "buyers": 1, "sellers": 1})
    v = quality_verdict(pool, cfg, _fdv(pool))
    assert not v.passes
    assert "trades/buyer" in v.reason


def test_real_pools_sit_well_under_the_wash_threshold(tmp_path):
    """5.1 trades/buyer was the busiest genuine pool in the live sample."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(tx_h1={"buys": 500, "sells": 280, "buyers": 153, "sellers": 90})
    v = quality_verdict(pool, cfg, _fdv(pool))
    assert "trades/buyer" not in v.reason


def test_wash_gate_disabled_lets_it_through(tmp_path):
    cfg = _mk_opt(tmp_path, max_trades_per_buyer=0, min_buyers_h1=0)
    pool = _pool(tx_h1={"buys": 701, "sells": 701, "buyers": 1, "sellers": 1})
    assert "trades/buyer" not in quality_verdict(pool, cfg, _fdv(pool)).reason


def test_zero_buyers_does_not_divide_by_zero(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(tx_h1={"buys": 0, "sells": 0, "buyers": 0, "sellers": 0})
    quality_verdict(pool, cfg, _fdv(pool))  # must not raise


# --- valuation not backed by turnover ---------------------------------------

def test_valuation_without_turnover_is_rejected(tmp_path):
    """Price is whatever the deployer says; paying to trade costs money."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(fdv="4000000", vol_h24="500")  # 0.000125 turnover
    v = quality_verdict(pool, cfg, _fdv(pool))
    assert not v.passes
    assert "vol/fdv" in v.reason


def test_thin_but_real_turnover_passes(tmp_path):
    """The thinnest genuine meme pool in the sample turned over 0.035 of FDV."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(fdv="2000000", vol_h24="70000")  # 0.035
    assert "vol/fdv" not in quality_verdict(pool, cfg, _fdv(pool)).reason


def test_unknown_meme_fdv_skips_the_ratio_rather_than_guessing(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(vol_h24="500")
    assert "vol/fdv" not in quality_verdict(pool, cfg, None).reason


# --- absolute volume floor --------------------------------------------------

def test_dead_pool_is_rejected_on_absolute_volume(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(vol_h1="400")
    v = quality_verdict(pool, cfg, _fdv(pool))
    assert not v.passes
    assert "vol/h1" in v.reason


def test_missing_volume_counts_as_zero_not_as_a_pass(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(vol_h1=None)
    assert "vol/h1" in quality_verdict(pool, cfg, _fdv(pool)).reason


# --- already ran and rolled over --------------------------------------------

def test_pool_that_pumped_then_turned_down_is_rejected(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(pct_h1="45.0", pct_m15="-8.0")
    v = quality_verdict(pool, cfg, _fdv(pool))
    assert not v.passes
    assert "retracing" in v.reason


def test_still_climbing_is_not_a_retrace(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(pct_h1="45.0", pct_m15="6.0")
    assert "retracing" not in quality_verdict(pool, cfg, _fdv(pool)).reason


def test_a_small_pullback_inside_a_big_move_is_tolerated(tmp_path):
    """-3% is the line; ordinary noise inside an uptrend must not reject."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(pct_h1="45.0", pct_m15="-1.0")
    assert "retracing" not in quality_verdict(pool, cfg, _fdv(pool)).reason


def test_flat_pool_drifting_down_is_not_a_retrace(tmp_path):
    """Retrace means it RAN first; a flat pool easing off is a different case."""
    cfg = _mk_opt(tmp_path)
    pool = _pool(pct_h1="3.0", pct_m15="-8.0")
    assert "retracing" not in quality_verdict(pool, cfg, _fdv(pool)).reason


def test_missing_m15_skips_the_retrace_check(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = _pool(pct_h1="45.0", pct_m15=None)
    assert "retracing" not in quality_verdict(pool, cfg, _fdv(pool)).reason
