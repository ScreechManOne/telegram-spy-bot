import aiosqlite
import time

DB_FILE = "database.db"
MAX_GLOBAL_MESSAGES = 1000


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
        await db.commit()


async def add_connection(connection_id: str, user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
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


async def save_message(
    connection_id: str,
    message_id: int,
    text: str,
    sender_name: str,
    media_file_id: str | None = None,
    media_type: str | None = None,
    archive_message_id: int | None = None,
):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR REPLACE INTO messages (
                business_connection_id, message_id, text, sender_name, timestamp,
                media_file_id, media_type, archive_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            connection_id, message_id, text, sender_name, time.time(),
            media_file_id, media_type, archive_message_id,
        ))
        await db.commit()
    await cleanup_db()


async def get_message(connection_id: str, message_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('''
            SELECT text, sender_name, media_file_id, media_type, archive_message_id
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
            DELETE FROM messages WHERE rowid NOT IN (
                SELECT rowid FROM messages ORDER BY timestamp DESC LIMIT {MAX_GLOBAL_MESSAGES}
            )
        ''')
        await db.commit()
