from app.bot import create_bot
from app.config import Settings


def main() -> None:
    settings = Settings.from_env()
    bot = create_bot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
