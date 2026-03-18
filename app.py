import sqlite3, os, json, uuid
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'flux_ultra_secret_mobile_2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# Убедимся, что папка для статики существует (для аватарок, если надо)
os.makedirs('static/uploads', exist_ok=True)

# --- Инициализация чистой БД с новой структурой ---
def init_db():
    db_path = 'flux.db'
    if os.path.exists(db_path): os.remove(db_path) # ПОЛНЫЙ СБРОС СТАРОЙ БАЗЫ
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Таблица пользователей (с почтой, аватаром и админкой)
    cur.execute('''CREATE TABLE users (
                    nick TEXT PRIMARY KEY, 
                    email TEXT UNIQUE, 
                    password TEXT, 
                    avatar TEXT, 
                    is_admin INTEGER)''')
    
    # Таблица чатов (Community, каналы, лички)
    cur.execute('''CREATE TABLE chats (
                    id TEXT PRIMARY KEY, 
                    name TEXT, 
                    type TEXT, 
                    owner TEXT)''')
    
    # Таблица сообщений (с поддержкой реакций в JSON)
    cur.execute('''CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    chat_id TEXT, 
                    sender TEXT, 
                    sender_av TEXT, 
                    text TEXT, 
                    time TIMESTAMP, 
                    reactions TEXT DEFAULT "{}")''')
    
    # 1. Создаем твой аккаунт Основателя (bloody)
    # Почта: nexusbloody7@gmail.com | Пароль: Zavoz7152
    pw = generate_password_hash('Zavoz7152')
    founder_av = "https://img.icons8.com/neon/96/user-male-circle.png" # Уникальный авар для bloody
    cur.execute("INSERT INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', ?, ?, 1)", (pw, founder_av))
    
    # 2. Создаем общий чат Flux Community
    cur.execute("INSERT INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    
    conn.commit()
    conn.close()

# Запускаем инициализацию при старте
init_db()

def get_db():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

# --- HTTP API для Аутентификации ---
@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    action = d.get('action')
    conn = get_db()
    
    if action == 'register':
        try:
            pw = generate_password_hash(d['password'])
            # Дефолтный аватар на основе ника через DiceBear
            av = f"https://api.dicebear.com/8.x/shapes/svg?seed={d['nick']}"
            conn.execute('INSERT INTO users VALUES (?, ?, ?, ?, 0)', (d['nick'], d['email'], pw, av))
            conn.commit()
            return jsonify({"status": "ok", "message": "Premium аккаунт создан!"})
        except sqlite3.IntegrityError:
            return jsonify({"status": "error", "message": "Ник или Email занят"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
        finally:
            conn.close()
            
    elif action == 'login':
        user = conn.execute('SELECT * FROM users WHERE nick = ?', (d['nick'],)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], d['password']):
            return jsonify({"status": "ok", "user": dict(user)})
        return jsonify({"status": "error", "message": "Неверные данные или пароль"})

# --- Socket.IO логика реального времени ---
@socketio.on('join_chat')
def on_join(data):
    chat_id = data['chat_id']
    join_room(chat_id)
    # Загрузка истории сообщений
    conn = get_db()
    msgs = conn.execute('SELECT * FROM messages WHERE chat_id = ? ORDER BY time ASC', (chat_id,)).fetchall()
    conn.close()
    emit('load_msgs', [dict(m) for m in msgs])

@socketio.on('new_msg')
def handle_msg(data):
    time_now = datetime.now().strftime('%H:%M')
    conn = get_db()
    
    # Сохраняем сообщение
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO messages (chat_id, sender, sender_av, text, time) 
                      VALUES (?, ?, ?, ?, ?)''',
                   (data['chat_id'], data['sender'], data['sender_av'], data['text'], time_now))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    
    # Рассылаем всем в комнате
    emit('msg_broadcast', {
        'id': msg_id,
        'chat_id': data['chat_id'],
        'sender': data['sender'],
        'sender_av': data['sender_av'],
        'text': data['text'],
        'time': time_now,
        'reactions': "{}" # Изначально пустые реакции
    }, room=data['chat_id'])

@socketio.on('add_reaction')
def handle_reaction(data):
    msg_id = data['msg_id']
    user = data['user']
    emoji = data['emoji']
    chat_id = data['chat_id']
    
    conn = get_db()
    msg = conn.execute('SELECT reactions FROM messages WHERE id = ?', (msg_id,)).fetchone()
    
    if msg:
        reactions = json.loads(msg['reactions'])
        # Логика: если юзер уже поставил этот эмодзи — убираем, если нет — добавляем
        if emoji not in reactions: reactions[emoji] = []
        
        if user in reactions[emoji]:
            reactions[emoji].remove(user)
            if not reactions[emoji]: del reactions[emoji] # Убираем эмодзи, если нет юзеров
        else:
            reactions[emoji].append(user)
            
        new_reactions_json = json.dumps(reactions)
        conn.execute('UPDATE messages SET reactions = ? WHERE id = ?', (new_reactions_json, msg_id))
        conn.commit()
        
        # Оповещаем всех об обновлении реакций
        emit('update_reactions', {'msg_id': msg_id, 'reactions': new_reactions_json}, room=chat_id)
    conn.close()

if __name__ == '__main__':
    # Слушаем на порту 8000 (стандарт для Render)
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))

