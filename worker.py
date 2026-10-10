import asyncio
from aiogram import Bot
import os
from loguru import logger

from connection import create_connection
import repository as rep
from static import TOKEN
from scheduler import scheduler_loop


async def main():
    conn = await create_connection()
    bot = Bot(TOKEN)

    os.makedirs("logs", exist_ok=True)

    logger.add(
        "logs/scheduler.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )

    try:
        await rep.init(conn)

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await scheduler_loop(conn, bot, stop_event)

    finally:
        await bot.session.close()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
