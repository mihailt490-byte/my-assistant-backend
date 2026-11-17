from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# === ВАЖНО: ВСТАВЬТЕ СЮДА ТОКЕН ВАШЕГО БОТА ===
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER" 
# ==============================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        # Старые таблицы
        c.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, text TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT, status TEXT DEFAULT "todo", deadline TEXT, notified INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS geo_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, text TEXT, lat REAL, lng REAL)')
        
        # Новые таблицы для 4 модулей
        c.execute('CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, url TEXT, title TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS subs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT, amount REAL, pay_day INTEGER, notified_month TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS diary (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, mood TEXT, text TEXT, date_str TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS countdowns (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT, target_date TEXT)')
        
        # Защита при обновлении старой базы
        try: c.execute('ALTER TABLE tasks ADD COLUMN deadline TEXT')
        except: pass
        try: c.execute('ALTER TABLE tasks ADD COLUMN notified INTEGER DEFAULT 0')
        except: pass
        conn.commit()

init_db()

def send_telegram_message(chat_id, text):
    if BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER": return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    try: urllib.request.urlopen(url, data=data)
    except Exception as e: print(e)

# --- ТАЙМЕР ДЛЯ УВЕДОМЛЕНИЙ ---
@app.get("/cron")
def check_deadlines():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        now = datetime.utcnow() + timedelta(hours=3) # Время по Минску/МСК
        
        # 1. Проверка дедлайнов задач
        c.execute("SELECT id, user_id, title, deadline FROM tasks WHERE status='todo' AND deadline IS NOT NULL AND deadline != '' AND notified=0")
        for row in c.fetchall():
            task_id, user_id, title, deadline_str = row
            try:
                deadline_dt = datetime.fromisoformat(deadline_str)
                if timedelta(hours=0) < (deadline_dt - now) <= timedelta(hours=24):
                    send_telegram_message(user_id, f"🔥 Внимание, дедлайн!\n\n📌 Задача: {title}\n⏰ Сдать до: {deadline_dt.strftime('%d.%m %H:%M')}")
                    c.execute("UPDATE tasks SET notified=1 WHERE id=?", (task_id,))
            except: pass

        # 2. Проверка подписок (уведомление за 1 день до списания)
        tomorrow = now + timedelta(days=1)
        current_month = now.strftime("%Y-%m")
        c.execute("SELECT id, user_id, title, amount FROM subs WHERE pay_day=? AND (notified_month IS NULL OR notified_month != ?)", (tomorrow.day, current_month))
        for row in c.fetchall():
            sub_id, user_id, title, amount = row
            send_telegram_message(user_id, f"💳 Напоминание об оплате!\n\nЗавтра спишут {amount} руб. за подписку «{title}».")
            c.execute("UPDATE subs SET notified_month=? WHERE id=?", (current_month, sub_id))

        conn.commit()
    return {"status": "ok", "time": str(now)}

# --- СХЕМЫ ДАННЫХ ---
class Item(BaseModel): user_id: str; text: str
class TaskCreate(BaseModel): user_id: str; title: str; deadline: Optional[str] = None
class TaskStatus(BaseModel): status: str
class GeoCreate(BaseModel): user_id: str; text: str; lat: float; lng: float
class LinkCreate(BaseModel): user_id: str; url: str; title: str
class SubCreate(BaseModel): user_id: str; title: str; amount: float; pay_day: int
class DiaryCreate(BaseModel): user_id: str; mood: str; text: str; date_str: str
class CountdownCreate(BaseModel): user_id: str; title: str; target_date: str

# --- СТАРЫЕ РОУТЫ (ЗАМЕТКИ, ЗАДАЧИ, ГЕО) ---
@app.get("/notes")
def get_notes(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "text": r[1]} for r in conn.cursor().execute("SELECT id, text FROM notes WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/notes")
def add_note(item: Item):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO notes (user_id, text) VALUES (?, ?)", (item.user_id, item.text))
        conn.commit()
    return {"status": "ok"}

