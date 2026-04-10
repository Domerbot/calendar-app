import json
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = "calendar.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            date      TEXT    NOT NULL,
            startTime TEXT    NOT NULL,
            endTime   TEXT    NOT NULL,
            category  TEXT    NOT NULL,
            people    TEXT    NOT NULL DEFAULT '[]',
            reminder  TEXT    NOT NULL DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Humariri Calendar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class EventIn(BaseModel):
    name: str
    date: str
    startTime: str
    endTime: str
    category: str
    people: list[str] = []
    reminder: str = ""


class Event(EventIn):
    id: int


def row_to_event(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["people"] = json.loads(d["people"])
    return d


@app.get("/events", response_model=list[Event])
def get_events():
    conn = get_db()
    rows = conn.execute("SELECT * FROM events ORDER BY date, startTime").fetchall()
    conn.close()
    return [row_to_event(r) for r in rows]


@app.post("/events", response_model=Event, status_code=201)
def create_event(event: EventIn):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO events (name, date, startTime, endTime, category, people, reminder) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            event.name,
            event.date,
            event.startTime,
            event.endTime,
            event.category,
            json.dumps(event.people),
            event.reminder,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return row_to_event(row)


@app.put("/events/{event_id}", response_model=Event)
def update_event(event_id: int, event: EventIn):
    conn = get_db()
    result = conn.execute(
        "UPDATE events SET name=?, date=?, startTime=?, endTime=?, category=?, people=?, reminder=? "
        "WHERE id=?",
        (
            event.name,
            event.date,
            event.startTime,
            event.endTime,
            event.category,
            json.dumps(event.people),
            event.reminder,
            event_id,
        ),
    )
    conn.commit()
    if result.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return row_to_event(row)


@app.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int):
    conn = get_db()
    result = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Event not found")