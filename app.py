import sqlite3, os, json
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_super_secret_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# Инициализация базы с нуля
def init_db():
    if os.path.exists('flux.db'): os.remove('flux.db')
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    # Юзеры: добавлена почта, аватар и статус админа
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    # Чаты: Community, Каналы, Лички
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)')
    # Сообщения + Реакции (храним реакции как JSON строку)
    cur.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, text TEXT, reactions TEXT DEFAULT "{}")')
    
    # Создаем тебя - Основателя
    pw = generate_password_hash('admin123')
    cur.execute("INSERT INTO users VALUES ('bloody', 'founder@flux.chat', ?, 'https://i.pravatar.cc/150?u=bloody', 1)", (pw,))
    # Создаем общий чат
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    d = request.json
    conn = sqlite3.connect('flux.db')
    try:
        pw = generate_password_hash(d['password'])
        conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, f"https://i.pravatar.cc/150?u={d['nick']}", 0))
        conn.commit()
        return jsonify({"status": "ok"})
    except: return jsonify({"status": "error", "message": "Ник или Email занят"})
    finally: conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    conn = sqlite3.connect('flux.db')
    user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
    conn.close()
    if user and check_password_hash(user[2], d['password']):
        return jsonify({"status": "ok", "user": {"nick": user[0], "avatar": user[3], "is_admin": user[4]}})
    return jsonify({"status": "error"})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

