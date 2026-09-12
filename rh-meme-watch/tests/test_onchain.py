"""On-chain verification: custody reads, reserve reads, LP-MOVED alerting.

The RPC is mocked with respx; the encodings mirror what the live chain returned
on 2026-09-12 (chain 4663), including the fact that nobody burns LP there.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import respx

from rh_meme_watch.onchain import (
    FUNGIBLE_LP,
    NOT_APPLICABLE,
    SEL_BALANCE_OF,
    SEL_DECIMALS,
    SEL_TOKEN0,
    SEL_TOKEN1,
    SEL_TOTAL_SUPPLY,
    Custody,
    OnchainVerifier,
    RpcClient,
)

from conftest import NOW, FakeGecko, api_item, mk_app, mk_cfg

RPC = "https://rpc.test/robinhood"
POOL = "0x9da17e29dad5823f3822fc46ddd736c4de405c1d"
V4_ID = "0x9fc198dc34217e98cd95d0fb93641810182ae002226d2d9701b57680d552374c"  # 32 bytes
CUSTODIAN = "0x2ac03e14cfe755426daaee0a4994184ce81482f8"
TOKEN_WETH = "0x1111111111111111111111111111111111111111"


def _word(value: int) -> str:
    return "0x" + f"{value:064x}"


def _addr_word(addr: str) -> str:
    return "0x" + addr.lower().removeprefix("0x").rjust(64, "0")


def _router(calls: dict[tuple[str, str], str], logs: list | None = None):
    """Route eth_call by (to, selector-or-full-calldata); everything else reverts."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        import json as _json

        payload = _json.loads(body)
        method = payload["method"]
        if method == "eth_getLogs":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": logs or []})
        if method == "eth_chainId":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1237"})
        if method != "eth_call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x"})
        to = payload["params"][0]["to"].lower()
        data = payload["params"][0]["data"].lower()
        for (ct, cd), result in calls.items():
            if ct.lower() == to and data.startswith(cd.lower()):
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "revert"}},
        )

    return handler


def _verifier(calls, logs=None, custodians=None) -> OnchainVerifier:
    respx.post(RPC).mock(side_effect=_router(calls, logs))
    return OnchainVerifier(
        RpcClient(RPC, http=httpx.Client(trust_env=False)),
        custodians if custodians is not None else {CUSTODIAN: "v2 launchpad custodian"},
    )


@respx.mock
def test_rpc_sends_a_real_user_agent():
    """The live RPC 403s Python's default urllib UA - never ship without one."""
    route = respx.post(RPC).mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x1237"})
    )
    client = RpcClient(RPC, http=httpx.Client(trust_env=False))
    assert client.chain_id() == 4663
    ua = route.calls[0].request.headers["user-agent"]
    assert "rh-meme-watch" in ua and "urllib" not in ua.lower()


@respx.mock
def test_32_byte_pool_id_is_not_applicable():
    v = _verifier({})
    c = v.custody(V4_ID)
    assert c.kind == NOT_APPLICABLE
    assert "pool id" in c.note
    assert c.label == "n/a"
    assert v.reserve(V4_ID, 1.0, TOKEN_WETH).ok is False


@respx.mock
def test_concentrated_liquidity_pool_is_not_applicable():
    """A v3 pool has no ERC-20 LP supply: totalSupply reverts -> n/a, not a guess."""
    v = _verifier({})  # every call reverts
    c = v.custody(POOL)
    assert c.kind == NOT_APPLICABLE
    assert "concentrated" in c.note


@respx.mock
def test_single_custodian_detected_with_zero_burn():
    """The measured reality on this chain: 0% burned, one contract holds 100%."""
    total = 13_033_173_363_683_014_091
    v = _verifier(
        {
            (POOL, SEL_TOTAL_SUPPLY): _word(total),
            (POOL, SEL_BALANCE_OF + _addr_word(CUSTODIAN)[2:]): _word(total),
        }
    )
    c = v.custody(POOL)
    assert c.kind == FUNGIBLE_LP
    assert c.total_supply == total
    assert c.holder == CUSTODIAN
    assert c.holder_pct == 100.0
    assert c.burned_pct == 0.0
    assert c.label == "single custodian"
    assert c.note == "v2 launchpad custodian"


@respx.mock
def test_burned_lp_is_reported_as_burned():
    total = 1_000_000
    zero = "0x0000000000000000000000000000000000000000"
    v = _verifier(
        {
            (POOL, SEL_TOTAL_SUPPLY): _word(total),
            (POOL, SEL_BALANCE_OF + _addr_word(zero)[2:]): _word(total),
        }
    )
    c = v.custody(POOL)
    assert c.burned_pct == 100.0
    assert c.label == "burned"