@app.delete("/notes/{item_id}")
def delete_note(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM notes WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}

@app.get("/tasks")
def get_tasks(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "title": r[1], "status": r[2], "deadline": r[3]} for r in conn.cursor().execute("SELECT id, title, status, deadline FROM tasks WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/tasks")
def add_task(item: TaskCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO tasks (user_id, title, status, deadline, notified) VALUES (?, ?, 'todo', ?, 0)", (item.user_id, item.title, item.deadline))
        conn.commit()
    return {"status": "ok"}

@app.put("/tasks/{item_id}")
def update_task(item_id: int, status: TaskStatus):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("UPDATE tasks SET status=? WHERE id=?", (status.status, item_id))
        conn.commit()
    return {"status": "ok"}

@app.delete("/tasks/{item_id}")
def delete_task(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM tasks WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}

@app.get("/geo")
def get_geo(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "text": r[1], "lat": r[2], "lng": r[3]} for r in conn.cursor().execute("SELECT id, text, lat, lng FROM geo_notes WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/geo")
def add_geo(item: GeoCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO geo_notes (user_id, text, lat, lng) VALUES (?, ?, ?, ?)", (item.user_id, item.text, item.lat, item.lng))
        conn.commit()
    return {"status": "ok"}

@app.delete("/geo/{item_id}")
def delete_geo(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM geo_notes WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}


# --- НОВЫЕ РОУТЫ (ССЫЛКИ, ПОДПИСКИ, ДНЕВНИК, СЧЕТЧИКИ) ---

# Ссылки
@app.get("/links")
def get_links(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "url": r[1], "title": r[2]} for r in conn.cursor().execute("SELECT id, url, title FROM links WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/links")
def add_link(item: LinkCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO links (user_id, url, title) VALUES (?, ?, ?)", (item.user_id, item.url, item.title))
        conn.commit()
    return {"status": "ok"}

@app.delete("/links/{item_id}")
def delete_link(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM links WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}

# Подписки
@app.get("/subs")
def get_subs(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "title": r[1], "amount": r[2], "pay_day": r[3]} for r in conn.cursor().execute("SELECT id, title, amount, pay_day FROM subs WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/subs")
def add_sub(item: SubCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO subs (user_id, title, amount, pay_day) VALUES (?, ?, ?, ?)", (item.user_id, item.title, item.amount, item.pay_day))
        conn.commit()
    return {"status": "ok"}

@app.delete("/subs/{item_id}")
def delete_sub(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM subs WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}

# Дневник
@app.get("/diary")
def get_diary(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "mood": r[1], "text": r[2], "date_str": r[3]} for r in conn.cursor().execute("SELECT id, mood, text, date_str FROM diary WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()]

@app.post("/diary")
def add_diary(item: DiaryCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO diary (user_id, mood, text, date_str) VALUES (?, ?, ?, ?)", (item.user_id, item.mood, item.text, item.date_str))
        conn.commit()
    return {"status": "ok"}

@app.delete("/diary/{item_id}")
def delete_diary(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM diary WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}

# Счетчики
@app.get("/countdowns")
def get_countdowns(user_id: str):
    with sqlite3.connect("database.db") as conn:
        return [{"id": r[0], "title": r[1], "target_date": r[2]} for r in conn.cursor().execute("SELECT id, title, target_date FROM countdowns WHERE user_id=?", (user_id,)).fetchall()]

@app.post("/countdowns")
def add_countdown(item: CountdownCreate):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("INSERT INTO countdowns (user_id, title, target_date) VALUES (?, ?, ?)", (item.user_id, item.title, item.target_date))
        conn.commit()
    return {"status": "ok"}

@app.delete("/countdowns/{item_id}")
def delete_countdown(item_id: int):
    with sqlite3.connect("database.db") as conn:
        conn.cursor().execute("DELETE FROM countdowns WHERE id=?", (item_id,))
        conn.commit()
    return {"status": "ok"}
