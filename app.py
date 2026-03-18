import sqlite3, os
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

# Указываем папку с шаблонами явно
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists('uploads'): os.makedirs('uploads')

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_db():
    conn, cur = get_db()
    cur.execute('CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, sender TEXT, text TEXT, avatar TEXT)')
    # Создаем официальное сообщество по умолчанию
    cur.execute("INSERT OR IGNORE INTO chats VALUES ('community', 'Flux Community', 'channel', 'system')")
    conn.commit()
    conn.close()

init_db()

@app.after_request
def add_header(response):
    response.headers['ngrok-skip-browser-warning'] = 'true'
    response.headers['Bypass-Tunnel-Reminder'] = 'true'
    return response

# ИСПРАВЛЕННЫЙ РОУТ
@app.route('/')
def index():
    # Используем render_template вместо open().read()
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def reg():
    d = request.json
    try:
        conn, cur = get_db()
        pw = generate_password_hash(d['password'])
        cur.execute('INSERT INTO users VALUES (?, ?, ?, ?)', (d['nick'], d['email'], pw, 'default.png'))
        conn.commit()
        return jsonify({"status": "ok"})
    except: return jsonify({"status": "error"})
    finally: conn.close()

@app.route('/login', methods=['POST'])
def login():
    d = request.json
    conn, cur = get_db()
    cur.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],))
    user = cur.fetchone()
    conn.close()
    if user and check_password_hash(user['password'], d['password']):
        return jsonify({"status": "ok", "nick": user['nick'], "avatar": user['avatar']})
    return jsonify({"status": "error"})

@app.route('/search')
def search():
    q = request.args.get('q')
    me = request.args.get('me')
    conn, cur = get_db()
    cur.execute('SELECT nick, avatar FROM users WHERE nick LIKE ? AND nick != ? LIMIT 10', (f'%{q}%', me))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/get_chats', methods=['GET'])
def get_chats():
    conn, cur = get_db()
    cur.execute('SELECT * FROM chats')
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    nick = request.form['nick']
    fname = f"av_{nick}.png"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
    conn, cur = get_db()
    cur.execute('UPDATE users SET avatar = ? WHERE nick = ?', (fname, nick))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "url": fname})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@socketio.on('msg')
def handle_msg(data):
    conn, cur = get_db()
    cur.execute('INSERT INTO messages VALUES (?,?,?,?)', (data['chat_id'], data['nick'], data['text'], data['avatar']))
    conn.commit()
    conn.close()
    emit('new_msg', data, room=data['chat_id'])

@socketio.on('create_room')
def create_room(data):
    conn, cur = get_db()
    room_id = f"{data['type']}_{os.urandom(3).hex()}"
    cur.execute('INSERT INTO chats VALUES (?,?,?,?)', (room_id, data['name'], data['type'], data['owner']))
    conn.commit()
    conn.close()
    emit('room_created', {'id': room_id, 'name': data['name'], 'type': data['type']}, broadcast=True)

if __name__ == '__main__':
    # Для Render важен порт из переменной окружения, но gunicorn его переопределит
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