@respx.mock
def test_holder_discovered_from_transfer_logs_when_unknown():
    total = 500
    mystery = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    logs = [
        {
            "topics": [
                "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                _addr_word("0x0000000000000000000000000000000000000000"),
                _addr_word(mystery),
            ]
        }
    ]
    v = _verifier(
        {
            (POOL, SEL_TOTAL_SUPPLY): _word(total),
            (POOL, SEL_BALANCE_OF + _addr_word(mystery)[2:]): _word(total),
        },
        logs=logs,
        custodians={},
    )
    c = v.custody(POOL)
    assert c.holder == mystery
    assert c.holder_pct == 100.0
    assert c.label == "single custodian"


@respx.mock
def test_reserve_read_from_chain_in_usd():
    """2 x quote-token balance x quote price; balance is trustless, price is not."""
    v = _verifier(
        {
            (POOL, SEL_TOKEN1): _addr_word(TOKEN_WETH),
            (TOKEN_WETH, SEL_BALANCE_OF + _addr_word(POOL)[2:]): _word(3 * 10**18),
            (TOKEN_WETH, SEL_DECIMALS): _word(18),
        }
    )
    r = v.reserve(POOL, 2500.0, TOKEN_WETH)
    assert r.ok is True
    assert r.quote_units == 3.0
    assert r.reserve_usd == 15000.0  # 2 * 3 * 2500


@respx.mock
def test_reserve_uses_the_named_quote_token_not_token0_token1_order():
    """v2 orders token0/token1 by address: guessing multiplies the MEME balance by
    the quote price and yields nonsense (seen live: $38.6T for a $303k pool)."""
    meme = "0x2222222222222222222222222222222222222222"
    v = _verifier(
        {
            # token0 is the meme side here, token1 the quote side
            (POOL, SEL_TOKEN0): _addr_word(meme),
            (POOL, SEL_TOKEN1): _addr_word(TOKEN_WETH),
            (meme, SEL_BALANCE_OF + _addr_word(POOL)[2:]): _word(15_000_000 * 10**18),
            (meme, SEL_DECIMALS): _word(18),
            (TOKEN_WETH, SEL_BALANCE_OF + _addr_word(POOL)[2:]): _word(60 * 10**18),
            (TOKEN_WETH, SEL_DECIMALS): _word(18),
        }
    )
    r = v.reserve(POOL, 2500.0, TOKEN_WETH)
    assert r.quote_token == TOKEN_WETH
    assert r.reserve_usd == 300_000.0  # 2 * 60 * 2500, not 15M * 2500


@respx.mock
def test_reserve_refuses_a_token_that_is_not_a_pool_side():
    stranger = "0x3333333333333333333333333333333333333333"
    v = _verifier(
        {
            (POOL, SEL_TOKEN0): _addr_word("0x2222222222222222222222222222222222222222"),
            (POOL, SEL_TOKEN1): _addr_word(TOKEN_WETH),
        }
    )
    r = v.reserve(POOL, 2500.0, stranger)
    assert r.ok is False
    assert "not a side" in r.note


@respx.mock
def test_reserve_without_a_known_quote_token_returns_not_ok():
    """A wrong number is worse than no number."""
    v = _verifier({(POOL, SEL_TOKEN1): _addr_word(TOKEN_WETH)})
    assert v.reserve(POOL, 2500.0, None).ok is False


@respx.mock
def test_reserve_handles_unreadable_tokens():
    v = _verifier({(POOL, SEL_TOKEN1): _addr_word(TOKEN_WETH)})  # balanceOf reverts
    assert v.reserve(POOL, 2500.0, TOKEN_WETH).ok is False


@respx.mock
def test_rpc_failure_degrades_without_raising():
    respx.post(RPC).mock(side_effect=httpx.ConnectError("dns"))
    v = OnchainVerifier(RpcClient(RPC, http=httpx.Client(trust_env=False)), {})
    c = v.custody(POOL)
    assert c.kind == NOT_APPLICABLE  # unreadable supply is never treated as locked
    assert v.reserve(POOL, 1.0, TOKEN_WETH).ok is False


class FakeVerifier:
    """Scripted custody/reserve results per call, for app-level wiring tests."""

    def __init__(self, sequence: list[Custody]) -> None:
        self.sequence = sequence
        self.calls = 0

    def custody(self, address: str) -> Custody:
        item = self.sequence[min(self.calls, len(self.sequence) - 1)]
        self.calls += 1
        return item

    def reserve(self, address: str, price, quote_token=None):
        from rh_meme_watch.onchain import OnchainReserve

        return OnchainReserve(True, quote_token=TOKEN_WETH, quote_units=1.0, reserve_usd=None)


