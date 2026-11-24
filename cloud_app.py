import os
import json
import psycopg2
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ.get("UPLOAD_API_KEY", "change-this-secret-key")


def get_conn():
    if "sslmode=" in DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(DATABASE_URL, sslmode="require")


class ScbUpload(BaseModel):
    shop_name: str
    file_name: str
    last_updated: str
    total_visitors: int
    payload: dict


@app.on_event("startup")
def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS store_scb_snapshots (
                    shop_name TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    total_visitors INTEGER NOT NULL DEFAULT 0,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()
    finally:
        conn.close()


@app.post("/api/upload")
def upload_scb(data: ScbUpload, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO store_scb_snapshots (shop_name, file_name, last_updated, total_visitors, payload, synced_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (shop_name) DO UPDATE SET
                    file_name = EXCLUDED.file_name,
                    last_updated = EXCLUDED.last_updated,
                    total_visitors = EXCLUDED.total_visitors,
                    payload = EXCLUDED.payload,
                    synced_at = NOW();
            """, (data.shop_name, data.file_name, data.last_updated, data.total_visitors, json.dumps(data.payload)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    return {"status": "ok"}


@app.get("/api/shops")
def list_shops():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT shop_name, file_name, last_updated, total_visitors, payload, synced_at
                FROM store_scb_snapshots
                ORDER BY shop_name;
            """)
            rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    return [
        {
            "shop_name": r[0],
            "file_name": r[1],
            "last_updated": r[2],
            "total_visitors": r[3],
