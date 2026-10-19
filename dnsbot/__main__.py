from __future__ import annotations

import logging
import sys

from dnsbot.bot import create_bot
from dnsbot.config import load_settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def main() -> None:
    # genkey helper
    if len(sys.argv) > 1 and sys.argv[1] in ("--genkey", "-g"):
        from dnsbot.config import generate_crypto_key

        generate_crypto_key()
        return

    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)

    bot = create_bot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
