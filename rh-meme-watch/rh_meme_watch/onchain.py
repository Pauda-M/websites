"""On-chain verification against the Robinhood Chain RPC (Arbitrum Orbit, chain 4663).

Three things are read directly from the chain, because the GeckoTerminal API
cannot answer them:

1. **LP custody** - for v2-style pools (fungible LP tokens) the LP total supply
   and who holds it. Measured on this chain 2026-09-12: nobody burns LP, and a
   single owner-controlled contract held 100% of the LP of every v2 pool
   sampled. So the useful output is not "locked: yes/no" but *who* custodies the
   LP and whether that balance moves.
2. **LP movement** - a drop in the custodian's LP balance is the actual rug
   event, observable at block level instead of inferred from price.
3. **Reserve verification** - the quote-token balance actually held by the pool
   contract, so the liquidity floor can be checked against the chain rather than
   trusted from the API (which is also where negative reserves come from).

Pools whose "address" is a 32-byte pool id (uniswap-v4, bankr) have no per-pool
contract, and v3 pools hold liquidity as NFT positions rather than fungible LP;
both are reported as not-applicable rather than guessed at.

The RPC rejects requests carrying Python's default urllib User-Agent, so a real
one is always sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("rh_meme_watch.onchain")

USER_AGENT = (
    "rh-meme-watch/0.1 (Robinhood Chain pool watcher; github.com/Pauda-M/rh-meme-watch)"
)

# Function selectors (keccak256 of the signature, first 4 bytes).
SEL_TOTAL_SUPPLY = "0x18160ddd"
SEL_BALANCE_OF = "0x70a08231"
SEL_TOKEN0 = "0x0dfe1681"
SEL_TOKEN1 = "0xd21220a7"
SEL_DECIMALS = "0x313ce567"
TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

BURN_ADDRESSES = (
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
)

# Custody kinds
FUNGIBLE_LP = "fungible_lp"
NOT_APPLICABLE = "not_applicable"
UNKNOWN = "unknown"


class RpcError(RuntimeError):
    pass


def _pad_address(addr: str) -> str:
    return addr.lower().removeprefix("0x").rjust(64, "0")


def _is_contract_address(addr: str) -> bool:
    """A 20-byte hex address. v4/bankr pool ids are 32 bytes and have no contract."""
    return addr.startswith("0x") and len(addr) == 42


class RpcClient:
    def __init__(
        self,
        url: str,
        http: httpx.Client | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.url = url
        self._own_http = http is None
        self.http = http or httpx.Client(timeout=httpx.Timeout(timeout))
        self.calls = 0

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def _post(self, method: str, params: list[Any]) -> Any:
        self.calls += 1
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            resp = self.http.post(
                self.url,
                json=payload,
                headers={"content-type": "application/json", "user-agent": USER_AGENT},
            )
        except httpx.HTTPError as exc:
            raise RpcError(f"{method}: transport error: {exc!r}") from exc
        if resp.status_code != 200:
            raise RpcError(f"{method}: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise RpcError(f"{method}: invalid JSON") from exc
        if "error" in body:
            raise RpcError(f"{method}: {body['error'].get('message', 'rpc error')}")
        return body.get("result")

    def chain_id(self) -> int | None:
        try:
            return int(self._post("eth_chainId", []), 16)
        except (RpcError, TypeError, ValueError):
            return None

    def eth_call(self, to: str, data: str) -> str | None:
        """Returns the hex result, or None when the call reverts / returns nothing."""
        try:
            result = self._post("eth_call", [{"to": to, "data": data}, "latest"])
        except RpcError as exc:
            log.debug("eth_call %s %s failed: %s", to, data[:10], exc)
            return None
        if not result or result == "0x":
            return None
        return result

    def call_uint(self, to: str, data: str) -> int | None:
        raw = self.eth_call(to, data)
        if raw is None:
            return None
        try:
            return int(raw, 16)
        except ValueError:
            return None

    def call_address(self, to: str, data: str) -> str | None:
        raw = self.eth_call(to, data)
        if raw is None or len(raw) < 42:
            return None
        return "0x" + raw[-40:]

    def balance_of(self, token: str, holder: str) -> int | None:
        return self.call_uint(token, SEL_BALANCE_OF + _pad_address(holder))

    def transfer_counterparties(self, token: str, limit: int = 8) -> list[str]:
        """Addresses seen in this token's Transfer logs, newest first, zero excluded."""
        try:
            logs = self._post(
                "eth_getLogs",
                [
                    {
                        "address": token,
                        "topics": [TOPIC_TRANSFER],
                        "fromBlock": "0x0",
                        "toBlock": "latest",
                    }
                ],
            )
        except RpcError as exc:
            log.debug("eth_getLogs for %s failed: %s", token, exc)
            return []
        out: list[str] = []
        for entry in reversed(logs or []):
            for topic in (entry.get("topics") or [])[1:3]:
                if not isinstance(topic, str) or len(topic) < 42:
                    continue
                addr = "0x" + topic[-40:]
                if int(addr, 16) == 0 or addr in out or addr.lower() == token.lower():
                    continue
                out.append(addr)
                if len(out) >= limit:
                    return out
        return out


