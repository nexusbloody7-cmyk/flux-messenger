import sqlite3, os
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'flux_ultra_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db_path = 'flux.db'
    if os.path.exists(db_path): os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, is_admin INTEGER)')
    cur.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, owner TEXT)')
    cur.execute('CREATE TABLE messages (chat_id INTEGER, sender TEXT, text TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Твой аккаунт
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, 1)", (generate_password_hash('Zavoz7152'),))
    # Общий чат
    cur.execute("INSERT INTO chats (name, type, owner) VALUES ('Flux Community', 'public', 'system')")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    conn = get_db()
    if d.get('action') == 'login':
        user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
        if user and check_password_hash(user['password'], d['password']):
            return jsonify({"status": "ok", "user": dict(user)})
    return jsonify({"status": "error"})

# Поиск пользователей
@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    conn = get_db()
    users = conn.execute("SELECT nick, is_admin FROM users WHERE nick LIKE ?", (f'%{query}%',)).fetchall()
    return jsonify([dict(u) for u in users])

# Создание чата
@app.route('/api/create_chat', methods=['POST'])
def create_chat():
    d = request.json
    conn = get_db()
    conn.execute("INSERT INTO chats (name, type, owner) VALUES (?, ?, ?)", (d['name'], d['type'], d['owner']))
    conn.commit()
    return jsonify({"status": "ok"})

# Список чатов
@app.route('/api/chats')
def get_chats():
    conn = get_db()
    chats = conn.execute("SELECT * FROM chats").fetchall()
    return jsonify([dict(c) for c in chats])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

