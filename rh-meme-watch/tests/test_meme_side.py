"""Meme-side resolution and classification on constructed names."""

from __future__ import annotations

from rh_meme_watch.models import Pool, split_pool_name
from rh_meme_watch.rules import classify

from conftest import api_item, mk_cfg


def _classify(tmp_path, name: str):
    cfg = mk_cfg(tmp_path)
    pool = Pool.from_api(api_item(name=name))
    return pool, classify(pool, cfg)


def test_stock_base_meme_quote(tmp_path):
    pool, cls = _classify(tmp_path, "AMZN / WADDLES")
    assert cls.is_stock_paired
    assert cls.stock_symbol == "AMZN"
    assert cls.meme_symbol == "WADDLES"
    assert cls.meme_is_base is False


def test_meme_base_stock_quote(tmp_path):
    pool, cls = _classify(tmp_path, "AAPLDOG / AAPL")
    assert cls.is_stock_paired
    assert cls.stock_symbol == "AAPL"
    assert cls.meme_symbol == "AAPLDOG"
    assert cls.meme_is_base is True


def test_all_named_pairs_classify_stock_paired(tmp_path):
    for name, meme in [
        ("AI / NVDA", "AI"),
        ("MOO / MU", "MOO"),
        ("BONER / HIMS", "BONER"),
        ("AAPLCAT / AAPL", "AAPLCAT"),
        ("CLIPPY / MSFT", "CLIPPY"),
    ]:
        _, cls = _classify(tmp_path, name)
        assert cls.is_stock_paired, name
        assert cls.meme_symbol == meme


def test_plain_meme_pool_not_stock_paired(tmp_path):
    _, cls = _classify(tmp_path, "PEPE / WETH")
    assert not cls.is_stock_paired
    assert cls.meme_symbol == "PEPE"
    assert cls.meme_is_base is True


def test_stock_vs_stable_has_no_meme_side(tmp_path):
    _, cls = _classify(tmp_path, "AMZN / USDG")
    assert cls.is_stock_paired  # a stock is present...
    assert cls.meme_symbol is None  # ...but there is nothing meme to alert on


def test_gld_lowercase_is_excluded(tmp_path):
    _, cls = _classify(tmp_path, "gld / USDG")
    assert cls.meme_symbol is None


def test_fee_suffix_is_stripped():
    assert split_pool_name("MOONPIG / AAPL 0.3%") == ("MOONPIG", "AAPL")
    assert split_pool_name("WETH / USDC 0.05%") == ("WETH", "USDC")
    assert split_pool_name("SOLO") == ("SOLO", "")


def test_case_insensitive_stock_match(tmp_path):
    _, cls = _classify(tmp_path, "doggy / aapl")
    assert cls.is_stock_paired
    assert cls.meme_symbol == "doggy"
