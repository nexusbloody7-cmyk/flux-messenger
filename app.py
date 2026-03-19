import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_ultra_fix_v6'

def get_db():
    # Используем то же имя БД, что и в V6
    conn = sqlite3.connect('flux_glass_v6.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # 1. Таблица пользователей
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
        (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, 
         password TEXT, avatar TEXT, bio TEXT, is_v INTEGER)''')
    
    # 2. Таблица чатов
    cur.execute('''CREATE TABLE IF NOT EXISTS chats 
        (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)''')
    
    # 3. Таблица сообщений (с полной структурой)
    cur.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, 
         text TEXT, time TEXT, is_v INTEGER, avatar TEXT)''')
    
    # МАГИЯ: Проверка и добавление недостающих колонок (если база уже была создана криво)
    try:
        cur.execute("SELECT is_v FROM messages LIMIT 1")
    except sqlite3.OperationalError:
        cur.execute("ALTER TABLE messages ADD COLUMN is_v INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE messages ADD COLUMN avatar TEXT")
        print("База данных успешно обновлена (добавлены колонки)")

    # Твой вечный аккаунт @bloody
    cur.execute("""INSERT OR IGNORE INTO users VALUES 
        ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 
         'https://img.icons8.com/fluency/96/user-male-circle.png', 
         'Основатель Flux Messenger.', 1)""")
    
    # Дефолтный чат
    cur.execute("INSERT OR IGNORE INTO chats VALUES ('community', 'Flux Community', 'public', 'system', NULL)")
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    conn = get_db()
    if d.get('action') == 'register':
        try:
            uname = "@" + d['nick'].lower().replace(" ", "")
            is_v = 1 if d['nick'].lower() == 'bloody' else 0
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", 
                (d['nick'], uname, d['email'], d['password'], d['avatar'], 'Новый пользователь Flux', is_v))
            conn.commit()
            u = {"nick": d['nick'], "username": uname, "avatar": d['avatar'], "is_v": is_v, "bio": 'Новый пользователь Flux'}
            return jsonify({"status": "ok", "user": u})
        except: return jsonify({"status": "error", "msg": "Ник или Email занят"})
    else:
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        return jsonify({"status": "ok", "user": dict(u)}) if u else jsonify({"status": "error", "msg": "Ошибка входа"})

@app.route('/api/profile', methods=['POST'])
def update_profile():
    d = request.json
    conn = get_db()
    conn.execute("UPDATE users SET bio=?, avatar=? WHERE nick=?", (d['bio'], d['avatar'], d['nick']))
    conn.commit()
    return jsonify({"status": "ok"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    conn = get_db()
    if request.method == 'POST':
        try:
            d = request.json
            # Важный фикс: если отправителя нет в базе (глюк), ставим заглушку
            u = conn.execute("SELECT avatar, is_v FROM users WHERE nick=?", (d['sender'],)).fetchone()
            ava = u['avatar'] if u else 'https://img.icons8.com/glassmorphism/96/user.png'
            is_v = u['is_v'] if u else 0
            t = datetime.now().strftime('%H:%M')
            
            conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['chat_id'], d['sender'], d['text'], t, is_v, ava))
            conn.commit()
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "msg": str(e)})
    
    c_id = request.args.get('chat_id', 'community')
    msgs = [dict(m) for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id ASC", (c_id,)).fetchall()]
    conn.close()
    return jsonify(msgs)

@app.route('/api/chats', methods=['GET', 'POST'])
def handle_chats():
    conn = get_db()
    user_nick = request.args.get('user_nick', '')
    
    if request.method == 'POST':
        d = request.json
        if d['type'] == 'direct':
            participants = sorted([d['owner'], d['target'].replace('@', '')])
            p_str = ','.join(participants)
            existing = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if existing: return jsonify({"status": "ok", "id": existing['id']})
            
            chat_id = "dm_" + str(uuid.uuid4())[:8]
            target_user = conn.execute("SELECT nick FROM users WHERE username=?", (d['target'],)).fetchone()
            if not target_user: return jsonify({"status": "error", "msg": "Юзер не найден"})
            
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, 'Личный чат', 'direct', d['owner'], p_str))
            conn.commit()
            return jsonify({"status": "ok", "id": chat_id})
        
        chat_id = str(uuid.uuid4())[:8]
        conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, d['name'], 'public', d['owner'], None))
        conn.commit()
        return jsonify({"status": "ok", "id": chat_id})

    # Список чатов
    chats_res = []
    # Общий
    comm = conn.execute("SELECT * FROM chats WHERE id='community'").fetchone()
    if comm: chats_res.append(dict(comm))
    # Лички
    if user_nick:
        my_d = conn.execute("SELECT * FROM chats WHERE type='direct' AND participants LIKE ?", (f'%{user_nick}%',)).fetchall()
        for c in my_d:
            c_d = dict(c)
            p = c_d['participants'].split(',')
            other = p[1] if p[0] == user_nick else p[0]
            u_data = conn.execute("SELECT avatar FROM users WHERE nick=?", (other,)).fetchone()
            c_d['other_user'] = other
            c_d['avatar'] = u_data['avatar'] if u_data else ''
            chats_res.append(c_d)
    # Группы
    pub = conn.execute("SELECT * FROM chats WHERE type='public' AND id != 'community'").fetchall()
    for c in pub: chats_res.append(dict(c))
    
    conn.close()
    return jsonify(chats_res)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

