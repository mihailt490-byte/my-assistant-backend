from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from fastapi.middleware.cors import CORSMiddleware

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
        # Таблица для заметок
        c.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, text TEXT)')
        # Новая таблица для задач
        c.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, title TEXT, status TEXT DEFAULT "todo")')
        conn.commit()

init_db()

# --- Схемы данных ---
class Item(BaseModel):
    user_id: str
    text: str

class TaskCreate(BaseModel):
    user_id: str
    title: str

class TaskStatus(BaseModel):
    status: str

# --- МОДУЛЬ ЗАМЕТОК ---
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

# --- НОВЫЙ МОДУЛЬ ЗАДАЧ ---
@app.get("/tasks")
def get_tasks(user_id: str):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, status FROM tasks WHERE user_id=?", (user_id,))
        return [{"id": row[0], "title": row[1], "status": row[2]} for row in c.fetchall()]

@app.post("/tasks")
def add_task(task: TaskCreate):
    with sqlite3.connect("database.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tasks (user_id, title, status) VALUES (?, ?, 'todo')", (task.user_id, task.title))
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
