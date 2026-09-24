"""Identity-collision detection, calibrated on the real Chunkee cluster.

The captured sample contains three launches sharing one name and one metadata
URI, two of them from a single deployer wallet, arriving seconds apart. Spotting
that by eye does not scale to 13 launches a minute, and it fails precisely when
a real coin is running and the imitations appear.
"""

from __future__ import annotations

from pf_meme_watch.models import parse_frame
from pf_meme_watch.rules import CopycatIndex, normalize_name

from conftest import frames


def _creates():
    return [p for p in map(parse_frame, frames()) if p.is_create]


def test_the_real_copycat_cluster_is_caught():
    index = CopycatIndex()
    verdicts = []
    for i, launch in enumerate(_creates()):
        verdicts.append((launch.symbol, index.check(launch, now=1000.0 + i)))

    chunkee = [(s, v) for s, v in verdicts if s == "Chunkee"]
    assert len(chunkee) == 3, "fixture holds the cluster"
    assert not chunkee[0][1].is_copycat, "the first one is not an imitation"
    assert chunkee[1][1].is_copycat
    assert chunkee[2][1].is_copycat
    assert chunkee[2][1].same_uri == 2, "both predecessors shared its metadata"


def test_same_deployer_relaunching_is_surfaced():
    index = CopycatIndex()
    last = None
    for i, launch in enumerate(_creates()):
        last = index.check(launch, now=1000.0 + i) if launch.symbol == "Chunkee" else last
    assert last is not None
    assert last.same_deployer >= 1, "one wallet launched twice in the sample"
    assert "same wallet" in last.reason


def test_unrelated_launches_do_not_collide():
    index = CopycatIndex()
    for i, launch in enumerate(_creates()):
        verdict = index.check(launch, now=1000.0 + i)
        if launch.symbol in {"mayhem", "SOCK"}:
            assert not verdict.is_copycat, f"{launch.symbol} is distinct"


def test_a_token_re_reported_is_not_its_own_imitator():
    """The same mint appearing twice is a duplicate frame, not a copycat."""
    launch = _creates()[0]
    index = CopycatIndex()
    index.check(launch, now=1000.0)
    again = index.check(launch, now=1001.0)
    assert not again.is_copycat


def test_collisions_expire_out_of_the_window():
    launches = [p for p in _creates() if p.symbol == "Chunkee"]
    index = CopycatIndex(window_sec=60)
    index.check(launches[0], now=1000.0)
    assert index.check(launches[1], now=1030.0).is_copycat, "inside the window"
    assert not index.check(launches[2], now=5000.0).is_copycat, "long after"


def test_the_window_cannot_grow_without_bound():
    index = CopycatIndex(window_sec=10**9, memory=5)
    launch = _creates()[0]
    for i in range(200):
        index.check(launch, now=float(i))
    assert len(index._seen) <= 6


def test_name_folding_catches_lookalikes_not_coincidences():
    assert normalize_name("NO PVP ON CHUNKE") == normalize_name("no-pvp_on chunke!")
    assert normalize_name("Pépé") == normalize_name("PEPE")
    assert normalize_name("Doge") != normalize_name("Dogecoin")
    assert normalize_name("") == ""
