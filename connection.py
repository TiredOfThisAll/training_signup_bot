import aiosqlite
from static import DB_PATH


async def create_connection():
    conn = await aiosqlite.connect(DB_PATH)

    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA busy_timeout = 5000")

    return conn
