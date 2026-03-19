import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_v11_private_power'

def get_db():
    conn = sqlite3.connect('flux_v8_final.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Убеждаемся, что все колонки на месте
    cur.execute("CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT, avatar TEXT, bio TEXT, is_v INTEGER, is_banned INTEGER DEFAULT 0)")
    # В chats добавляем participants для групп тоже
    cur.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER, avatar TEXT)")
    
    # Твой аккаунт (броня)
    cur.execute("INSERT OR IGNORE INTO users (nick, username, email, password, avatar, bio, is_v, is_banned) VALUES ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 'https://img.icons8.com/fluency/96/user-male-circle.png', 'Основатель Flux Messenger.', 1, 0)")
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
        if d['nick'].lower() == 'bloody': return jsonify({"status": "error", "msg": "Ник зарезервирован!"})
        check = conn.execute("SELECT nick FROM users WHERE nick=? OR email=?", (d['nick'], d['email'])).fetchone()
        if check: return jsonify({"status": "error", "msg": "Ник или Email заняты!"})
        ava = d.get('avatar') or "https://img.icons8.com/glassmorphism/96/user.png"
        uname = "@" + d['nick'].lower().replace(" ", "")
        conn.execute("INSERT INTO users (nick, username, email, password, avatar, bio, is_v, is_banned) VALUES (?, ?, ?, ?, ?, ?, 0, 0)", (d['nick'], uname, d['email'], d['password'], ava, 'Новый пользователь'))
        conn.commit()
        return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": ava, "is_v": 0}})
    else:
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        if u and u['is_banned']: return jsonify({"status": "error", "msg": "Вы забанены!"})
        return jsonify({"status": "ok", "user": dict(u)}) if u else jsonify({"status": "error", "msg": "Ошибка входа"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        sender = d.get('sender')
        text = d.get('text', '').strip()
        chat_id = d.get('chat_id')
        
        u = conn.execute("SELECT is_banned, is_v, avatar FROM users WHERE nick=?", (sender,)).fetchone()
        if u and u['is_banned']: return jsonify({"status": "error"})

        # ПРОВЕРКА КОМАНД (Только создатель чата или bloody могут это делать)
        chat_info = conn.execute("SELECT owner, participants FROM chats WHERE id=?", (chat_id,)).fetchone()
        
        if text.startswith('/') and (sender == 'bloody' or sender == chat_info['owner']):
            # Команда ИНВАЙТ: /invite @nick
            if text.startswith('/invite '):
                target = text.replace('/invite @', '').replace('/invite ', '').strip()
                # Добавляем в список участников (через запятую)
                new_parts = f"{chat_info['participants'] or sender},{target}"
                conn.execute("UPDATE chats SET participants=? WHERE id=?", (new_parts, chat_id))
                conn.commit()
                text = f"📢 {target} добавлен в группу."
            
            # Команды БАНА и ОЧИСТКИ (только для тебя @bloody)
            elif sender == 'bloody' and text.startswith('/ban '):
                t = text.replace('/ban @', '').strip()
                conn.execute("UPDATE users SET is_banned=1 WHERE nick=?", (t,))
                conn.commit()
                text = f"🚫 {t} забанен."
            elif sender == 'bloody' and text == '/clear':
                conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
                conn.commit()
                text = "🧹 Чат очищен."

        if text:
            conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                         (chat_id, sender, text, datetime.now().strftime('%H:%M'), u['is_v'], u['avatar']))
            conn.commit()
        return jsonify({"status": "ok"})
    
    msgs = [dict(m) for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id ASC", (request.args.get('chat_id'),)).fetchall()]
    return jsonify(msgs)

@app.route('/api/chats', methods=['GET', 'POST'])
def handle_chats():
    conn = get_db()
    user_nick = request.args.get('user_nick', '')
    if request.method == 'POST':
        d = request.json
        c_id = "chat_" + str(uuid.uuid4())[:8]
        # Если создаем личку или приватную группу
        is_private = d.get('type') == 'private' or d.get('type') == 'direct'
        
        if d.get('type') == 'direct':
            target = d['target'].replace('@', '').strip()
            p_str = ','.join(sorted([d['owner'], target]))
            ex = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if ex: return jsonify({"status": "ok", "id": ex['id']})
            conn.execute("INSERT INTO chats VALUES (?, 'Личка', 'direct', ?, ?)", (c_id, d['owner'], p_str))
        else:
            # Для групп owner автоматически становится первым участником
            t = 'private' if d.get('type') == 'private' else 'public'
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (c_id, d['name'], t, d['owner'], d['owner']))
            
        conn.commit()
        return jsonify({"status": "ok", "id": c_id})

    # ФИЛЬТРАЦИЯ: Показываем только публичные чаты ИЛИ те, где юзер в списке участников
    all_c = [dict(c) for c in conn.execute("SELECT * FROM chats").fetchall()]
    res = []
    for c in all_c:
        is_member = user_nick and c['participants'] and user_nick in c['participants'].split(',')
        if c['type'] == 'public' or is_member or c['owner'] == user_nick:
            if c['type'] == 'direct':
                p = c['participants'].split(',')
                other = p[1] if p[0] == user_nick else p[0]
                u_info = conn.execute("SELECT avatar FROM users WHERE nick=?", (other,)).fetchone()
                c['name'] = other
                c['avatar'] = u_info['avatar'] if u_info else ''
            res.append(c)
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