def _alerting_app(tmp_path, verifier, ttl: int = 0):
    cfg = mk_cfg(tmp_path, digest_hour=25, rpc_url=RPC, onchain_cache_ttl_sec=ttl)
    item = api_item(
        name="MAPLE / WETH",
        address=POOL,
        reserve="310000",
        created_at=NOW - timedelta(minutes=20),
    )
    gecko = FakeGecko(new_items=[item], top_items=[item])
    app, telegram, clock = mk_app(tmp_path, gecko, cfg=cfg)
    app.onchain = verifier
    return app, telegram, clock


def test_lp_moved_alert_fires_when_custodian_balance_drops(tmp_path):
    full = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 1000, 100.0, 0.0, "v2 launchpad custodian")
    drained = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 400, 40.0, 0.0, "v2 launchpad custodian")
    app, telegram, clock = _alerting_app(tmp_path, FakeVerifier([full, drained]))

    app.run_cycle()
    assert len(telegram.sent) == 1, "NEW alert only; first on-chain read is the baseline"

    clock.advance(minutes=1)
    app.run_cycle()
    assert len(telegram.sent) == 2
    assert "LP MOVED" in telegram.sent[1]
    assert "60.0% of the custodied LP left" in telegram.sent[1].replace("\\", "")


def test_no_lp_moved_alert_when_custody_is_stable(tmp_path):
    full = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 1000, 100.0, 0.0, "")
    app, telegram, clock = _alerting_app(tmp_path, FakeVerifier([full, full, full]))
    for _ in range(3):
        app.run_cycle()
        clock.advance(minutes=1)
    assert len(telegram.sent) == 1


def test_onchain_results_cached_by_ttl(tmp_path):
    full = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 1000, 100.0, 0.0, "")
    verifier = FakeVerifier([full])
    app, telegram, clock = _alerting_app(tmp_path, verifier, ttl=1800)
    app.run_cycle()
    clock.advance(minutes=5)
    app.run_cycle()
    assert verifier.calls == 1, "second cycle inside the TTL must not re-read the chain"
    clock.advance(minutes=31)
    app.run_cycle()
    assert verifier.calls == 2


def test_dashboard_shows_custody_badge(tmp_path):
    from rh_meme_watch.dashboard import collect, render_html

    full = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 1000, 100.0, 0.0, "v2 launchpad custodian")
    app, telegram, clock = _alerting_app(tmp_path, FakeVerifier([full]))
    app.run_cycle()

    data = collect(app.cfg.db_path, app.cfg, clock.now)
    pool = data["pools"][0]
    assert pool["custody"] == "single custodian"
    assert pool["custody_pct"] == 100.0
    assert pool["burned_pct"] == 0.0

    page = render_html(app.cfg.db_path, app.cfg, clock.now, show_all=True)
    assert "1 custodian" in page
    assert "LP custody read from the RPC" in page


def test_onchain_disabled_without_rpc_url(tmp_path):
    cfg = mk_cfg(tmp_path, digest_hour=25)
    assert cfg.rpc_url == ""
    item = api_item(name="MAPLE / WETH", address=POOL, reserve="310000",
                    created_at=NOW - timedelta(minutes=20))
    app, telegram, clock = mk_app(tmp_path, FakeGecko(new_items=[item]), cfg=cfg)
    assert app.onchain is None
    app.run_cycle()
    assert len(telegram.sent) == 1


def test_pool_no_longer_in_the_api_window_is_still_custody_checked(tmp_path):
    """The rug moment: a pool drops out of the API's top-40, LP is then pulled.

    Custody is a pure chain read, so the sweep is driven from the store and the
    alert still fires with details reconstructed from stored pool state.
    """
    full = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 1000, 100.0, 0.0, "v2 launchpad custodian")
    drained = Custody(FUNGIBLE_LP, 1000, CUSTODIAN, 100, 10.0, 0.0, "v2 launchpad custodian")
    verifier = FakeVerifier([full, drained])
    app, telegram, clock = _alerting_app(tmp_path, verifier)

    app.run_cycle()  # pool visible: alerts + baseline custody read
    assert len(telegram.sent) == 1

    # the pool now vanishes from both API windows
    app.gecko.new_items = []
    app.gecko.top_items = []
    clock.advance(minutes=1)
    app.run_cycle()

    assert verifier.calls == 2, "custody must still be read for an invisible pool"
    assert len(telegram.sent) == 2
    body = telegram.sent[1].replace("\\", "")
    assert "LP MOVED" in body
    assert "MAPLE / WETH" in body  # name reconstructed from the store
    assert "90.0% of the custodied LP left" in body
