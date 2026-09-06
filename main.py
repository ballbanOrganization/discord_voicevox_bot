import logging

from app.bot import create_bot
from app.config import Settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    bot = create_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
