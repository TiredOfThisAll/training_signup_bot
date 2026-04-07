import aiosqlite
from static import DB_PATH


async def create_connection():
    conn = await aiosqlite.connect(DB_PATH)
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn