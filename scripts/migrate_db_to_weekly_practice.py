import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name for column in columns)


def drop_object_if_exists(conn: sqlite3.Connection, object_type: str, name: str) -> None:
    conn.execute(f"DROP {object_type} IF EXISTS {name}")


def make_backup(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}_before_migration_{timestamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def create_chat_id_map(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS _chat_id_map")
    conn.execute(
        """
        CREATE TEMP TABLE _chat_id_map (
            source_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL
        )
        """
    )

    if table_exists(conn, "managed_chats"):
        has_id = column_exists(conn, "managed_chats", "id")
        source_id_expr = "id" if has_id else "rowid"
        conn.execute(
            f"""
            INSERT OR IGNORE INTO _chat_id_map (source_id, chat_id)
            SELECT {source_id_expr}, chat_id
            FROM managed_chats
            """
        )

    if table_exists(conn, "lists"):
        conn.execute(
            """
            INSERT OR IGNORE INTO _chat_id_map (source_id, chat_id)
            SELECT id, chat_id
            FROM lists
            """
        )


def create_new_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS managed_chats_new")
    conn.execute("DROP TABLE IF EXISTS weekly_practice_new")
    conn.execute("DROP TABLE IF EXISTS participants_new")

    conn.execute(
        """
        CREATE TABLE managed_chats_new (
            chat_id INTEGER PRIMARY KEY
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE weekly_practice_new (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            registration_start TEXT,
            registration_end TEXT,
            train_start TEXT,
            train_end TEXT,
            max_participants INTEGER
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE participants_new (
            id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            UNIQUE(user_id, chat_id)
        )
        """
    )


def copy_managed_chats(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO managed_chats_new (chat_id)
        SELECT chat_id
        FROM _chat_id_map
        """
    )

    if table_exists(conn, "weekly_practice") and column_exists(conn, "weekly_practice", "chat_id"):
        conn.execute(
            """
            INSERT OR IGNORE INTO managed_chats_new (chat_id)
            SELECT DISTINCT chat_id
            FROM weekly_practice
            WHERE chat_id IS NOT NULL
            """
        )

    if table_exists(conn, "participants") and column_exists(conn, "participants", "chat_id"):
        conn.execute(
            """
            INSERT OR IGNORE INTO managed_chats_new (chat_id)
            SELECT DISTINCT chat_id
            FROM participants
            WHERE chat_id IS NOT NULL
            """
        )


def copy_weekly_practice(conn: sqlite3.Connection) -> None:
    source_table = None
    if table_exists(conn, "weekly_practice"):
        source_table = "weekly_practice"
    elif table_exists(conn, "training_days"):
        source_table = "training_days"
    elif table_exists(conn, "training_day"):
        source_table = "training_day"

    if source_table is None:
        return

    if column_exists(conn, source_table, "weekday"):
        weekday_expr = "src.weekday"
    else:
        weekday_expr = "src.day"

    if column_exists(conn, source_table, "registration_start"):
        registration_start_expr = "src.registration_start"
        registration_end_expr = "src.registration_end"
    else:
        registration_start_expr = "src.reg_start"
        registration_end_expr = "src.reg_end"

    if column_exists(conn, source_table, "chat_id"):
        chat_id_expr = "src.chat_id"
        join_sql = ""
    else:
        chat_id_expr = "m.chat_id"
        join_sql = "JOIN _chat_id_map m ON m.source_id = src.list_id"

    conn.execute(
        f"""
        INSERT OR IGNORE INTO weekly_practice_new (
            id,
            chat_id,
            weekday,
            registration_start,
            registration_end,
            train_start,
            train_end,
            max_participants
        )
        SELECT
            src.id,
            {chat_id_expr},
            {weekday_expr},
            {registration_start_expr},
            {registration_end_expr},
            src.train_start,
            src.train_end,
            src.max_participants
        FROM {source_table} src
        {join_sql}
        WHERE {chat_id_expr} IS NOT NULL
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO managed_chats_new (chat_id)
        SELECT DISTINCT chat_id
        FROM weekly_practice_new
        """
    )


def copy_participants(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "participants"):
        return

    if column_exists(conn, "participants", "chat_id"):
        chat_id_expr = "p.chat_id"
        join_sql = ""
    else:
        chat_id_expr = "m.chat_id"
        join_sql = "JOIN _chat_id_map m ON m.source_id = p.list_id"

    conn.execute(
        f"""
        INSERT OR IGNORE INTO participants_new (
            id,
            chat_id,
            user_id,
            username,
            full_name
        )
        SELECT
            p.id,
            {chat_id_expr},
            p.user_id,
            p.username,
            p.full_name
        FROM participants p
        {join_sql}
        WHERE {chat_id_expr} IS NOT NULL
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO managed_chats_new (chat_id)
        SELECT DISTINCT chat_id
        FROM participants_new
        """
    )


def drop_legacy_objects(conn: sqlite3.Connection) -> None:
    for table_name in [
        "participants",
        "weekly_practice",
        "training_days",
        "training_day",
        "managed_chats",
        "lists",
    ]:
        if table_exists(conn, table_name):
            drop_object_if_exists(conn, "TABLE", table_name)


def rename_new_tables(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE managed_chats_new RENAME TO managed_chats")
    conn.execute("ALTER TABLE weekly_practice_new RENAME TO weekly_practice")
    conn.execute("ALTER TABLE participants_new RENAME TO participants")


def migrate(db_path: Path, no_backup: bool) -> Path | None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_path = None if no_backup else make_backup(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")

        create_chat_id_map(conn)
        create_new_tables(conn)
        copy_managed_chats(conn)
        copy_weekly_practice(conn)
        copy_participants(conn)
        drop_legacy_objects(conn)
        rename_new_tables(conn)

        conn.commit()
        return backup_path
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate bot.db to managed_chats / weekly_practice / registration_* / weekday."
    )
    parser.add_argument(
        "--db",
        default="bot.db",
        help="Path to SQLite database. Default: bot.db",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a backup copy before migration.",
    )
    args = parser.parse_args()

    db_path = Path(args.db).resolve()

    try:
        backup_path = migrate(db_path, no_backup=args.no_backup)
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    print(f"Migration completed: {db_path}")
    if backup_path is not None:
        print(f"Backup created: {backup_path}")
    print("New tables: managed_chats, weekly_practice, participants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
