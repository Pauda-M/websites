"""NEW-token qualification requires socials AND liquidity, never either alone."""

from __future__ import annotations

from datetime import timedelta

from rh_meme_watch.models import Pool
from rh_meme_watch.rules import classify, meme_socials, passes_new_rule

from conftest import mk_cfg_optional as _mk_opt, NOW, api_item, mk_cfg


def test_social_without_liquidity_is_rejected(tmp_path):
    cfg = _mk_opt(tmp_path, liq_floor=150_000.0, liq_floor_stock=75_000.0)
    pool = Pool.from_api(
        api_item(name="SOCIAL / WETH", created_at=NOW, reserve="2500", socials=True)
    )
    cls = classify(pool, cfg)
    assert pool.reserve_usd == 2500.0
    assert meme_socials(pool, cls)
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_liquidity_without_social_is_rejected(tmp_path):
    cfg = _mk_opt(tmp_path)
    pool = Pool.from_api(
        api_item(name="NOSOCIAL / WETH", created_at=NOW, reserve="500000", socials=False)
    )
    cls = classify(pool, cfg)
    assert pool.reserve_usd == 500_000.0
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_social_and_liquidity_together_pass(tmp_path):
    cfg = _mk_opt(tmp_path, liq_floor=150_000.0)
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
    cfg = _mk_opt(tmp_path)
    item = api_item(name="AAPL / MEME", created_at=NOW, reserve="500000", socials=False)
    base_id = item["relationships"]["base_token"]["data"]["id"]
    item["_socials_by_token"] = {base_id: ["https://x.com/aapl"]}
    pool = Pool.from_api(item)
    cls = classify(pool, cfg)
    assert cls.meme_symbol == "MEME"
    assert not cls.meme_is_base
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_stock_paired_meme_side_social_passes(tmp_path):
    cfg = _mk_opt(tmp_path, liq_floor_stock=75_000.0)
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
    cfg = _mk_opt(tmp_path)
    item = api_item(name="OUTAGE / WETH", created_at=NOW, reserve="500000", socials=True)
    item.pop("_socials_by_token")
    pool = Pool.from_api(item)
    cls = classify(pool, cfg)
    assert not passes_new_rule(pool, cls, cfg, NOW)


def test_kill_switch_drops_the_social_requirement_but_not_liquidity(tmp_path):
    """REQUIRE_SOCIALS=0 is an outage escape hatch, not a liquidity bypass."""
    cfg = _mk_opt(tmp_path, require_socials=False, liq_floor=150_000.0)
    aged = NOW - timedelta(minutes=30)

    funded = Pool.from_api(
        api_item(name="NOSOC / WETH", created_at=aged, reserve="500000", socials=False)
    )
    assert passes_new_rule(funded, classify(funded, cfg), cfg, NOW)

    thin = Pool.from_api(
        api_item(name="THIN / WETH", created_at=aged, reserve="2500", socials=False)
    )
    assert not passes_new_rule(thin, classify(thin, cfg), cfg, NOW)


# --- where the lookup budget gets spent -------------------------------------

def test_a_lookup_is_only_spent_on_a_pool_that_cleared_everything_else(tmp_path):
    """The bug this guards: enriching discovery blindly spent the whole budget
    on pools too young to alert, so real candidates hit the social gate with no
    data and failed closed - zero alerts, and nothing in the log to say why."""
    from conftest import FakeGecko, mk_app

    too_young = api_item(
        name="NEWBORN / WETH", address="0x" + "11" * 20,
        created_at=NOW - timedelta(minutes=1), reserve="500000", socials=True,
    )
    too_thin = api_item(
        name="THIN / WETH", address="0x" + "22" * 20,
        created_at=NOW - timedelta(minutes=45), reserve="9000", socials=True,
    )
    candidate = api_item(
        name="REAL / WETH", address="0x" + "33" * 20,
        created_at=NOW - timedelta(minutes=45), reserve="500000", socials=True,
        tx_h1={"buys": 140, "sells": 70, "buyers": 90, "sellers": 45},
    )

    gecko = FakeGecko(new_items=[too_young, too_thin, candidate])
    cfg = _mk_opt(tmp_path, digest_hour=25, liq_floor=150_000.0, require_socials=True)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)

    app.run_cycle()

    assert gecko.social_calls == ["0x" + "33" * 20], (
        "exactly one lookup, on the only pool whose socials decide the outcome"
    )


