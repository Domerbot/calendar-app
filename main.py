import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

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


@app.get("/summary")
async def get_summary():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    today = date.today()
    window_end = today + timedelta(days=14)

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM events WHERE date >= ? AND date <= ? ORDER BY date, startTime",
        (today.isoformat(), window_end.isoformat()),
    ).fetchall()
    conn.close()

    if not rows:
        return {"summary": "Nothing in the calendar for the next two weeks — a great chance to relax before the big move to Spain!"}

    events_text = "\n".join(
        f"- {r['date']} {r['startTime']}–{r['endTime']}: {r['name']} "
        f"(category: {r['category']}, people: {r['people']}, reminder: {r['reminder']})"
        for r in rows
    )

    prompt = (
        "You are a warm, friendly family assistant for the Humariri family: "
        "Mark, Julie, Ryan, and Noah. They are preparing to move from the UK to Spain in July 2026 "
        "and are excited about the adventure ahead.\n\n"
        "Here are their upcoming events for the next 14 days:\n"
        f"{events_text}\n\n"
        "Write a short, friendly 3–4 sentence summary of the week ahead. "
        "Highlight the key events, mention who is involved by name, and end with one warm or fun observation "
        "about the family or their upcoming move to Spain. Keep it upbeat and personal."
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.7,
            },
            timeout=20,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="OpenAI request failed")

    summary = response.json()["choices"][0]["message"]["content"].strip()
    return {"summary": summary}