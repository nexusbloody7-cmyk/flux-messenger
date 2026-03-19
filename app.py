import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_final_fix_v7'

def get_db():
    # Используем новое имя БД, чтобы точно избежать конфликтов старых таблиц
    conn = sqlite3.connect('flux_v7_final.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Пользователи
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
        (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, 
         password TEXT, avatar TEXT, bio TEXT, is_v INTEGER)''')
    # Чаты
    cur.execute('''CREATE TABLE IF NOT EXISTS chats 
        (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)''')
    # Сообщения
    cur.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, 
         text TEXT, time TEXT, is_v INTEGER, avatar TEXT)''')

    # Твой бронированный аккаунт
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
                (d['nick'], uname, d['email'], d['password'], d['avatar'], 'Новый пользователь', is_v))
            conn.commit()
            return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": d['avatar'], "is_v": is_v}})
        except: return jsonify({"status": "error", "msg": "Ошибка: ник или почта заняты"})
    else:
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        return jsonify({"status": "ok", "user": dict(u)}) if u else jsonify({"status": "error", "msg": "Неверный вход"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    conn = get_db()
    if request.method == 'POST':
        try:
            d = request.json
            # ГАРАНТИРОВАННОЕ ПОЛУЧЕНИЕ ДАННЫХ ОТПРАВИТЕЛЯ
            u = conn.execute("SELECT avatar, is_v FROM users WHERE nick=?", (d.get('sender'),)).fetchone()
            
            # Подстраховка на случай пустых данных
            ava = u['avatar'] if u else 'https://img.icons8.com/glassmorphism/96/user.png'
            is_v = u['is_v'] if u else 0
            chat_id = d.get('chat_id', 'community')
            text = d.get('text', '')
            sender = d.get('sender', 'Unknown')
            t = datetime.now().strftime('%H:%M')

            if text.strip(): # Если текст не пустой
                conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                             (chat_id, sender, text, t, is_v, ava))
                conn.commit()
                return jsonify({"status": "ok"})
            return jsonify({"status": "error", "msg": "Пустое сообщение"})
        except Exception as e:
            print(f"DEBUG ERROR: {e}")
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
        chat_id = str(uuid.uuid4())[:8]
        if d.get('type') == 'direct':
            participants = sorted([d['owner'], d['target'].replace('@', '')])
            p_str = ','.join(participants)
            existing = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if existing: return jsonify({"status": "ok", "id": existing['id']})
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, 'Личка', 'direct', d['owner'], p_str))
        else:
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, d['name'], 'public', d['owner'], None))
        conn.commit()
        return jsonify({"status": "ok", "id": chat_id})

    chats = [dict(c) for c in conn.execute("SELECT * FROM chats").fetchall()]
    # Если это личка, подменяем имя для отображения
    res = []
    for c in chats:
        if c['type'] == 'direct':
            if user_nick and user_nick in c['participants']:
                p = c['participants'].split(',')
                other = p[1] if p[0] == user_nick else p[0]
                c['other_user'] = other
                res.append(c)
        else:
            res.append(c)
    conn.close()
    return jsonify(res)

@app.route('/api/profile', methods=['POST'])
def update_profile():
    d = request.json
    conn = get_db()
    conn.execute("UPDATE users SET bio=?, avatar=? WHERE nick=?", (d['bio'], d['avatar'], d['nick']))
    conn.commit()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

