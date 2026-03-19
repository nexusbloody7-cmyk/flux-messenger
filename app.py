import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.config['SECRET_KEY'] = 'flux_direct_v6'

def get_db():
    conn = sqlite3.connect('flux_glass_v6.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Пользователи
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
        (nick TEXT PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, 
         password TEXT, avatar TEXT, bio TEXT, is_v INTEGER)''')
    
    # Чаты: id, имя, тип: public/direct, участники (для direct — 'user1,user2')
    cur.execute('''CREATE TABLE IF NOT EXISTS chats 
        (id TEXT PRIMARY KEY, name TEXT, type TEXT, owner TEXT, participants TEXT)''')
    
    # Сообщения
    cur.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, 
         text TEXT, time TEXT, is_v INTEGER, avatar TEXT)''')
    
    # Твой эталонный аккаунт Основателя
    cur.execute("""INSERT OR IGNORE INTO users VALUES 
        ('bloody', '@bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 
         'https://img.icons8.com/fluency/96/user-male-circle.png', 
         'Основатель Flux. Создаю будущее.', 1)""")
    
    # Общий чат Flux Community
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
            return jsonify({"status": "ok", "user": {"nick": d['nick'], "username": uname, "avatar": d['avatar'], "is_v": is_v, "bio": 'Новый пользователь Flux'}})
        except: return jsonify({"status": "error", "msg": "Ошибка регистрации"})
    else:
        u = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (d['email'], d['password'])).fetchone()
        return jsonify({"status": "ok", "user": dict(u)}) if u else jsonify({"status": "error", "msg": "Ошибка входа"})

@app.route('/api/profile', methods=['POST'])
def update_profile():
    d = request.json
    conn = get_db()
    conn.execute("UPDATE users SET bio=?, avatar=? WHERE nick=?", (d['bio'], d['avatar'], d['nick']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
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
    conn.close()
    return jsonify(msgs)

@app.route('/api/chats', methods=['GET', 'POST'])
def handle_chats():
    conn = get_db()
    user_nick = request.args.get('user_nick', '')
    
    if request.method == 'POST':
        d = request.json
        conn = get_db()
        
        # Проверка на дубликат директ-чата
        if d['type'] == 'direct':
            participants = sorted([d['owner'], d['target']])
            p_str = ','.join(participants)
            existing = conn.execute("SELECT id FROM chats WHERE participants=?", (p_str,)).fetchone()
            if existing: return jsonify({"status": "ok", "id": existing['id']})
            
            chat_id = "dm_" + str(uuid.uuid4())[:8]
            target_user = conn.execute("SELECT nick FROM users WHERE username=?", (d['target'],)).fetchone()
            if not target_user: return jsonify({"status": "error", "msg": "Юзер не найден"})
            chat_name = f"{d['owner']} & {target_user['nick']}"
            
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, chat_name, 'direct', d['owner'], p_str))
            conn.commit()
            return jsonify({"status": "ok", "id": chat_id})
        
        # Создание публичной группы (как раньше)
        chat_id = str(uuid.uuid4())[:8]
        conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, d['name'], 'public', d['owner'], NULL))
        conn.commit()
        return jsonify({"status": "ok", "id": chat_id})

    # ГЕТ запрос: показать только Flux Community и ТВОИ личные чаты
    chats = []
    
    # 1. Показать Flux Community
    community = conn.execute("SELECT * FROM chats WHERE id='community'").fetchone()
    if community: chats.append(dict(community))
    
    # 2. Показать директ чаты, где этот юзер — участник
    if user_nick:
        my_directs = conn.execute("SELECT * FROM chats WHERE type='direct' AND participants LIKE ?", (f'%{user_nick}%',)).fetchall()
        for c in my_directs:
            c_dict = dict(c)
            # Узнать, с кем личка (чтобы поставить его аватарку и имя)
            p = c_dict['participants'].split(',')
            other_user_nick = p[1] if p[0] == user_nick else p[0]
            other_user = conn.execute("SELECT avatar FROM users WHERE nick=?", (other_user_nick,)).fetchone()
            
            c_dict['other_user'] = other_user_nick
            c_dict['avatar'] = other_user['avatar'] if other_user else 'https://img.icons8.com/glassmorphism/96/user.png'
            chats.append(c_dict)
            
    # 3. Показать публичные группы (которые создали пользователи)
    other_public = conn.execute("SELECT * FROM chats WHERE type='public' AND id != 'community'").fetchall()
    for c in other_public: chats.append(dict(c))
            
    conn.close()
    return jsonify(chats)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

