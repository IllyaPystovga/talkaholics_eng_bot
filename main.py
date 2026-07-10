import asyncio
import logging
import os
import sys
from pathlib import Path

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from dotenv import load_dotenv

from handlers import router


class AdminIdMiddleware(BaseMiddleware):
    def __init__(self, admin_id: int) -> None:
        self.admin_id = admin_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["admin_id"] = self.admin_id
        return await handler(event, data)

BASE_DIR = Path(__file__).resolve().parent


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Environment variable {name} is not set in .env file")
    return value


async def main() -> None:
    load_dotenv(BASE_DIR / ".env", override=True)

    bot_token = get_required_env("BOT_TOKEN")
    admin_id = int(get_required_env("ADMIN_ID"))

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(AdminIdMiddleware(admin_id))
    dp.include_router(router)

    logger = logging.getLogger(__name__)
    logger.info("Bot is starting...")

    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("Bot stopped due to an error")
        raise
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        asyncio.run(main())
    except ValueError as error:
        logger.error("%s", error)
        logger.error(
            "Створіть файл .env у папці проєкту та вкажіть BOT_TOKEN і ADMIN_ID. "
            "Приклад є у файлі .env.example"
        )
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
