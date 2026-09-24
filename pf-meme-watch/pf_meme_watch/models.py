"""pump.fun stream frames -> a typed launch record.

Every quirk handled here was observed in captured live frames
(tests/fixture_pumpportal_frames.jsonl), not inferred from documentation:

- Three ``pool`` values appear: ``pump`` (standard bonding-curve launch, full
  field set), ``bonk`` (post-migration relaunch, carries ``tokensInPool`` and
  ``newTokenBalance`` instead of the bonding-curve fields and has no
  ``uri``/``name``/``symbol``), and ``raydium-cpmm`` (seen on migrations).
- ``txType: "migrate"`` frames carry only signature, mint and pool. No metrics,
  no metadata. Anything that needs a number must look it up separately.
- Subscription acknowledgements arrive on the same socket as data, shaped
  ``{"message": "..."}``. They are not launches.
- ``marketCapSol`` is denominated in SOL, not USD. Converting needs a SOL price;
  this module does not guess one.
- ``initialBuy`` can be 0 (deployer created without buying), a dust amount, or
  most of the supply. It is only meaningful against ``vTokensInBondingCurve``,
  which the ``bonk`` shape does not carry - so dev share is None there rather
  than a fabricated 100%.
"""

from __future__ import annotations

from dataclasses import dataclass

CREATE = "create"
MIGRATE = "migrate"
STATUS = "status"


def _f(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


@dataclass(frozen=True)
class Launch:
    """One stream frame. ``kind`` is create / migrate / status."""

    kind: str
    signature: str = ""
    mint: str = ""
    pool: str = ""
    deployer: str = ""
    name: str = ""
    symbol: str = ""
    uri: str = ""
    initial_buy: float | None = None
    sol_amount: float | None = None
    tokens_in_curve: float | None = None
    sol_in_curve: float | None = None
    mcap_sol: float | None = None
    mayhem: bool = False
    message: str = ""

    @property
    def is_create(self) -> bool:
        return self.kind == CREATE

    @property
    def dev_share(self) -> float | None:
        """Deployer's share of supply at creation, 0.0-1.0, or None if unknowable.

        This is the direct measurement that a first-candle eyeball estimates:
        total supply at creation is what the deployer took plus what remains in
        the curve. Without the curve figure the denominator is unknown, and a
        guess here would be worse than no reading - so ``bonk`` relaunches, which
        omit it, return None rather than appearing to be 100% insider-held.
        """
        bought = self.initial_buy
        remaining = self.tokens_in_curve
        if bought is None or remaining is None:
            return None
        total = bought + remaining
        if total <= 0:
            return None
        share = bought / total
        return share if 0.0 <= share <= 1.0 else None

    def mcap_usd(self, sol_price_usd: float | None) -> float | None:
        """marketCapSol is in SOL; without a price there is no USD figure."""
        if self.mcap_sol is None or not sol_price_usd or sol_price_usd <= 0:
            return None
        return self.mcap_sol * sol_price_usd


def parse_frame(raw: dict) -> Launch:
    """Parse one frame. Unknown shapes come back as STATUS rather than raising -
    the socket must never die on a message this code has not seen before."""
    if not isinstance(raw, dict):
        return Launch(kind=STATUS, message="non-object frame")

    if raw.get("message") is not None and raw.get("txType") is None:
        return Launch(kind=STATUS, message=_s(raw.get("message")))

    tx_type = _s(raw.get("txType")).lower()
    if tx_type == MIGRATE:
        return Launch(
            kind=MIGRATE,
            signature=_s(raw.get("signature")),
            mint=_s(raw.get("mint")),
            pool=_s(raw.get("pool")),
        )
    if tx_type != CREATE:
        return Launch(kind=STATUS, message=f"unhandled txType {tx_type!r}")

    return Launch(
        kind=CREATE,
        signature=_s(raw.get("signature")),
        mint=_s(raw.get("mint")),
        pool=_s(raw.get("pool")),
        deployer=_s(raw.get("traderPublicKey")),
        name=_s(raw.get("name")),
        symbol=_s(raw.get("symbol")),
        uri=_s(raw.get("uri")),
        initial_buy=_f(raw.get("initialBuy")),
        sol_amount=_f(raw.get("solAmount")),
        tokens_in_curve=_f(raw.get("vTokensInBondingCurve")),
        sol_in_curve=_f(raw.get("vSolInBondingCurve")),
        mcap_sol=_f(raw.get("marketCapSol")),
        mayhem=bool(raw.get("is_mayhem_mode")),
    )
