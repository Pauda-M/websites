"""R3 ESCALATE (once per 6 h per address) and R4 dump warnings."""

from __future__ import annotations

from datetime import timedelta

from conftest import NOW, FakeGecko, api_item, mk_app

ADDR = "0x" + "e1" * 20


def _new_item(reserve="118000", created=None, **kw):
    return api_item(
        name="AAPLDOG / AAPL",
        address=ADDR,
        reserve=reserve,
        created_at=created or (NOW - timedelta(minutes=41)),
        **kw,
    )


def _bootstrap(tmp_path):
    gecko = FakeGecko(new_items=[_new_item()])
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert len(telegram.sent) == 1  # the NEW alert
    return app, telegram, clock, gecko


def test_escalates_on_liquidity_doubling_once_within_6h(tmp_path):
    app, telegram, clock, gecko = _bootstrap(tmp_path)

    clock.advance(minutes=30)
    gecko.new_items = []
    gecko.top_items = [_new_item(reserve="240000")]  # >= 2x first-alert liq
    app.run_cycle()
    assert len(telegram.sent) == 2
    assert "ESCALATE" in telegram.sent[1]

    # still growing 10 minutes later -> must NOT escalate again within 6 h
    clock.advance(minutes=10)
    gecko.top_items = [_new_item(reserve="300000")]
    app.run_cycle()
    assert len(telegram.sent) == 2, "escalation must fire once, not twice, within 6h"


def test_escalates_again_after_6h_cooldown(tmp_path):
    app, telegram, clock, gecko = _bootstrap(tmp_path)

    clock.advance(minutes=30)
    gecko.new_items = []
    gecko.top_items = [_new_item(reserve="240000")]
    app.run_cycle()
    assert len(telegram.sent) == 2

    clock.advance(hours=7)  # cooldown expired, condition still true
    app.run_cycle()
    assert len(telegram.sent) == 3


def test_escalates_on_h1_volume(tmp_path):
    app, telegram, clock, gecko = _bootstrap(tmp_path)

    clock.advance(minutes=30)
    gecko.new_items = []
    gecko.top_items = [_new_item(reserve="119000", vol_h1="500000")]  # >= ESC_VOL_H1
    app.run_cycle()
    assert len(telegram.sent) == 2
    assert "ESCALATE" in telegram.sent[1]


def test_no_escalation_without_condition(tmp_path):
    app, telegram, clock, gecko = _bootstrap(tmp_path)

    clock.advance(minutes=30)
    gecko.new_items = []
    gecko.top_items = [_new_item(reserve="150000", vol_h1="100000")]  # 1.27x, low vol
    app.run_cycle()
    assert len(telegram.sent) == 1


def test_never_alerted_pool_never_escalates(tmp_path):
    gecko = FakeGecko(
        top_items=[
            api_item(
                name="OLDMEME / WETH",
                address="0x" + "e2" * 20,
                reserve="900000",
                vol_h1="900000",
                created_at=NOW - timedelta(days=5),
            )
        ]
    )
    app, telegram, clock = mk_app(tmp_path, gecko)
    app.run_cycle()
    assert telegram.sent == []


def test_dump_warning_shown_inside_escalation(tmp_path):
    app, telegram, clock, gecko = _bootstrap(tmp_path)

    clock.advance(minutes=45)
    gecko.new_items = []
    gecko.top_items = [
        _new_item(
            vol_h1="600000",  # escalation via volume...
            tx_h1={"buys": 200, "sells": 300, "buyers": 60, "sellers": 100},  # ...ratio 0.6
        )
    ]
    app.run_cycle()
    assert len(telegram.sent) == 2
    assert "⚠️" in telegram.sent[1]
    assert "buyers/sellers h1 0" in telegram.sent[1].replace("\\", "")
