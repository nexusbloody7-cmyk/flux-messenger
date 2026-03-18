import sqlite3, os, uuid, json
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_mobile_ultra_key_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Инициализация чистой БД ---
def init_db():
    if os.path.exists('flux.db'): os.remove('flux.db') # Полный сброс!
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    # Юзеры (с email, аватаром и админом)
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    # Чаты (Community, лички)
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)')
    # Сообщения + Реакции (reactions как JSON строка)
    cur.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, sender_av TEXT, text TEXT, time TIMESTAMP, reactions TEXT DEFAULT "{}")')
    
    # 1. Создаем Flux Community
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    # 2. Создаем ТВОЙ аккаунт: nexusbloody7@gmail.com | bloody | Zavoz7152 (Основатель ✔)
    pw = generate_password_hash('Zavoz7152')
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, 'founder_av.png', 1)", (pw,))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index(): return render_template('index.html')

# --- Логика Аутентификации ---
@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    action = d.get('action')
    conn = get_db()
    
    if action == 'register':
        try:
            pw = generate_password_hash(d['password'])
            # Дефолтный аватар на основе ника
            av = f"https://api.dicebear.com/8.x/shapes/svg?seed={d['nick']}"
            conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, av, 0))
            conn.commit()
            return jsonify({"status": "ok", "message": "Аккаунт создан!"})
        except: return jsonify({"status": "error", "message": "Ник или Email занят"})
        
    elif action == 'login':
        user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
        if user and check_password_hash(user['password'], d['password']):
            return jsonify({"status": "ok", "user": dict(user)})
        return jsonify({"status": "error", "message": "Неверные данные"})
    conn.close()

# --- Логика Чат-Системы (Socket.IO) ---
@socketio.on('join_chat')
def on_join(data):
    join_room(data['chat_id'])
    # Загрузка истории сообщений
    conn = get_db()
    msgs = conn.execute('SELECT * FROM messages WHERE chat_id = ? ORDER BY time ASC', (data['chat_id'],)).fetchall()
    conn.close()
    emit('load_msgs', [dict(m) for m in msgs])

@socketio.on('new_msg')
def handle_msg(data):
    time_now = datetime.now().strftime('%H:%M')
    conn = get_db()
    conn.execute('INSERT INTO messages (chat_id, sender, sender_av, text, time) VALUES (?, ?, ?, ?, ?)',
                 (data['chat_id'], data['sender'], data['sender_av'], data['text'], time_now))
    conn.commit()
    # Получаем id только что вставленного сообщения
    msg_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    
    emit('msg_broadcast', {
        'id': msg_id,
        'chat_id': data['chat_id'],
        'sender': data['sender'],
        'sender_av': data['sender_av'],
        'text': data['text'],
        'time': time_now,
        'is_admin': data['is_admin'], # Пробрасываем статус админа
        'reactions': "{}"
    }, room=data['chat_id'])

# --- Поиск юзеров ---
@socketio.on('search_users')
def handle_search(data):
    conn = get_db()
    users = conn.execute('SELECT nick, avatar, is_admin FROM users WHERE nick LIKE ?', (f"%{data['query']}%",)).fetchall()
    emit('search_results', [dict(u) for u in users])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

