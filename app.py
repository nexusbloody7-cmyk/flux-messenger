import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room

# Инициализация без лишних наворотов
app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_final_safety'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

def init_db():
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, password TEXT, is_verified INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER)')
    cur.execute("INSERT OR REPLACE INTO users VALUES ('bloody', 'Zavoz7152', 1)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    n, p = d.get('nick', '').lower().strip(), d.get('password', '')
    if n == 'bloody' and p == 'Zavoz7152':
        return jsonify({"status": "ok", "user": {"nick": "bloody", "is_verified": 1}})
    return jsonify({"status": "error"})

@socketio.on('join')
def on_join(data):
    join_room(data['chat_id'])
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    msgs = [dict(m) for m in conn.execute('SELECT * FROM messages WHERE chat_id = ?', (data['chat_id'],)).fetchall()]
    conn.close()
    emit('history', msgs)

@socketio.on('send_msg')
def handle_msg(data):
    t, is_v = datetime.now().strftime('%H:%M'), (1 if data['sender'] == 'bloody' else 0)
    conn = sqlite3.connect('flux.db')
    conn.execute('INSERT INTO messages VALUES (?, ?, ?, ?, ?)', (data['chat_id'], data['sender'], data['text'], t, is_v))
    conn.commit()
    conn.close()
    emit('broadcast_msg', {'chat_id': data['chat_id'], 'sender': data['sender'], 'text': data['text'], 'time': t, 'is_v': is_v}, room=data['chat_id'])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)

