import sqlite3, os
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_secret_99'
socketio = SocketIO(app, cors_allowed_origins="*")

# Функция сброса и инициализации БД
def init_db():
    if os.path.exists('flux.db'): os.remove('flux.db') # СБРОС БАЗЫ
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    # Таблица юзеров (добавили email)
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    # Таблица чатов (общее сообщество, каналы, лички)
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)')
    # Сообщения
    cur.execute('CREATE TABLE messages (chat_id TEXT, sender TEXT, text TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Создаем Flux Community по умолчанию
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    # Добавляем тебя как основателя с галочкой (is_admin = 1)
    pw = generate_password_hash('admin123') # Поменяй пароль потом!
    cur.execute("INSERT INTO users VALUES ('bloody', 'admin@flux.com', ?, 'default.png', 1)", (pw,))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index(): return render_template('index.html')

@app.route('/register', methods=['POST'])
def reg():
    d = request.json
    conn = get_db()
    try:
        pw = generate_password_hash(d['password'])
        conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, 'default.png'))
        conn.commit()
        return jsonify({"status": "ok"})
    except: return jsonify({"status": "error", "message": "Ник занят"})
    finally: conn.close()

@app.route('/search_user')
def search():
    q = request.args.get('q')
    conn = get_db()
    users = conn.execute('SELECT nick, is_admin FROM users WHERE nick LIKE ?', (f'%{q}%',)).fetchall()
    return jsonify([dict(u) for u in users])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