def test_a_candidate_without_socials_is_rejected_and_says_so(tmp_path, caplog):
    """Failing closed is correct; failing closed silently is what hid the bug.

    The live symptom was zero alerts with an empty rejection log, because the
    social check sat inside passes_new_rule, which logs nothing. It is now a
    named, logged rejection like every other gate.
    """
    import logging

    from conftest import FakeGecko, mk_app

    anon = api_item(
        name="ANON / WETH", address="0x" + "44" * 20,
        created_at=NOW - timedelta(minutes=45), reserve="500000", socials=False,
        tx_h1={"buys": 140, "sells": 70, "buyers": 90, "sellers": 45},
    )
    gecko = FakeGecko(new_items=[anon])
    cfg = _mk_opt(tmp_path, digest_hour=25, liq_floor=150_000.0, require_socials=True)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)

    with caplog.at_level(logging.INFO, logger="rh_meme_watch.app"):
        app.run_cycle()

    assert telegram.sent == [], "no alert without a social"
    assert "no social" in caplog.text, "and the reason is logged"
    assert "ANON" in caplog.text, "naming the pool it rejected"


def test_socials_found_during_the_alert_are_persisted(tmp_path):
    """Fetched once, then available to the dashboard without refetching."""
    from conftest import FakeGecko, mk_app

    good = api_item(
        name="GOOD / WETH", address="0x" + "55" * 20,
        created_at=NOW - timedelta(minutes=45), reserve="500000", socials=True,
        tx_h1={"buys": 140, "sells": 70, "buyers": 90, "sellers": 45},
    )
    gecko = FakeGecko(new_items=[good])
    cfg = _mk_opt(tmp_path, digest_hour=25, liq_floor=150_000.0, require_socials=True)
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)

    app.run_cycle()

    from rh_meme_watch.store import Store
    row = app.store.get_pool("0x" + "55" * 20)
    assert Store.socials_of(row), "written to the store, not just used and dropped"


# --- the mismatch my tests could not previously detect ----------------------

def test_socials_match_when_the_info_endpoint_spells_ids_differently(tmp_path):
    """The bug this exists for.

    Pool relationships key tokens as "robinhood_0xabc..."; the info endpoint's
    spelling is a separate contract and nothing guarantees it matches. An
    exact-string lookup that misses yields no socials for every pool - which
    downstream is indistinguishable from a chain whose projects register none,
    and is how a live deployment produced zero alerts with 205 green tests.

    conftest builds both sides from one variable, so no existing test could
    detect this. These spell them differently on purpose.
    """
    item = api_item(name="SPELT / WETH", created_at=NOW, reserve="500000", socials=False)
    base_id = item["relationships"]["base_token"]["data"]["id"]  # robinhood_0xbase...
    address = base_id.rsplit("_", 1)[-1]
    pool = Pool.from_api(item)

    for spelling in (
        address,                    # bare address
        address.upper(),            # different case
        f"solana_{address}",        # a different network prefix
        f"eth_{address.upper()}",
    ):
        enriched = pool.with_socials({spelling: ["https://t.me/real"]})
        cls = classify(enriched, cfg_for(tmp_path))
        assert meme_socials(enriched, cls) == ("https://t.me/real",), (
            f"{spelling!r} must still match the pool's base token"
        )


def test_a_payload_that_matches_nothing_is_distinguishable_from_no_socials(tmp_path):
    """Both produce an empty result; only one is a fault, so they must differ."""
    item = api_item(name="OTHER / WETH", created_at=NOW, reserve="500000", socials=False)
    pool = Pool.from_api(item)

    assert not pool.sides_matched({}), "nothing fetched is not a mismatch"
    assert not pool.sides_matched(
        {"robinhood_0xsomethingelse": ["https://t.me/x"]}
    ), "keys that match neither side IS a mismatch"
    assert pool.sides_matched(
        {pool.base_token_id: ["https://t.me/x"]}
    ), "a genuine hit"
    assert pool.sides_matched(
        {pool.quote_token_id.rsplit("_", 1)[-1].upper(): ["https://t.me/x"]}
    ), "a hit on the quote side, differently spelled"


def cfg_for(tmp_path):
    return mk_cfg(tmp_path, require_socials=True)
