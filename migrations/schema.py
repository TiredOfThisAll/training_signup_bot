async def _table_exists(conn, table_name: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return await cursor.fetchone() is not None


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    cursor = await conn.execute(f"PRAGMA table_info({table_name})")
    columns = await cursor.fetchall()
    return any(column[1] == column_name for column in columns)


async def migrate_schema(conn):
    has_managed_chats = await _table_exists(conn, "managed_chats")
    has_lists = await _table_exists(conn, "lists")
    has_weekly_practice = await _table_exists(conn, "weekly_practice")
    has_training_days_table = await _table_exists(conn, "training_days")
    has_participants = await _table_exists(conn, "participants")

    if has_lists and not has_managed_chats:
        await conn.execute("ALTER TABLE lists RENAME TO managed_chats")
        has_managed_chats = True

    if not has_managed_chats:
        await conn.execute(
            """
            CREATE TABLE managed_chats (
                chat_id INTEGER PRIMARY KEY
            )
            """
        )

    if has_training_days_table and not has_weekly_practice:
        await conn.execute("ALTER TABLE training_days RENAME TO weekly_practice")
        has_weekly_practice = True

    if not has_weekly_practice:
        await conn.execute(
            """
            CREATE TABLE weekly_practice (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                weekday INTEGER,
                registration_start TEXT,
                registration_end TEXT,
                train_start TEXT,
                train_end TEXT,
                max_participants INTEGER
            )
            """
        )

    if await _column_exists(conn, "weekly_practice", "list_id"):
        await conn.execute(
            """
            ALTER TABLE weekly_practice
            RENAME COLUMN list_id TO chat_id
            """
        )

    if await _column_exists(conn, "weekly_practice", "day"):
        await conn.execute(
            """
            ALTER TABLE weekly_practice
            RENAME COLUMN day TO weekday
            """
        )

    if await _column_exists(conn, "weekly_practice", "reg_start"):
        await conn.execute(
            """
            ALTER TABLE weekly_practice
            RENAME COLUMN reg_start TO registration_start
            """
        )

    if await _column_exists(conn, "weekly_practice", "reg_end"):
        await conn.execute(
            """
            ALTER TABLE weekly_practice
            RENAME COLUMN reg_end TO registration_end
            """
        )

    if has_participants and await _column_exists(conn, "participants", "list_id"):
        await conn.execute(
            """
            ALTER TABLE participants
            RENAME COLUMN list_id TO chat_id
            """
        )

    if has_participants:
        await conn.execute(
            """
            UPDATE participants
            SET chat_id = (
                SELECT chat_id
                FROM managed_chats mc
                WHERE mc.rowid = participants.chat_id
            )
            WHERE chat_id IN (SELECT rowid FROM managed_chats)
            """
        )

    await conn.execute(
        """
        UPDATE weekly_practice
        SET chat_id = (
            SELECT chat_id
            FROM managed_chats mc
            WHERE mc.rowid = weekly_practice.chat_id
        )
        WHERE chat_id IN (SELECT rowid FROM managed_chats)
        """
    )

    if has_participants:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS participants_new (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                UNIQUE(user_id, chat_id)
            )
            """
        )
        await conn.execute(
            """
            INSERT OR IGNORE INTO participants_new (
                id, chat_id, user_id, username, full_name
            )
            SELECT id, chat_id, user_id, username, full_name
            FROM participants
            """
        )
        await conn.execute("DROP TABLE participants")
        await conn.execute("ALTER TABLE participants_new RENAME TO participants")
    else:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                UNIQUE(user_id, chat_id)
            )
            """
        )
