import os, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('flux_glass.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Таблица пользователей
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (nick TEXT PRIMARY KEY, email TEXT UNIQUE, password TEXT, avatar TEXT, is_v INTEGER)''')
    # Таблица сообщений
    cur.execute('''CREATE TABLE IF NOT EXISTS messages 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER, avatar TEXT, likes INTEGER DEFAULT 0)''')
    
    # Твой личный аккаунт Создателя (вшит намертво)
    cur.execute("INSERT OR IGNORE INTO users VALUES ('bloody', 'nexusbloody7@gmail.com', 'Zavoz7152', 'https://img.icons8.com/fluency/96/user-male-circle.png', 1)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    action = d.get('action')
    email = d.get('email', '').strip()
    pw = d.get('password', '')
    
    conn = get_db()
    if action == 'register':
        nick = d.get('nick', '').strip()
        avatar = d.get('avatar', 'https://img.icons8.com/glassmorphism/96/user.png')
        is_v = 1 if nick.lower() == 'bloody' else 0
        try:
            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (nick, email, pw, avatar, is_v))
            conn.commit()
            user = {"nick": nick, "avatar": avatar, "is_v": is_v}
            conn.close()
            return jsonify({"status": "ok", "user": user})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"status": "error", "msg": "Ник или почта уже заняты"})

    elif action == 'login':
        user = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw)).fetchone()
        conn.close()
        if user:
            return jsonify({"status": "ok", "user": dict(user)})
        return jsonify({"status": "error", "msg": "Неверная почта или пароль"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_msgs():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        t = datetime.now().strftime('%H:%M')
        user = conn.execute("SELECT avatar, is_v FROM users WHERE nick=?", (d['sender'],)).fetchone()
        avatar = user['avatar'] if user else ''
        is_v = user['is_v'] if user else 0
        
        conn.execute("INSERT INTO messages (chat_id, sender, text, time, is_v, avatar) VALUES (?, ?, ?, ?, ?, ?)", 
                     (d.get('chat_id', 'community'), d['sender'], d['text'], t, is_v, avatar))
        conn.commit()
        return jsonify({"status": "ok"})
    
    chat_id = request.args.get('chat_id', 'community')
    msgs = [dict(m) for m in conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id ASC", (chat_id,)).fetchall()]
    conn.close()
    return jsonify(msgs)

@app.route('/api/react', methods=['POST'])
def react():
    msg_id = request.json.get('msg_id')
    conn = get_db()
    conn.execute("UPDATE messages SET likes = likes + 1 WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

