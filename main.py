import os
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DATABASE_URL = os.environ.get("DATABASE_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_db():
    if not DATABASE_URL:
        raise RuntimeError("Не задана переменная окружения DATABASE_URL")
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    text TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    status TEXT DEFAULT 'todo',
                    deadline TEXT,
                    notified INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS geo_notes (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    text TEXT,
                    lat DOUBLE PRECISION,
                    lng DOUBLE PRECISION
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    url TEXT,
                    title TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS subs (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    amount DOUBLE PRECISION,
                    pay_day INTEGER,
                    notified_month TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS diary (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    mood TEXT,
                    text TEXT,
                    date_str TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS countdowns (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    target_date TEXT
                )
            """)


if DATABASE_URL:
    init_db()


def send_telegram_message(chat_id, text):
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    try:
        urllib.request.urlopen(url, data=data)
    except Exception as e:
        print(f"Telegram send error: {e}")


# --- ТАЙМЕР ДЛЯ УВЕДОМЛЕНИЙ ---
@app.get("/cron")
def check_deadlines():
    now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
    with get_db() as conn:
        with conn.cursor() as c:
            # 1. Проверка дедлайнов задач
            c.execute(
                "SELECT id, user_id, title, deadline FROM tasks "
                "WHERE status = 'todo' AND deadline IS NOT NULL AND deadline != '' AND notified = 0"
            )
            for task_id, user_id, title, deadline_str in c.fetchall():
                try:
                    deadline_dt = datetime.fromisoformat(deadline_str)
                    if timedelta(hours=0) < (deadline_dt - now) <= timedelta(hours=24):
                        send_telegram_message(
                            user_id,
                            f"🔥 Внимание, дедлайн!\n\n📌 Задача: {title}\n⏰ Сдать до: {deadline_dt.strftime('%d.%m %H:%M')}",
                        )
                        c.execute("UPDATE tasks SET notified = 1 WHERE id = %s", (task_id,))
                except Exception:
                    pass

            # 2. Проверка подписок (уведомление за 1 день до списания)
            tomorrow = now + timedelta(days=1)
            current_month = now.strftime("%Y-%m")
            c.execute(
                "SELECT id, user_id, title, amount FROM subs "
                "WHERE pay_day = %s AND (notified_month IS NULL OR notified_month != %s)",
                (tomorrow.day, current_month),
            )
            for sub_id, user_id, title, amount in c.fetchall():
                send_telegram_message(
                    user_id,
                    f"💳 Напоминание об оплате!\n\nЗавтра спишут {amount} руб. за подписку «{title}».",
                )
                c.execute("UPDATE subs SET notified_month = %s WHERE id = %s", (current_month, sub_id))

    return {"status": "ok", "time": str(now)}


# --- СХЕМЫ ДАННЫХ ---
class Item(BaseModel):
    user_id: str
    text: str


class TaskCreate(BaseModel):
    user_id: str
    title: str
    deadline: Optional[str] = None


class TaskStatus(BaseModel):
    status: str


class GeoCreate(BaseModel):
    user_id: str
    text: str
    lat: float
    lng: float


class LinkCreate(BaseModel):
    user_id: str
    url: str
    title: str


class SubCreate(BaseModel):
    user_id: str
    title: str
    amount: float
    pay_day: int


class DiaryCreate(BaseModel):
    user_id: str
    mood: str
    text: str
    date_str: str


class CountdownCreate(BaseModel):
    user_id: str
    title: str
    target_date: str


# --- ЗАМЕТКИ ---
@app.get("/notes")
def get_notes(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, text FROM notes WHERE user_id = %s ORDER BY id ASC", (user_id,))
            return [{"id": r[0], "text": r[1]} for r in c.fetchall()]


@app.post("/notes")
def add_note(item: Item):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO notes (user_id, text) VALUES (%s, %s)", (item.user_id, item.text))
    return {"status": "ok"}


@app.delete("/notes/{item_id}")
def delete_note(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM notes WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- ЗАДАЧИ ---
@app.get("/tasks")
def get_tasks(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, title, status, deadline FROM tasks WHERE user_id = %s ORDER BY id ASC",
                (user_id,),
            )
            return [{"id": r[0], "title": r[1], "status": r[2], "deadline": r[3]} for r in c.fetchall()]


@app.post("/tasks")
def add_task(item: TaskCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO tasks (user_id, title, status, deadline, notified) VALUES (%s, %s, 'todo', %s, 0)",
                (item.user_id, item.title, item.deadline),
            )
    return {"status": "ok"}


@app.put("/tasks/{item_id}")
def update_task(item_id: int, status: TaskStatus):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE tasks SET status = %s WHERE id = %s", (status.status, item_id))
    return {"status": "ok"}


@app.delete("/tasks/{item_id}")
def delete_task(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM tasks WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- ГЕО ---
@app.get("/geo")
def get_geo(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, text, lat, lng FROM geo_notes WHERE user_id = %s ORDER BY id ASC",
                (user_id,),
            )
            return [{"id": r[0], "text": r[1], "lat": r[2], "lng": r[3]} for r in c.fetchall()]


@app.post("/geo")
def add_geo(item: GeoCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO geo_notes (user_id, text, lat, lng) VALUES (%s, %s, %s, %s)",
                (item.user_id, item.text, item.lat, item.lng),
            )
    return {"status": "ok"}


@app.delete("/geo/{item_id}")
def delete_geo(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM geo_notes WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- ССЫЛКИ ---
@app.get("/links")
def get_links(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, url, title FROM links WHERE user_id = %s ORDER BY id ASC", (user_id,))
            return [{"id": r[0], "url": r[1], "title": r[2]} for r in c.fetchall()]


@app.post("/links")
def add_link(item: LinkCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO links (user_id, url, title) VALUES (%s, %s, %s)",
                (item.user_id, item.url, item.title),
            )
    return {"status": "ok"}


@app.delete("/links/{item_id}")
def delete_link(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM links WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- ПОДПИСКИ ---
@app.get("/subs")
def get_subs(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, title, amount, pay_day FROM subs WHERE user_id = %s ORDER BY id ASC",
                (user_id,),
            )
            return [{"id": r[0], "title": r[1], "amount": r[2], "pay_day": r[3]} for r in c.fetchall()]


@app.post("/subs")
def add_sub(item: SubCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO subs (user_id, title, amount, pay_day) VALUES (%s, %s, %s, %s)",
                (item.user_id, item.title, item.amount, item.pay_day),
            )
    return {"status": "ok"}


@app.delete("/subs/{item_id}")
def delete_sub(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM subs WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- ДНЕВНИК ---
@app.get("/diary")
def get_diary(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, mood, text, date_str FROM diary WHERE user_id = %s ORDER BY id DESC",
                (user_id,),
            )
            return [{"id": r[0], "mood": r[1], "text": r[2], "date_str": r[3]} for r in c.fetchall()]


@app.post("/diary")
def add_diary(item: DiaryCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO diary (user_id, mood, text, date_str) VALUES (%s, %s, %s, %s)",
                (item.user_id, item.mood, item.text, item.date_str),
            )
    return {"status": "ok"}


@app.delete("/diary/{item_id}")
def delete_diary(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM diary WHERE id = %s", (item_id,))
    return {"status": "ok"}


# --- СЧЕТЧИКИ ---
@app.get("/countdowns")
def get_countdowns(user_id: str):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, title, target_date FROM countdowns WHERE user_id = %s ORDER BY id ASC",
                (user_id,),
            )
            return [{"id": r[0], "title": r[1], "target_date": r[2]} for r in c.fetchall()]


@app.post("/countdowns")
def add_countdown(item: CountdownCreate):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO countdowns (user_id, title, target_date) VALUES (%s, %s, %s)",
                (item.user_id, item.title, item.target_date),
            )
    return {"status": "ok"}


@app.delete("/countdowns/{item_id}")
def delete_countdown(item_id: int):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM countdowns WHERE id = %s", (item_id,))
    return {"status": "ok"}
