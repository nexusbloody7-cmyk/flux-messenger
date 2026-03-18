import eventlet
eventlet.monkey_patch()
import sqlite3, os, uuid
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, password TEXT, avatar TEXT, is_verified INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_verified INTEGER)')
    
    # Твой аккаунт (bloody) с синей галочкой
    pw = generate_password_hash('Zavoz7152')
    cur.execute("INSERT OR REPLACE INTO users VALUES ('bloody', ?, 'https://img.icons8.com/fluency/96/user-male-circle.png', 1)", (pw,))
    
    if not cur.execute("SELECT * FROM chats WHERE id='community'").fetchone():
        cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
    if user and check_password_hash(user['password'], d['password']):
        return jsonify({"status": "ok", "user": dict(user)})
    return jsonify({"status": "error"})

@socketio.on('search_user')
def search_user(data):
    conn = get_db()
    target = conn.execute('SELECT nick FROM users WHERE nick = ?', (data['nick'],)).fetchone()
    if target:
        pair = sorted([data['my_nick'], target['nick']])
        chat_id = f"dm_{pair[0]}_{pair[1]}"
        emit('user_found', {'chat_id': chat_id, 'name': target['nick']})
    else:
        emit('error', 'Пользователь не найден')

@socketio.on('create_channel')
def create_channel(data):
    c_id = str(uuid.uuid4())[:8]
    conn = get_db()
    conn.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', (c_id, data['name'], 'public', data['owner']))
    conn.commit()
    emit('new_chat_available', {'id': c_id, 'name': data['name']}, broadcast=True)

@socketio.on('send_msg')
def handle_msg(data):
    conn = get_db()
    user = conn.execute('SELECT is_verified FROM users WHERE nick = ?', (data['sender'],)).fetchone()
    is_v = user['is_verified'] if user else 0
    t = datetime.now().strftime('%H:%M')
    conn.execute('INSERT INTO messages VALUES (?, ?, ?, ?, ?)', (data['chat_id'], data['sender'], data['text'], t, is_v))
    conn.commit()
    emit('broadcast_msg', {'chat_id': data['chat_id'], 'sender': data['sender'], 'text': data['text'], 'time': t, 'is_v': is_v}, room=data['chat_id'])

@socketio.on('join')
def join(data):
    join_room(data['chat_id'])
    conn = get_db()
    msgs = conn.execute('SELECT * FROM messages WHERE chat_id = ? ORDER BY rowid ASC', (data['chat_id'],)).fetchall()
    emit('history', [dict(m) for m in msgs])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

