from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

app = FastAPI()

# Разрешаем запросы из любых источников (чтобы Mini App мог стучаться на сервер)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Функция создания базы данных, если её нет
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Структура данных для новой заметки
class NoteCreate(BaseModel):
    user_id: str
    text: str

# 1. Получить все заметки конкретного пользователя по его Telegram ID
@app.get("/notes")
def get_notes(user_id: str):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, text FROM notes WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "text": row[1]} for row in rows]

# 2. Добавить новую заметку
@app.post("/notes")
def add_note(note: NoteCreate):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO notes (user_id, text) VALUES (?, ?)", (note.user_id, note.text))
    conn.commit()
    conn.close()
    return {"status": "success"}

# 3. Удалить заметку по её ID
@app.delete("/notes/{note_id}")
def delete_note(note_id: int):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}