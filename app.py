import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_stable_v1'
# Мы убрали async_mode='eventlet', теперь всё будет работать стандартно
socketio = SocketIO(app, cors_allowed_origins="*")

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
    
    pw_hash = generate_password_hash('Zavoz7152')
    cur.execute("INSERT OR REPLACE INTO users VALUES ('bloody', ?, 'https://img.icons8.com/fluency/96/user-male-circle.png', 1)", (pw_hash,))
    
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
    nick = d.get('nick', '').lower().strip()
    pw = d.get('password', '')
    if nick == 'bloody' and pw == 'Zavoz7152':
        return jsonify({"status": "ok", "user": {"nick": "bloody", "is_verified": 1}})
    return jsonify({"status": "error"})

@socketio.on('join')
def on_join(data):
    join_room(data['chat_id'])
    conn = get_db()
    msgs = conn.execute('SELECT * FROM messages WHERE chat_id = ? ORDER BY rowid ASC', (data['chat_id'],)).fetchall()
    emit('history', [dict(m) for m in msgs])

@socketio.on('send_msg')
def handle_msg(data):
    t = datetime.now().strftime('%H:%M')
    is_v = 1 if data['sender'] == 'bloody' else 0
    conn = get_db()
    conn.execute('INSERT INTO messages VALUES (?, ?, ?, ?, ?)', (data['chat_id'], data['sender'], data['text'], t, is_v))
    conn.commit()
    emit('broadcast_msg', {'chat_id': data['chat_id'], 'sender': data['sender'], 'text': data['text'], 'time': t, 'is_v': is_v}, room=data['chat_id'])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    # Запуск в стандартном режиме
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

