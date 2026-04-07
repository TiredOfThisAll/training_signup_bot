import asyncio
from aiogram import Bot

from connection import create_connection
import repository as rep
from static import TOKEN
from scheduler import scheduler_loop


async def main():
    conn = await create_connection()
    await rep.init(conn)
    bot = Bot(TOKEN)

    stop_event = asyncio.Event()

    task = asyncio.create_task(
        scheduler_loop(conn, bot, stop_event)
    )

    try:
        await asyncio.Event().wait()  # держим процесс живым
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        stop_event.set()
        task.cancel()

        await bot.session.close()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
