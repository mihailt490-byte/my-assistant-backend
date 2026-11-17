from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# === ВАЖНО: ВСТАВЬТЕ СЮДА ТОКЕН ВАШЕГО БОТА ===
BOT_TOKEN = "9109464866:AAFBOp81sTq44ZAqvxAPx11LT7k2qIwhDog" 
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
        c.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, text TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT, status TEXT DEFAULT "todo", deadline TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS geo_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, text TEXT, lat REAL, lng REAL)')
        
        # Добавляем колонки для дедлайнов и защиты от спама уведомлениями
        try:
            c.execute('ALTER TABLE tasks ADD COLUMN deadline TEXT')
        except:
            pass
        try:
            c.execute('ALTER TABLE tasks ADD COLUMN notified INTEGER DEFAULT 0')
        except:
            pass
        conn.commit()

init_db()

# --- СИСТЕМА ОТПРАВКИ УВЕДОМЛЕНИЙ ---
def send_telegram_message(chat_id, text):
    if BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        return # Защита от ошибок, если токен не заменили
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    try:
        urllib.request.urlopen(url, data=data)
    except Exception as e:
        print("Ошибка отправки Telegram:", e)

# --- СПЕЦИАЛЬНЫЙ РОУТ ДЛЯ ТАЙМЕРА (КРУГЛОСУТОЧНАЯ РАБОТА) ---
@app.get("/cron")
def check_deadlines():
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        # Ищем активные задачи с дедлайном, о которых еще не уведомляли
        c.execute("SELECT id, user_id, title, deadline FROM tasks WHERE status='todo' AND deadline IS NOT NULL AND deadline != '' AND notified=0")
        tasks = c.fetchall()

        # Сервер Render живет по UTC, прибавляем 3 часа для времени Беларуси (МСК)
        now = datetime.utcnow() + timedelta(hours=3)

        for row in tasks:
            task_id, user_id, title, deadline_str = row
            try:
                # Читаем время из базы
                deadline_dt = datetime.fromisoformat(deadline_str)
                diff = deadline_dt - now
                
                # Если до дедлайна осталось от 0 до 24 часов
                if timedelta(hours=0) < diff <= timedelta(hours=24):
                    msg = f"🔥 Внимание, дедлайн!\n\n📌 Задача: {title}\n⏰ Сдать до: {deadline_dt.strftime('%d.%m %H:%M')}"
                    send_telegram_message(user_id, msg)
                    
                    # Отмечаем, что уведомление отправлено, чтобы не спамить
                    c.execute("UPDATE tasks SET notified=1 WHERE id=?", (task_id,))
            except Exception as e:
                pass
        conn.commit()
    return {"status": "ok", "time": str(now)}

# --- Схемы данных ---
class Item(BaseModel):
    user_id: str
    text: str

class TaskCreate(BaseModel):
    user_id: str
    title: str
    deadline: Optional[str] = None

class TaskStatus(BaseModel):
    status: str

class GeoNoteCreate(BaseModel):
    user_id: str
    text: str
    lat: float
    lng: float

# --- 1. ЗАМЕТКИ ---
@app.get("/notes")
def get_notes(user_id: str):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, text FROM notes WHERE user_id=?", (user_id,))
        return [{"id": row[0], "text": row[1]} for row in c.fetchall()]

@app.post("/notes")
def add_note(item: Item):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO notes (user_id, text) VALUES (?, ?)", (item.user_id, item.text))
        conn.commit()
    return {"status": "ok"}

@app.delete("/notes/{note_id}")
def delete_note(note_id: int):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.commit()
    return {"status": "ok"}

# --- 2. ЗАДАЧИ ---
@app.get("/tasks")
def get_tasks(user_id: str):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, status, deadline FROM tasks WHERE user_id=?", (user_id,))
        return [{"id": row[0], "title": row[1], "status": row[2], "deadline": row[3]} for row in c.fetchall()]

@app.post("/tasks")
def add_task(task: TaskCreate):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tasks (user_id, title, status, deadline, notified) VALUES (?, ?, 'todo', ?, 0)", (task.user_id, task.title, task.deadline))
        conn.commit()
    return {"status": "ok"}

@app.put("/tasks/{task_id}")
def update_task_status(task_id: int, task_status: TaskStatus):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE tasks SET status=? WHERE id=?", (task_status.status, task_id))
        conn.commit()
    return {"status": "ok"}

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
    return {"status": "ok"}

# --- 3. ГЕО-ЗАМЕТКИ ---
@app.get("/geo")
def get_geo(user_id: str):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, text, lat, lng FROM geo_notes WHERE user_id=?", (user_id,))
        return [{"id": row[0], "text": row[1], "lat": row[2], "lng": row[3]} for row in c.fetchall()]

@app.post("/geo")
def add_geo(item: GeoNoteCreate):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO geo_notes (user_id, text, lat, lng) VALUES (?, ?, ?, ?)", (item.user_id, item.text, item.lat, item.lng))
        conn.commit()
    return {"status": "ok"}

@app.delete("/geo/{geo_id}")
def delete_geo(geo_id: int):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM geo_notes WHERE id=?", (geo_id,))
        conn.commit()
    return {"status": "ok"}
