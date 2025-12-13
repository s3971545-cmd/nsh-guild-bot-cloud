import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("環境變數 DATABASE_URL 未設定（PostgreSQL 未連上）")
    return url

def get_conn():
    url = get_database_url()
    # Render Postgres 通常需要 SSL
    if "sslmode=" not in url:
        return psycopg2.connect(url, sslmode="require")
    return psycopg2.connect(url)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signups (
                    guild_id BIGINT NOT NULL,
                    user_id  BIGINT NOT NULL,
                    user_name TEXT,
                    display_name TEXT,
                    job TEXT,
                    gear TEXT,
                    availability TEXT,
                    voice TEXT,
                    note TEXT,
                    team TEXT DEFAULT '未分配',
                    timestamp TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (guild_id, user_id)
                );
            """)
        conn.commit()

def db_upsert_signup(guild_id: int, user_id: int, info: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO signups
                (guild_id, user_id, user_name, display_name, job, gear, availability, voice, note, team, timestamp, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    user_name=EXCLUDED.user_name,
                    display_name=EXCLUDED.display_name,
                    job=EXCLUDED.job,
                    gear=EXCLUDED.gear,
                    availability=EXCLUDED.availability,
                    voice=EXCLUDED.voice,
                    note=EXCLUDED.note,
                    team=EXCLUDED.team,
                    timestamp=EXCLUDED.timestamp,
                    updated_at=NOW();
            """, (
                guild_id, user_id,
                info.get("user_name"),
                info.get("display_name"),
                info.get("job"),
                info.get("gear"),
                info.get("availability"),
                info.get("voice"),
                info.get("note"),
                info.get("team", "未分配"),
                info.get("timestamp"),
            ))
        conn.commit()

def db_get_signup(guild_id: int, user_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups WHERE guild_id=%s AND user_id=%s;", (guild_id, user_id))
            return cur.fetchone()

def db_list_signups_by_guild(guild_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups WHERE guild_id=%s ORDER BY display_name ASC;", (guild_id,))
            return cur.fetchall()

def db_list_all_signups():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM signups ORDER BY guild_id ASC, display_name ASC;")
            return cur.fetchall()

def db_update_team(guild_id: int, user_id: int, team: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE signups SET team=%s, updated_at=NOW()
                WHERE guild_id=%s AND user_id=%s;
            """, (team, guild_id, user_id))
        conn.commit()
