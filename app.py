import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_v8_power'

def get_db():
    # Новое имя БД для чистого запуска
    conn = sqlite3.connect('flux_v8_final.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Таблицы
    cur.execute("CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT, avatar TEXT, bio TEXT, is_v INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER, avatar TEXT)")

    # Твой аккаунт
    cur.execute("INSERT OR IGNORE INTO users VALUES ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 'https://img.icons8.com/fluency/96/user-male-circle.png', 'Основатель Flux Messenger.', 1)")
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
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", (d['nick'], uname, d['email'], d['password'], d['avatar'], 'Новый пользователь', is_v))
            conn.commit()
            return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": d['avatar'], "is_v": is_v}})
        except: return jsonify({"status": "error", "msg": "Ошибка регистрации"})
    else:
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        return jsonify({"status": "ok", "user": dict(u)}) if u else jsonify({"status": "error", "msg": "Вход не удался"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    conn = get_db()
    if request.method == 'POST':
        try:
            d = request.json
            sender_nick = d.get('sender')
            u = conn.execute("SELECT avatar, is_v FROM users WHERE nick=?", (sender_nick,)).fetchone()
            
            # Если юзера нет в базе (глюк), берем дефолт
            ava = u['avatar'] if u else 'https://img.icons8.com/glassmorphism/96/user.png'
            is_v = u['is_v'] if u else 0
            
            conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                         (d.get('chat_id'), sender_nick, d.get('text'), datetime.now().strftime('%H:%M'), is_v, ava))
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
        chat_id = str(uuid.uuid4())[:8]
        if d.get('type') == 'direct':
            parts = sorted([d['owner'], d['target'].replace('@', '')])
            p_str = ','.join(parts)
            ex = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if ex: return jsonify({"status": "ok", "id": ex['id']})
            conn.execute("INSERT INTO chats VALUES (?, 'Личка', 'direct', d['owner'], ?)", (chat_id, p_str))
        else:
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, NULL)", (chat_id, d['name'], 'public', d['owner']))
        conn.commit()
        return jsonify({"status": "ok", "id": chat_id})

    all_chats = [dict(c) for c in conn.execute("SELECT * FROM chats").fetchall()]
    res = []
    for c in all_chats:
        if c['type'] == 'direct':
            if user_nick and user_nick in (c['participants'] or ''):
                p = c['participants'].split(',')
                other = p[1] if p[0] == user_nick else p[0]
                u_info = conn.execute("SELECT avatar FROM users WHERE nick=?", (other,)).fetchone()
                c['other_user'] = other
                c['avatar'] = u_info['avatar'] if u_info else ''
                res.append(c)
        else: res.append(c)
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

