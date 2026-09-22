"""Server Schedule: self-hosted backend.

Serves the single-page app and a tiny JSON document store in SQLite.
Documents live at "<collection>/<id>" paths, e.g. "config/main" or "weeks/2026-09-28".
"""
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = os.environ.get("DB_PATH", "/data/schedule.db")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SEG = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")
MAX_DOC_BYTES = 512 * 1024

app = FastAPI(title="Server Schedule", docs_url=None, redoc_url=None)


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    folder = Path(DB_PATH).parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if not os.access(folder, os.W_OK):
        raise SystemExit(
            f"Can't write to {folder} as UID {os.getuid()}. "
            f"Fix the host folder's ownership (chown {os.getuid()}:{os.getgid()} <folder>) "
            "or set PUID/PGID to match the folder's owner."
        )
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            """CREATE TABLE IF NOT EXISTS docs(
                 collection TEXT NOT NULL,
                 id TEXT NOT NULL,
                 data TEXT NOT NULL,
                 version INTEGER NOT NULL DEFAULT 1,
                 updated_at REAL NOT NULL,
                 PRIMARY KEY(collection, id))"""
        )


init_db()


def check(collection: str, doc_id: str):
    if not (SEG.match(collection) and SEG.match(doc_id)) or doc_id in (".", ".."):
        raise HTTPException(400, "Invalid document path")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/doc/{collection}/{doc_id}")
def get_doc(collection: str, doc_id: str):
    check(collection, doc_id)
    with conn() as c:
        row = c.execute(
            "SELECT data, version FROM docs WHERE collection=? AND id=?", (collection, doc_id)
        ).fetchone()
    if not row:
        return {"exists": False, "data": None, "version": 0}
    return {"exists": True, "data": json.loads(row[0]), "version": row[1]}


@app.put("/api/doc/{collection}/{doc_id}")
def put_doc(collection: str, doc_id: str, data: dict = Body(...)):
    check(collection, doc_id)
    raw = json.dumps(data, separators=(",", ":"))
    if len(raw.encode()) > MAX_DOC_BYTES:
        raise HTTPException(413, "Document too large")
    with conn() as c:
        c.execute(
            """INSERT INTO docs(collection, id, data, version, updated_at) VALUES(?,?,?,1,?)
               ON CONFLICT(collection, id) DO UPDATE SET
                 data=excluded.data, version=docs.version+1, updated_at=excluded.updated_at""",
            (collection, doc_id, raw, time.time()),
        )
        version = c.execute(
            "SELECT version FROM docs WHERE collection=? AND id=?", (collection, doc_id)
        ).fetchone()[0]
    return {"ok": True, "version": version}


@app.get("/api/export")
def export_all():
    with conn() as c:
        rows = c.execute("SELECT collection, id, data FROM docs ORDER BY collection, id").fetchall()
    payload = {
        "app": "server-schedule",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "docs": [{"path": f"{r[0]}/{r[1]}", "data": json.loads(r[2])} for r in rows],
    }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="server-schedule-backup-{stamp}.json"'},
    )


@app.post("/api/import")
def import_all(payload: dict = Body(...)):
    docs = payload.get("docs")
    if not isinstance(docs, list):
        raise HTTPException(400, "Not a Server Schedule backup file")
    count = 0
    with conn() as c:
        for d in docs:
            path, data = d.get("path", ""), d.get("data")
            parts = path.split("/")
            if len(parts) != 2 or not isinstance(data, dict):
                continue
            check(*parts)
            c.execute(
                """INSERT INTO docs(collection, id, data, version, updated_at) VALUES(?,?,?,1,?)
                   ON CONFLICT(collection, id) DO UPDATE SET
                     data=excluded.data, version=docs.version+1, updated_at=excluded.updated_at""",
                (parts[0], parts[1], json.dumps(data, separators=(",", ":")), time.time()),
            )
            count += 1
    return {"ok": True, "imported": count}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
