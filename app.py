import sqlite3, os
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'flux_fixed_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Инициализация базы
def init_db():
    db_path = 'flux.db'
    if os.path.exists(db_path): os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, is_admin INTEGER)')
    # Твой аккаунт bloody
    from werkzeug.security import generate_password_hash
    pw = generate_password_hash('Zavoz7152')
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, 1)", (pw,))
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    from werkzeug.security import check_password_hash
    d = request.json
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
    if user and check_password_hash(user['password'], d['password']):
        return jsonify({"status": "ok", "user": {"nick": user['nick'], "is_admin": user['is_admin']}})
    return jsonify({"status": "error", "message": "Данные не подошли"})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

