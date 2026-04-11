import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

load_dotenv()

# Workaround: passlib reads bcrypt.__about__.__version__ but bcrypt 4.x removed __about__
if not hasattr(_bcrypt, "__about__"):
    _bcrypt.__about__ = type("about", (), {"__version__": _bcrypt.__version__})()  # type: ignore[attr-defined]

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = "calendar.db"
PH = "%s" if DATABASE_URL else "?"  # SQL placeholder style

# JWT config — set JWT_SECRET in your environment
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    pk = "SERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts_default = "DEFAULT NOW()" if DATABASE_URL else "DEFAULT CURRENT_TIMESTAMP"

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id            {pk},
            name          TEXT      NOT NULL,
            email         TEXT      NOT NULL UNIQUE,
            password_hash TEXT      NOT NULL,
            created_at    TIMESTAMP NOT NULL {ts_default}
        )
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS events (
            id        {pk},
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


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SignupIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut


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


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def make_token(user_id: int) -> str:
    """Create a JWT that expires in JWT_EXPIRE_DAYS days."""
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Dependency: decode the Bearer token and return the user row. Raises 401 if invalid."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id, name, email FROM users WHERE id = {PH}", (user_id,))
    user = cur.fetchone()
    conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)


# ---------------------------------------------------------------------------
# Event helper
# ---------------------------------------------------------------------------

def row_to_event(row) -> dict:
    d = dict(row)
    d["people"] = json.loads(d["people"])
    # PostgreSQL lowercases column names; restore camelCase
    if "starttime" in d:
        d["startTime"] = d.pop("starttime")
    if "endtime" in d:
        d["endTime"] = d.pop("endtime")
    return d


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/signup", response_model=TokenResponse, status_code=201)
def signup(data: SignupIn):
    conn = get_db()
    cur = conn.cursor()

    # Reject duplicate emails
    cur.execute(f"SELECT id FROM users WHERE email = {PH}", (data.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")

    # bcrypt silently truncates at 72 bytes — do it explicitly so hashing and
    # verification always use the same input regardless of caller behaviour
    password_hash = pwd_context.hash(data.password.encode("utf-8")[:72])

    if DATABASE_URL:
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (data.name, data.email, password_hash),
        )
        user_id = cur.fetchone()["id"]  # type: ignore[index]
    else:
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (data.name, data.email, password_hash),
        )
        user_id = cur.lastrowid or 0

    conn.commit()
    conn.close()

    return {"token": make_token(user_id), "user": {"id": user_id, "name": data.name, "email": data.email}}


@app.post("/login", response_model=TokenResponse)
def login(data: LoginIn):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, name, email, password_hash FROM users WHERE email = {PH}",
        (data.email,),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = dict(row)
    if not pwd_context.verify(data.password.encode("utf-8")[:72], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"token": make_token(user["id"]), "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}


# ---------------------------------------------------------------------------
# Event endpoints (protected)
# ---------------------------------------------------------------------------

@app.get("/events", response_model=list[Event])
def get_events(_: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY date, startTime")
    rows = cur.fetchall()
    conn.close()
    return [row_to_event(r) for r in rows]


@app.post("/events", response_model=Event, status_code=201)
def create_event(event: EventIn, _: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    params = (
        event.name, event.date, event.startTime, event.endTime,
        event.category, json.dumps(event.people), event.reminder,
    )
    if DATABASE_URL:
        cur.execute(
            "INSERT INTO events (name, date, startTime, endTime, category, people, reminder) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            params,
        )
        new_id = cur.fetchone()["id"]  # type: ignore[index]
    else:
        cur.execute(
            "INSERT INTO events (name, date, startTime, endTime, category, people, reminder) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            params,
        )
        new_id = cur.lastrowid or 0
    conn.commit()
    cur.execute(f"SELECT * FROM events WHERE id = {PH}", (new_id,))
    row = cur.fetchone()
    conn.close()
    return row_to_event(row)


@app.put("/events/{event_id}", response_model=Event)
def update_event(event_id: int, event: EventIn, _: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE events SET name={PH}, date={PH}, startTime={PH}, endTime={PH}, "
        f"category={PH}, people={PH}, reminder={PH} WHERE id={PH}",
        (event.name, event.date, event.startTime, event.endTime,
         event.category, json.dumps(event.people), event.reminder, event_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    cur.execute(f"SELECT * FROM events WHERE id = {PH}", (event_id,))
    row = cur.fetchone()
    conn.close()
    return row_to_event(row)


@app.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, _: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM events WHERE id = {PH}", (event_id,))
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="Event not found")


@app.get("/summary")
async def get_summary(_: dict = Depends(get_current_user)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    today = date.today()
    window_end = today + timedelta(days=14)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM events WHERE date >= {PH} AND date <= {PH} ORDER BY date, startTime",
        (today.isoformat(), window_end.isoformat()),
    )
    rows = [row_to_event(r) for r in cur.fetchall()]
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
