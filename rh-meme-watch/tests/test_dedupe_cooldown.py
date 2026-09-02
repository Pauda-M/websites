"""Dedupe on pool address and the 24 h per-symbol cooldown."""

from __future__ import annotations

from datetime import timedelta

from conftest import NOW, Clock, FakeGecko, api_item, mk_app


def test_same_address_twice_alerts_once(tmp_path):
    item = api_item(
        name="AAPLDOG / AAPL",
        address="0x" + "ab" * 20,
        reserve="118000",
        created_at=NOW - timedelta(minutes=41),
    )
    gecko = FakeGecko(new_items=[item, item])  # duplicated within one response
    app, telegram, clock = mk_app(tmp_path, gecko)

    app.run_cycle()
    assert len(telegram.sent) == 1

    app.run_cycle()  # same pool seen again next cycle
    assert len(telegram.sent) == 1


def test_same_symbol_second_pool_suppressed_within_cooldown(tmp_path):
    first = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "01" * 20,
        reserve="190000",
        created_at=NOW - timedelta(minutes=20),
    )
    gecko = FakeGecko(new_items=[first])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert len(telegram.sent) == 1

    # a decoy pool for the same symbol shows up an hour later, passing R1 on its own
    clock.advance(hours=1)
    decoy = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "02" * 20,
        reserve="200000",
        created_at=clock.now - timedelta(minutes=15),
    )
    gecko.new_items = [decoy]
    app.run_cycle()
    assert len(telegram.sent) == 1, "decoy within the 24h symbol cooldown must not alert"


def test_same_symbol_alerts_after_cooldown_expiry(tmp_path):
    first = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "03" * 20,
        reserve="190000",
        created_at=NOW - timedelta(minutes=20),
    )
    gecko = FakeGecko(new_items=[first])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert len(telegram.sent) == 1

    clock.advance(hours=25)  # cooldown over
    fresh = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "04" * 20,
        reserve="210000",
        created_at=clock.now - timedelta(minutes=10),
    )
    gecko.new_items = [fresh]
    app.run_cycle()
    assert len(telegram.sent) == 2


def test_second_symbol_pool_must_pass_r1_itself(tmp_path):
    first = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "05" * 20,
        reserve="190000",
        created_at=NOW - timedelta(minutes=20),
    )
    gecko = FakeGecko(new_items=[first])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()

    clock.advance(hours=25)
    weak_decoy = api_item(
        name="CLIPPY / MSFT",
        address="0x" + "06" * 20,
        reserve="5100",  # below every floor
        created_at=clock.now - timedelta(minutes=5),
    )
    gecko.new_items = [weak_decoy]
    app.run_cycle()
    assert len(telegram.sent) == 1, "cooldown expiry alone must not alert a weak decoy"
