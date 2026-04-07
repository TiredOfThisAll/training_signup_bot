import sqlite3
from loguru import logger

import models


async def init(conn):
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS managed_chats (
        chat_id INTEGER PRIMARY KEY
    )
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS weekly_practice (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER NOT NULL,
        weekday INTEGER NOT NULL,
        registration_start TEXT,
        registration_end TEXT,
        train_start TEXT,
        train_end TEXT,
        max_participants INTEGER
    )
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY,
        chat_id INTEGER NOT NULL,
        user_id INTEGER,
        username TEXT,
        full_name TEXT,
        UNIQUE(user_id, chat_id)
    )
    """)

    await conn.commit()


async def has_time_conflict(conn, chat_id, weekday, start, end):
    logger.debug(
        f"has_time_conflict chat_id: {chat_id}, weekday: {weekday}, start: {start}, end: {end}"
    )
    cursor = await conn.execute("""
        SELECT 1
        FROM weekly_practice
        WHERE chat_id = ?
        AND weekday = ?
        AND NOT (
            registration_end <= ? OR registration_start >= ?
        )
    """, (chat_id, weekday, start, end))

    return await cursor.fetchone() is not None


# ----- managed_chats -----


async def get_managed_chats(conn):
    cursor = await conn.execute("SELECT chat_id FROM managed_chats")
    rows = await cursor.fetchall()
    return [models.ManagedChat(*row) for row in rows]


async def get_or_create_managed_chat(conn, chat_id):

    await conn.execute("""
        INSERT OR IGNORE INTO managed_chats (chat_id)
        VALUES (?)
    """, (chat_id,))
    await conn.commit()

    cursor = await conn.execute("""
        SELECT chat_id FROM managed_chats WHERE chat_id = ?
    """, (chat_id,))
    row = await cursor.fetchone()

    return models.ManagedChat(*row)


async def remove_managed_chat(conn, chat_id):
    await conn.execute("DELETE FROM participants WHERE chat_id = ?", (chat_id,))
    await conn.execute("DELETE FROM weekly_practice WHERE chat_id = ?", (chat_id,))
    await conn.execute("DELETE FROM managed_chats WHERE chat_id = ?", (chat_id,))
    await conn.commit()


# ----- weekly_practice -----


async def get_training_schedule(conn, chat_id):
    cursor = await conn.execute("""
        SELECT id, chat_id, weekday,
               registration_start, registration_end,
               train_start, train_end,
               max_participants
        FROM weekly_practice
        WHERE chat_id = ?
        ORDER BY weekday
    """, (chat_id,))
    rows = await cursor.fetchall()
    return [models.WeeklyPractice(*row) for row in rows]


async def create_weekly_practice(
    conn,
    chat_id: int,
    weekday: int,
    registration_start: str,
    registration_end: str,
    train_start: str,
    train_end: str,
    max_participants: int
):
    await conn.execute("""
        INSERT OR IGNORE INTO managed_chats (chat_id)
        VALUES (?)
    """, (chat_id,))

    cursor = await conn.execute("""
        INSERT INTO weekly_practice (
            chat_id, weekday,
            registration_start, registration_end,
            train_start, train_end,
            max_participants
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        weekday,
        registration_start, registration_end,
        train_start, train_end,
        max_participants
    ))

    await conn.commit()
    return cursor.rowcount > 0


async def remove_weekly_practice(conn, weekly_practice_id: int):
    await conn.execute("""
        DELETE FROM weekly_practice WHERE id = ?
    """, (weekly_practice_id,))
    await conn.commit()


# ----- participants -----


async def get_participants(conn, chat_id):
    cursor = await conn.execute("""
        SELECT id, chat_id, user_id, username, full_name
        FROM participants
        WHERE chat_id = ?
    """, (chat_id,))
    rows = await cursor.fetchall()
    return [models.Participant(*row) for row in rows]


async def add_participant(conn, chat_id, user_id, username, full_name):
    try:
        logger.debug(f"ADD participant {user_id} to chat {chat_id}")
        await conn.execute("""
            INSERT OR IGNORE INTO managed_chats (chat_id)
            VALUES (?)
        """, (chat_id,))
        cursor = await conn.execute("""
            INSERT INTO participants (chat_id, user_id, username, full_name)
            VALUES (?, ?, ?, ?)
        """, (chat_id, user_id, username, full_name))

        await conn.commit()
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        return False


async def remove_participant(conn, chat_id, user_id):
    logger.debug(f"REMOVE participant {user_id} from chat {chat_id}")
    cursor = await conn.execute("""
        DELETE FROM participants
        WHERE user_id = ?
        AND chat_id = ?
    """, (user_id, chat_id))
    await conn.commit()
    return cursor.rowcount != 0


async def count_participants(conn, chat_id):
    cursor = await conn.execute("""
        SELECT COUNT(*)
        FROM participants
        WHERE chat_id = ?
    """, (chat_id,))
    row = await cursor.fetchone()
    return row[0]


async def clear_participants(conn, chat_id):
    await conn.execute("""
        DELETE FROM participants
        WHERE chat_id = ?
    """, (chat_id,))
    await conn.commit()
