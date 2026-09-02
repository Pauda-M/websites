"""Entry point: python -m rh_meme_watch"""

from __future__ import annotations

import logging
import sys

from .app import App
from .config import Config, ConfigError
from .telegram import TelegramError


def main() -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("rh_meme_watch")

    app = App(cfg)
    try:
        app.startup()
    except TelegramError as exc:
        log.critical("telegram startup failed, exiting: %s", exc)
        return 1

    try:
        app.run()
    except KeyboardInterrupt:
        log.info("interrupted, shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
