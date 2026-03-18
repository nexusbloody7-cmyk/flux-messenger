import sqlite3, os
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'flux_ultra_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

def init_db():
    # Принудительно сносим старую базу, чтобы применились новые данные bloody
    if os.path.exists('flux.db'): os.remove('flux.db')
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    
    # Таблицы: Юзеры, Чаты, Сообщения
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT)')
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public')")
    
    # СОЗДАЕМ ТВОЙ ГЛАВНЫЙ АККАУНТ
    # Почта: nexusbloody7@gmail.com | Ник: bloody | Пароль: Zavoz7152
    pw = generate_password_hash('Zavoz7152')
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, 'https://i.pravatar.cc/150?u=bloody', 1)", (pw,))
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if d.get('action') == 'register':
        try:
            pw = generate_password_hash(d['password'])
            cur.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, 'default.png'))
            conn.commit()
            return jsonify({"status": "ok"})
        except: return jsonify({"status": "error", "message": "Ник или Email занят"})
    
    # ВХОД
    user = cur.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
    if user and check_password_hash(user['password'], d['password']):
        return jsonify({"status": "ok", "user": {"nick": user['nick'], "is_admin": user['is_admin']}})
    return jsonify({"status": "error", "message": "Неверный логин или пароль"})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

