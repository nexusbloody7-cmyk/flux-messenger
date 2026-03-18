import eventlet
eventlet.monkey_patch() # ГЛАВНЫЙ ФИКС ДЛЯ RENDER

import sqlite3, os, json, uuid
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_ultra_premium_2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- Настройки загрузки файлов ---
# На Render используем /tmp для временного хранения, т.к. статика стирается при деплое
UPLOAD_FOLDER = '/tmp/flux_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Маршрут для раздачи загруженных аватарок ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Инициализация чистой БД ---
def init_db():
    db_path = 'flux.db'
    if os.path.exists(db_path): os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Юзеры (с email, аватаром и админом)
    cur.execute('CREATE TABLE users (nick TEXT PRIMARY KEY, email TEXT, password TEXT, avatar TEXT, is_admin INTEGER)')
    # Чаты (id, name, type: public/private, members: JSON список ников для ЛС)
    cur.execute('CREATE TABLE chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, members TEXT)')
    # Сообщения
    cur.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, sender_av TEXT, text TEXT, time TIMESTAMP)')
    
    # 1. Твой Premium аккаунт (bloody)
    pw = generate_password_hash('Zavoz7152')
    # Дефолтный авар основателя
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, 'https://img.icons8.com/neon/96/user-male-circle.png', 1)", (pw,))
    # 2. Общий чат
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', '[]')")
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index(): return render_template('index.html')

# --- HTTP API (Auth & Uploads) ---
@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    action = d.get('action')
    conn = get_db()
    
    if action == 'register':
        try:
            pw = generate_password_hash(d['password'])
            # Дефолтный авар
            av = f"https://api.dicebear.com/8.x/shapes/svg?seed={d['nick']}"
            conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, av, 0))
            conn.commit()
            return jsonify({"status": "ok"})
        except: return jsonify({"status": "error", "message": "Ник или Email занят"})
        finally: conn.close()
            
    elif action == 'login':
        user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], d['password']):
            return jsonify({"status": "ok", "user": dict(user)})
        return jsonify({"status": "error", "message": "Неверные данные"})

# Загрузка собственного аватара
@app.route('/api/upload_avatar', methods=['POST'])
def upload_avatar():
    if 'avatar' not in request.files: return jsonify({"status": "error", "message": "Нет файла"})
    file = request.files['avatar']
    nick = request.form.get('nick')
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{nick}_{uuid.uuid4().hex[:8]}.png")
        file.save(os.path.exists(UPLOAD_FOLDER, filename))
        
        # Обновляем в базе
        new_av_url = f"/uploads/{filename}"
        conn = get_db()
        conn.execute('UPDATE users SET avatar = ? WHERE nick = ?', (new_av_url, nick))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "avatar_url": new_av_url})
    return jsonify({"status": "error", "message": "Тип файла не разрешен"})

# Поиск пользователей для ЛС
@app.route('/api/search')
def search():
    q = request.args.get('q', '')
    if len(q) < 2: return jsonify([])
    conn = get_db()
    users = conn.execute('SELECT nick, avatar, is_admin FROM users WHERE nick LIKE ? AND nick != ?', (f'%{q}%', request.args.get('my_nick'))).fetchall()
    return jsonify([dict(u) for u in users])

# --- Socket.IO (Чат ЛС и Community) ---
@socketio.on('join_chat')
def on_join(data):
    chat_id = data['chat_id']
    join_room(chat_id)
    # История
    conn = get_db()
    msgs = conn.execute('SELECT * FROM messages WHERE chat_id = ? ORDER BY time ASC', (chat_id,)).fetchall()
    
    # Если это ЛС и чат новый, создаем его в базе
    if chat_id.startswith('chat_') and chat_id != 'community':
        existing = conn.execute('SELECT id FROM chats WHERE id = ?', (chat_id,)).fetchone()
        if not existing:
            # chat_nick1_nick2 -> получаем ники
            parts = chat_id.split('_')
            members = json.dumps([parts[1], parts[2]])
            conn.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', (chat_id, f"ЛС: {parts[1]} & {parts[2]}", 'private', members))
            conn.commit()
            
    conn.close()
    emit('load_msgs', [dict(m) for m in msgs])

@socketio.on('new_msg')
def handle_msg(data):
    time_now = datetime.now().strftime('%H:%M')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (chat_id, sender, sender_av, text, time) VALUES (?, ?, ?, ?, ?)',
                   (data['chat_id'], data['sender'], data['sender_av'], data['text'], time_now))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    
    emit('msg_broadcast', {
        'id': msg_id, 'chat_id': data['chat_id'], 'sender': data['sender'],
        'sender_av': data['sender_av'], 'text': data['text'], 'time': time_now
    }, room=data['chat_id'])

# Получение списка моих чатов (Community + все ЛС)
@socketio.on('get_my_chats')
def get_chats(data):
    nick = data['nick']
    conn = get_db()
    # Public chats
    public = conn.execute('SELECT * FROM chats WHERE type = "public"').fetchall()
    # Private chats (где я в списке members)
    private = conn.execute('SELECT * FROM chats WHERE type = "private" AND members LIKE ?', (f'%"{nick}"%',)).fetchall()
    conn.close()
    emit('my_chats_list', {'public': [dict(c) for c in public], 'private': [dict(c) for c in private]})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)

