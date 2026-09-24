"""Deployer concentration and copycat detection for pump.fun launches.

Both of these replace manual work. Deployer concentration is normally estimated
by eyeballing the shape of a launch's first candle; the stream reports the
underlying numbers, so it is measured instead. Copycat launches are normally
spotted by noticing a familiar name, which does not scale to 13 launches a
minute and fails exactly when a real coin is running and the imitations appear.

Neither produces a verdict it cannot support. An unknown deployer share reports
UNKNOWN, never "clean" - an unmeasured risk is not an absent one.
"""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field

from .config import Config
from .models import Launch

CLEAN = "clean"
ELEVATED = "elevated"
BUNDLED = "bundled"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class DevShareVerdict:
    level: str
    share: float | None = None

    @property
    def is_bundled(self) -> bool:
        return self.level == BUNDLED

    @property
    def reason(self) -> str:
        if self.share is None:
            return "deployer share unmeasurable"
        return f"deployer holds {self.share * 100:.2f}% at launch ({self.level})"


def dev_share_verdict(launch: Launch, cfg: Config) -> DevShareVerdict:
    """Grade how much of the supply the deployer took at creation."""
    share = launch.dev_share
    if share is None:
        return DevShareVerdict(UNKNOWN)
    if share >= cfg.dev_share_bundled:
        return DevShareVerdict(BUNDLED, share)
    if share >= cfg.dev_share_elevated:
        return DevShareVerdict(ELEVATED, share)
    return DevShareVerdict(CLEAN, share)


_PUNCT = re.compile(r"[^a-z0-9]+")


def normalize_name(text: str) -> str:
    """Fold a name for collision matching.

    Imitators reach for lookalikes rather than exact copies, so accents are
    stripped and case and punctuation are dropped. This is deliberately not
    fuzzy matching - a shared metadata URI or a folded-identical name is
    concrete evidence, whereas an edit-distance threshold invents borderline
    cases that need judging.
    """
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _PUNCT.sub("", folded.lower())


@dataclass(frozen=True)
class CopycatVerdict:
    """What else has launched under this identity recently."""

    same_name: int = 0
    same_uri: int = 0
    same_deployer: int = 0
    first_seen: bool = True

    @property
    def is_copycat(self) -> bool:
        return not self.first_seen and (self.same_name > 0 or self.same_uri > 0)

    @property
    def reason(self) -> str:
        if self.first_seen:
            return "first under this identity"
        parts = []
        if self.same_uri:
            parts.append(f"{self.same_uri} sharing its metadata")
        if self.same_name:
            parts.append(f"{self.same_name} sharing its name")
        if self.same_deployer:
            parts.append(f"{self.same_deployer} from the same wallet")
        return "; ".join(parts) or "seen before"


@dataclass
class CopycatIndex:
    """Rolling window of recent launches, for identity-collision lookups.

    Bounded by both age and count so a long-running process cannot grow without
    limit at 13 launches a minute.
    """

    window_sec: int = 900
    memory: int = 4_000
    _seen: deque = field(default_factory=deque)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_sec
        while self._seen and self._seen[0][0] < cutoff:
            self._seen.popleft()
        while len(self._seen) > self.memory:
            self._seen.popleft()

    def check(self, launch: Launch, now: float) -> CopycatVerdict:
        """Compare against the window, then record. Order matters: a launch must
        not match itself."""
        self._evict(now)
        name = normalize_name(launch.name) or normalize_name(launch.symbol)
        uri = (launch.uri or "").strip()
        deployer = launch.deployer or ""

        same_name = same_uri = same_deployer = 0
        for _, prev_name, prev_uri, prev_dev, prev_mint in self._seen:
            if prev_mint == launch.mint:
                continue  # the same token re-reported is not an imitation
            if name and prev_name == name:
                same_name += 1
            if uri and prev_uri == uri:
                same_uri += 1
            if deployer and prev_dev == deployer:
                same_deployer += 1

        self._seen.append((now, name, uri, deployer, launch.mint))
        return CopycatVerdict(
            same_name=same_name,
            same_uri=same_uri,
            same_deployer=same_deployer,
            first_seen=not (same_name or same_uri),
        )


@dataclass(frozen=True)
class Regime:
    """Market context recorded with an alert - never a gate on it.

    The source checklist claims memecoins run more easily when Bitcoin is rising,
    then states in the next breath that many of the largest runners appeared when
    Bitcoin was falling. As a filter that would suppress the very launches it
    says made the most money, so this is stamped onto alerts as context and
    measured against outcomes later, rather than being allowed to block anything.
    """

    btc_pct_24h: float | None = None
    hour_utc: int | None = None
    weekday: int | None = None

    @property
    def label(self) -> str:
        if self.btc_pct_24h is None:
            return "unknown"
        if self.btc_pct_24h >= 2.0:
            return "btc-up"
        if self.btc_pct_24h <= -2.0:
            return "btc-down"
        return "btc-flat"
