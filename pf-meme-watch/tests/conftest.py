from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE = Path(__file__).parent / "fixture_pumpportal_frames.jsonl"


def frames() -> list[dict]:
    """Real frames captured from the live stream."""
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
