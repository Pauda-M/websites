"""Deployer concentration, measured rather than eyeballed."""

from __future__ import annotations

import pytest

from pf_meme_watch.config import Config
from pf_meme_watch.models import parse_frame
from pf_meme_watch.rules import BUNDLED, CLEAN, ELEVATED, UNKNOWN, dev_share_verdict

from conftest import frames

CFG = Config()


def _launches():
    return [parse_frame(r) for r in frames()]


def test_the_bundled_launch_in_the_sample_is_caught():
    """SOCK: 214.6M of 1073M supply taken by the deployer for 7.5 SOL."""
    sock = next(p for p in _launches() if p.symbol == "SOCK")
    assert sock.dev_share == pytest.approx(0.20, abs=0.001)
    verdict = dev_share_verdict(sock, CFG)
    assert verdict.is_bundled
    assert "20.00%" in verdict.reason


def test_a_modest_deployer_buy_reads_elevated_not_bundled():
    mayhem = next(p for p in _launches() if p.symbol == "mayhem")
    assert mayhem.dev_share == pytest.approx(0.0619, abs=0.0005)
    assert dev_share_verdict(mayhem, CFG).level == ELEVATED


def test_a_launch_with_no_deployer_buy_is_clean():
    chunkee = [p for p in _launches() if p.symbol == "Chunkee"]
    zero = [p for p in chunkee if p.initial_buy == 0]
    assert zero, "fixture has a zero-buy launch"
    assert dev_share_verdict(zero[0], CFG).level == CLEAN


def test_post_migration_relaunch_reports_unknown_not_one_hundred_percent():
    """The bonk shape omits the curve figure, so the denominator is unknown.
    Reporting 100% insider-held there would be a fabricated red flag."""
    bonk = next(p for p in _launches() if p.pool == "bonk")
    assert bonk.initial_buy and bonk.initial_buy > 999_000_000
    assert bonk.tokens_in_curve is None
    assert bonk.dev_share is None
    assert dev_share_verdict(bonk, CFG).level == UNKNOWN


def test_thresholds_are_configurable():
    sock = next(p for p in _launches() if p.symbol == "SOCK")
    lenient = Config(dev_share_bundled=0.5, dev_share_elevated=0.3)
    assert dev_share_verdict(sock, lenient).level == CLEAN
    strict = Config(dev_share_bundled=0.01, dev_share_elevated=0.001)
    assert dev_share_verdict(sock, strict).is_bundled