@dataclass(frozen=True)
class Custody:
    """Who holds a pool's LP tokens, and how much of the supply."""

    kind: str  # FUNGIBLE_LP | NOT_APPLICABLE | UNKNOWN
    total_supply: int | None = None
    holder: str | None = None
    holder_units: int | None = None
    holder_pct: float | None = None
    burned_pct: float | None = None
    note: str = ""

    @property
    def label(self) -> str:
        if self.kind == NOT_APPLICABLE:
            return "n/a"
        if self.kind == UNKNOWN:
            return "unknown"
        if self.burned_pct is not None and self.burned_pct >= 99.0:
            return "burned"
        if self.holder_pct is not None and self.holder_pct >= 90.0:
            return "single custodian"
        if self.holder_pct is not None:
            return "dispersed"
        return "unknown"


@dataclass(frozen=True)
class OnchainReserve:
    """Quote-token units actually held by the pool contract."""

    ok: bool
    quote_token: str | None = None
    quote_units: float | None = None
    reserve_usd: float | None = None
    note: str = ""


class OnchainVerifier:
    def __init__(self, rpc: RpcClient, known_custodians: dict[str, str] | None = None) -> None:
        self.rpc = rpc
        # address (lowercase) -> human label, e.g. the launchpad custodian
        self.known: dict[str, str] = {
            k.lower(): v for k, v in (known_custodians or {}).items()
        }

    def custody(self, pool_address: str) -> Custody:
        if not _is_contract_address(pool_address):
            return Custody(
                NOT_APPLICABLE,
                note="32-byte pool id (uniswap-v4 / bankr): no per-pool contract",
            )
        total = self.rpc.call_uint(pool_address, SEL_TOTAL_SUPPLY)
        if not total:
            return Custody(
                NOT_APPLICABLE,
                note="no ERC-20 LP supply (concentrated liquidity / NFT positions)",
            )

        burned = 0
        for addr in BURN_ADDRESSES:
            burned += self.rpc.balance_of(pool_address, addr) or 0
        burned_pct = 100.0 * burned / total

        # Known custodians first (one call each), then discover via Transfer logs.
        candidates = list(self.known.keys())
        best_holder, best_units = None, 0
        for addr in candidates:
            units = self.rpc.balance_of(pool_address, addr) or 0
            if units > best_units:
                best_holder, best_units = addr, units
        if best_units * 2 < total:  # nobody known holds a majority -> look it up
            for addr in self.rpc.transfer_counterparties(pool_address):
                units = self.rpc.balance_of(pool_address, addr) or 0
                if units > best_units:
                    best_holder, best_units = addr, units
                if best_units * 2 >= total:
                    break

        holder_pct = 100.0 * best_units / total if best_holder else None
        label_note = self.known.get((best_holder or "").lower(), "")
        return Custody(
            FUNGIBLE_LP,
            total_supply=total,
            holder=best_holder,
            holder_units=best_units or None,
            holder_pct=holder_pct,
            burned_pct=burned_pct,
            note=label_note,
        )

    def reserve(self, pool_address: str, quote_price_usd: float | None) -> OnchainReserve:
        """Pool liquidity in USD from the chain: 2 x quote-token balance x price.

        The balance is trustless; only the quote price still comes from the API.
        """
        if not _is_contract_address(pool_address):
            return OnchainReserve(False, note="32-byte pool id: no per-pool contract")
        token1 = self.rpc.call_address(pool_address, SEL_TOKEN1)
        token0 = self.rpc.call_address(pool_address, SEL_TOKEN0)
        if token1 is None and token0 is None:
            return OnchainReserve(False, note="pool exposes no token0/token1")

        for token in (token1, token0):
            if token is None:
                continue
            units_raw = self.rpc.balance_of(token, pool_address)
            if units_raw is None:
                continue
            decimals = self.rpc.call_uint(token, SEL_DECIMALS)
            decimals = 18 if decimals is None or decimals > 36 else decimals
            units = units_raw / (10**decimals)
            usd = 2.0 * units * quote_price_usd if quote_price_usd else None
            return OnchainReserve(
                True, quote_token=token, quote_units=units, reserve_usd=usd
            )
        return OnchainReserve(False, note="token balances unreadable")
