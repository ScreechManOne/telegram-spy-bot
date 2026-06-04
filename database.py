import aiosqlite
import time

DB_FILE = "database.db"
MAX_MESSAGES_PER_USER = 50000


async def _table_columns(db, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
        return {row[1] for row in rows}


async def _ensure_column(db, table: str, column: str, col_def: str) -> None:
    if column not in await _table_columns(db, table):
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS connections (
                business_connection_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                business_connection_id TEXT,
                message_id INTEGER,
                text TEXT,
                sender_name TEXT,
                timestamp REAL,
                media_file_id TEXT,
                media_type TEXT,
                archive_message_id INTEGER,
                PRIMARY KEY (business_connection_id, message_id)
            )
        ''')
        await _ensure_column(db, "messages", "media_file_id", "TEXT")
        await _ensure_column(db, "messages", "media_type", "TEXT")
        await _ensure_column(db, "messages", "archive_message_id", "INTEGER")
        await _ensure_column(db, "messages", "sender_id", "INTEGER")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            )
        ''')
        await db.execute('''
            DELETE FROM connections WHERE rowid NOT IN (
                SELECT MAX(rowid) FROM connections GROUP BY user_id
            )
        ''')
        await db.commit()


async def add_connection(connection_id: str, user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM connections WHERE user_id = ?', (user_id,))
        await db.execute(
            'INSERT OR REPLACE INTO connections (business_connection_id, user_id) VALUES (?, ?)',
            (connection_id, user_id),
        )
        await db.commit()


async def remove_connection(connection_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM connections WHERE business_connection_id = ?', (connection_id,))
        await db.commit()


async def get_user_by_connection(connection_id: str) -> int | None:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT user_id FROM connections WHERE business_connection_id = ?',
            (connection_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_connection_for_user(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT business_connection_id FROM connections WHERE user_id = ?',
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def list_connections() -> list[tuple[int, str]]:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT user_id, business_connection_id FROM connections ORDER BY user_id'
        ) as cursor:
            return await cursor.fetchall()


async def save_message(
    connection_id: str,
    message_id: int,
    text: str,
    sender_name: str,
    media_file_id: str | None = None,
    media_type: str | None = None,
    archive_message_id: int | None = None,
    sender_id: int | None = None,
):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO messages (
                business_connection_id, message_id, text, sender_name, timestamp,
                media_file_id, media_type, archive_message_id, sender_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            connection_id, message_id, text, sender_name, time.time(),
            media_file_id, media_type, archive_message_id, sender_id,
        ))
        await db.commit()
    await cleanup_db()


async def get_message(connection_id: str, message_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('''
            SELECT text, sender_name, media_file_id, media_type, archive_message_id, sender_id
            FROM messages
            WHERE business_connection_id = ? AND message_id = ?
        ''', (connection_id, message_id)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "text": row[0],
                    "sender_name": row[1],
                    "media_file_id": row[2],
                    "media_type": row[3],
                    "archive_message_id": row[4],
                    "sender_id": row[5],
                }
            return None


async def update_message(connection_id: str, message_id: int, new_text: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE messages SET text = ?, timestamp = ?
            WHERE business_connection_id = ? AND message_id = ?
        ''', (new_text, time.time(), connection_id, message_id))
        await db.commit()


async def update_message_archive(connection_id: str, message_id: int, archive_message_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE messages SET archive_message_id = ?, timestamp = ?
            WHERE business_connection_id = ? AND message_id = ?
        ''', (archive_message_id, time.time(), connection_id, message_id))
        await db.commit()


async def cleanup_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f'''
            DELETE FROM messages WHERE rowid IN (
                SELECT m.rowid FROM messages m
                INNER JOIN connections c ON m.business_connection_id = c.business_connection_id
                WHERE m.rowid NOT IN (
                    SELECT m2.rowid FROM messages m2
                    INNER JOIN connections c2 ON m2.business_connection_id = c2.business_connection_id
                    WHERE c2.user_id = c.user_id
                    ORDER BY m2.timestamp DESC
                    LIMIT {MAX_MESSAGES_PER_USER}
                )
            )
        ''')
        await db.commit()


async def register_bot_user(user_id: int, username: str | None, full_name: str | None):
    now = time.time()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO bot_users (user_id, username, full_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen = excluded.last_seen
        ''', (user_id, username, full_name, now, now))
        await db.commit()


async def get_admin_stats() -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT COUNT(*) FROM bot_users') as cursor:
            total_users = (await cursor.fetchone())[0]
        async with db.execute('SELECT COUNT(DISTINCT user_id) FROM connections') as cursor:
            connected_users = (await cursor.fetchone())[0]
    return {"total_users": total_users, "connected_users": connected_users}


async def get_all_bot_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT user_id FROM bot_users') as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]
