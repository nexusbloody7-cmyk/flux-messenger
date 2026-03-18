import sqlite3, os, uuid
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_ultra_secret_99'
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOADS = 'static/uploads'
os.makedirs(UPLOADS, exist_ok=True)

# --- Инициализация чистой БД ---
def init_db():
    if os.path.exists('flux.db'): os.remove('flux.db') # Полный сброс!
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    # Юзеры (с email, аватаром и админом)
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    # Чаты (Community, каналы, лички)
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, members TEXT)')
    # Сообщения (с фото)
    cur.execute('CREATE TABLE messages (id TEXT PRIMARY KEY, chat_id TEXT, sender TEXT, text TEXT, file TEXT, time TIMESTAMP)')
    # Реакции
    cur.execute('CREATE TABLE reactions (msg_id TEXT, user TEXT, emoji TEXT)')
    
    # 1. Создаем Flux Community
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system', '*')")
    # 2. Создаем тебя, Основателя bloody (пароль: admin123, поменяй потом!)
    pw = generate_password_hash('admin123')
    cur.execute("INSERT INTO users VALUES ('bloody', 'founder@flux.chat', ?, 'bloody_av.png', 1)", (pw,))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index(): return render_template('index.html')

# --- Логика Входа и Регистрации ---
@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    action = d.get('action')
    conn = get_db()
    
    if action == 'register':
        try:
            pw = generate_password_hash(d['password'])
            conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, 'default.png'))
            conn.commit()
            return jsonify({"status": "ok", "message": "Аккаунт создан!"})
        except: return jsonify({"status": "error", "message": "Ник или Email занят"})
        
    elif action == 'login':
        user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
        if user and check_password_hash(user['password'], d['password']):
            return jsonify({"status": "ok", "nick": user['nick'], "avatar": user['avatar'], "is_admin": user['is_admin']})
        return jsonify({"status": "error", "message": "Неверные данные"})
    conn.close()

# --- Поиск юзеров (внутри интерфейса) ---
@socketio.on('search_users')
def handle_search(data):
    conn = get_db()
    users = conn.execute('SELECT nick, avatar, is_admin FROM users WHERE nick LIKE ?', (f"%{data['query']}%",)).fetchall()
    emit('search_results', [dict(u) for u in users])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

