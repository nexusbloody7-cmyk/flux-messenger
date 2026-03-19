import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_ocean_pro_v3'

def get_db():
    conn = sqlite3.connect('flux_v3.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Пользователи: теперь с юзернеймом и био
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
        (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, 
         password TEXT, avatar TEXT, bio TEXT, is_v INTEGER)''')
    
    # Чаты: общедоступные и приватные
    cur.execute('''CREATE TABLE IF NOT EXISTS chats 
        (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT)''')
    
    # Сообщения
    cur.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, 
         text TEXT, time TEXT, is_v INTEGER, avatar TEXT)''')
    
    # Твой эталонный аккаунт
    cur.execute("""INSERT OR IGNORE INTO users VALUES 
        ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 
         'https://img.icons8.com/fluency/96/user-male-circle.png', 
         'Основатель Flux. Создаю будущее.', 1)""")
    
    # Общий чат
    cur.execute("INSERT OR IGNORE INTO chats VALUES ('community', 'Flux Community', 'public', 'system')")
    
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
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", 
                (d['nick'], uname, d['email'], d['password'], d['avatar'], 'Новый пользователь Flux', 0))
            conn.commit()
            return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": d['avatar'], "is_v": 0}})
        except: return jsonify({"status": "error", "msg": "Ник или почта уже заняты"})
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
def messages():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        u = conn.execute("SELECT avatar, is_v FROM users WHERE nick=?", (d['sender'],)).fetchone()
        t = datetime.now().strftime('%H:%M')
        conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                     (d['chat_id'], d['sender'], d['text'], t, u['is_v'], u['avatar']))
        conn.commit()
        return jsonify({"status": "ok"})
    
    c_id = request.args.get('chat_id', 'community')
    msgs = [dict(m) for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id ASC", (c_id,)).fetchall()]
    return jsonify(msgs)

@app.route('/api/chats', methods=['GET', 'POST'])
def chats():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        cid = str(uuid.uuid4())[:8]
        conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?)", (cid, d['name'], d['type'], d['owner']))
        conn.commit()
        return jsonify({"status": "ok", "id": cid})
    return jsonify([dict(c) for c in conn.execute("SELECT * FROM chats").fetchall()])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

