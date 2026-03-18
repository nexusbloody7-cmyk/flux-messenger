import os, sqlite3, uuid
from flask import Flask, request, jsonify, render_template
from datetime import datetime

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('flux.db')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (nick TEXT PRIMARY KEY, password TEXT, is_verified INTEGER)')
    cur.execute('CREATE TABLE IF NOT EXISTS messages (chat_id TEXT, sender TEXT, text TEXT, time TEXT, is_v INTEGER)')
    cur.execute("INSERT OR REPLACE INTO users VALUES ('bloody', 'Zavoz7152', 1)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    d = request.json
    n, p = d.get('nick', '').lower().strip(), d.get('password', '')
    if n == 'bloody' and p == 'Zavoz7152':
        return jsonify({"status": "ok", "user": {"nick": "bloody", "is_verified": 1}})
    return jsonify({"status": "error"})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_msgs():
    conn = sqlite3.connect('flux.db')
    conn.row_factory = sqlite3.Row
    if request.method == 'POST':
        d = request.json
        t = datetime.now().strftime('%H:%M')
        is_v = 1 if d['sender'] == 'bloody' else 0
        conn.execute('INSERT INTO messages VALUES (?, ?, ?, ?, ?)', ('community', d['sender'], d['text'], t, is_v))
        conn.commit()
    
    msgs = [dict(m) for m in conn.execute('SELECT * FROM messages ORDER BY rowid ASC').fetchall()]
    conn.close()
    return jsonify(msgs)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


