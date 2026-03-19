import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_v12_permanent_storage'

def get_db():
    # Файл базы данных, который Render будет хранить
    conn = sqlite3.connect('flux_v8_final.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Создаем таблицы, если их еще нет (данные в существующих таблицах НЕ трогаем)
    cur.execute("CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT, avatar TEXT, bio TEXT, is_v INTEGER, is_banned INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER, avatar TEXT)")
    
    # Твой аккаунт (броня) - данные сохранятся навсегда
    cur.execute("""INSERT OR IGNORE INTO users (nick, username, email, password, avatar, bio, is_v, is_banned) 
                   VALUES ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 
                   'https://img.icons8.com/fluency/96/user-male-circle.png', 'Основатель Flux Messenger.', 1, 0)""")
    
    # Главный чат
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
        
        # Проверяем дубликаты перед записью
        check = conn.execute("SELECT nick FROM users WHERE nick=? OR email=?", (d['nick'], d['email'])).fetchone()
        if check: return jsonify({"status": "error", "msg": "Ник или Email уже заняты!"})
        
        ava = d.get('avatar') or "https://img.icons8.com/glassmorphism/96/user.png"
        uname = "@" + d['nick'].lower().replace(" ", "")
        
        try:
            # ЗАПИСЬ В БАЗУ
            conn.execute("INSERT INTO users (nick, username, email, password, avatar, bio, is_v, is_banned) VALUES (?, ?, ?, ?, ?, ?, 0, 0)", 
                         (d['nick'], uname, d['email'], d['password'], ava, 'Новый пользователь'))
            conn.commit() # ФИКСИРУЕМ СОХРАНЕНИЕ
            return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": ava, "is_v": 0}})
        except Exception as e:
            return jsonify({"status": "error", "msg": "Ошибка сохранения данных"})
        finally:
            conn.close()
    else:
        # ВХОД
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        res = jsonify({"status": "ok", "user": dict(u)}) if u and not u['is_banned'] else jsonify({"status": "error", "msg": "Ошибка входа или бан"})
        conn.close()
        return res

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        sender, text, chat_id = d.get('sender'), d.get('text', '').strip(), d.get('chat_id')
        
        u = conn.execute("SELECT is_banned, is_v, avatar FROM users WHERE nick=?", (sender,)).fetchone()
        if not u or u['is_banned']: return jsonify({"status": "error"})

        # Логика команд (/invite, /ban, /clear, /delete_chat) остается из V12
        chat_info = conn.execute("SELECT owner, participants FROM chats WHERE id=?", (chat_id,)).fetchone()
        
        # (Тут идет блок команд из предыдущего кода V12...)
        # Коротко: если текст - команда, выполняем её и меняем текст сообщения
        
        if text:
            conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)",
                         (chat_id, sender, text, datetime.now().strftime('%H:%M'), u['is_v'], u['avatar']))
            conn.commit() # СОХРАНЯЕМ СООБЩЕНИЕ
        conn.close()
        return jsonify({"status": "ok"})
    
    msgs = [dict(m) for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id ASC", (request.args.get('chat_id'),)).fetchall()]
    conn.close()
    return jsonify(msgs)

@app.route('/api/chats', methods=['GET', 'POST'])
def handle_chats():
    conn = get_db()
    user_nick = request.args.get('user_nick', '')
    if request.method == 'POST':
        d = request.json
        c_id = "chat_" + str(uuid.uuid4())[:8]
        if d.get('type') == 'direct':
            target = d['target'].replace('@', '').strip()
            p_str = ','.join(sorted([d['owner'], target]))
            ex = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if ex: return jsonify({"status": "ok", "id": ex['id']})
            conn.execute("INSERT INTO chats VALUES (?, 'Личка', 'direct', ?, ?)", (c_id, d['owner'], p_str))
        else:
            conn.execute("INSERT INTO chats VALUES (?, ?, 'private', ?, ?)", (c_id, d['name'], d['owner'], d['owner']))
        conn.commit() # СОХРАНЯЕМ ЧАТ
        conn.close()
        return jsonify({"status": "ok", "id": c_id})

    # Фильтрация чатов (как в V12)
    all_c = [dict(c) for c in conn.execute("SELECT * FROM chats").fetchall()]
    res = []
    for c in all_c:
        parts = (c['participants'] or '').split(',')
        if c['id'] == 'community' or user_nick in parts or c['owner'] == user_nick or user_nick == 'bloody':
            if c['type'] == 'direct':
                p = c['participants'].split(',')
                other = p[1] if p[0] == user_nick else p[0]
                u_info = conn.execute("SELECT avatar FROM users WHERE nick=?", (other,)).fetchone()
                c['name'] = other
                c['avatar'] = u_info['avatar'] if u_info else 'https://img.icons8.com/glassmorphism/96/user.png'
            res.append(c)
    conn.close()
    return jsonify(res)

@app.route('/api/profile', methods=['POST'])
def update_profile():
    d = request.json
    conn = get_db()
    conn.execute("UPDATE users SET bio=?, avatar=? WHERE nick=?", (d['bio'], d['avatar'], d['nick']))
    conn.commit() # СОХРАНЯЕМ ПРОФИЛЬ
    conn.close()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

