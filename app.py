import os, json, time, hashlib, secrets, re
from flask import Flask, request, jsonify, send_from_directory, session
from datetime import timedelta
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'flux_secret_bloody_2025_xkq9')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

DATABASE_URL = os.environ.get('DATABASE_URL', '')
BASE = os.path.dirname(os.path.abspath(__file__))

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def hp(p): return hashlib.sha256((p + 'flux_salt_2025').encode()).hexdigest()
def gid(): return secrets.token_hex(10)
def now(): return int(time.time() * 1000)
def make_flux_id(): return 'FLX-' + secrets.token_hex(4).upper()

PREMIUM_PRICE = 299  # Flux Coins

def auth(f):
    @wraps(f)
    def w(*a, **kw):
        uid = session.get('uid')
        if not uid: return jsonify({'error': 'Unauthorized'}), 401
        conn = get_db(); cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE id=%s', (uid,))
        u = cur.fetchone(); conn.close()
        if not u: return jsonify({'error': 'Unauthorized'}), 401
        return f(dict(u), *a, **kw)
    return w

def sys_msg(cid, text):
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,is_system,timestamp) VALUES (%s,%s,NULL,NULL,%s,TRUE,%s)',
                (gid(), cid, text, now()))
    conn.commit(); conn.close()

def is_chat_admin(u, cid):
    if u['role'] in ('admin','creator'): return True
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT is_admin FROM chat_members WHERE chat_id=%s AND user_id=%s', (cid, u['id']))
    m = cur.fetchone()
    cur.execute('SELECT creator_id FROM chats WHERE id=%s', (cid,))
    c = cur.fetchone(); conn.close()
    return (m and m['is_admin']) or (c and c['creator_id'] == u['id'])

def is_member(uid, cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM chat_members WHERE chat_id=%s AND user_id=%s', (cid, uid))
    r = cur.fetchone(); conn.close()
    return r is not None

def get_chat(cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM chats WHERE id=%s', (cid,))
    c = cur.fetchone()
    if not c: conn.close(); return None
    cur.execute('SELECT user_id FROM chat_members WHERE chat_id=%s', (cid,))
    members = [r['user_id'] for r in cur.fetchall()]
    cur.execute('SELECT user_id FROM chat_members WHERE chat_id=%s AND is_admin=TRUE', (cid,))
    admins = [r['user_id'] for r in cur.fetchall()]
    conn.close()
    d = dict(c); d['members'] = members; d['admins'] = admins
    return d

def get_user(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id=%s', (uid,))
    u = cur.fetchone(); conn.close()
    if not u: return None
    d = dict(u); d.pop('password', None)
    d['online'] = bool(d.get('online') and now() - (d.get('last_seen') or 0) < 15000)
    d['linked_services'] = json.loads(d.get('linked_services') or '[]')
    d['privacy'] = json.loads(d.get('privacy') or '{}')
    d['flux_coins'] = d.get('flux_coins') or 0
    d['premium'] = bool(d.get('premium'))
    d['bio'] = d.get('bio') or ''
    return d

def init_db():
    conn = get_db(); cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, flux_id TEXT, email TEXT UNIQUE,
        username TEXT UNIQUE, nick TEXT, password TEXT,
        role TEXT DEFAULT 'user', avatar TEXT,
        banned BOOLEAN DEFAULT FALSE, muted BOOLEAN DEFAULT FALSE,
        online BOOLEAN DEFAULT FALSE, last_seen BIGINT DEFAULT 0,
        created_at BIGINT DEFAULT 0, linked_services TEXT DEFAULT '[]',
        privacy TEXT DEFAULT '{}', bio TEXT DEFAULT '',
        flux_coins INTEGER DEFAULT 0, premium BOOLEAN DEFAULT FALSE
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY, type TEXT, name TEXT, description TEXT,
        icon TEXT, username TEXT, creator_id TEXT,
        pinned BOOLEAN DEFAULT FALSE, verified BOOLEAN DEFAULT FALSE,
        created_at BIGINT DEFAULT 0
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS chat_members (
        id SERIAL PRIMARY KEY, chat_id TEXT, user_id TEXT,
        is_admin BOOLEAN DEFAULT FALSE, pinned BOOLEAN DEFAULT FALSE,
        UNIQUE(chat_id, user_id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, chat_id TEXT, sender_id TEXT,
        sender_nick TEXT, text TEXT,
        reply_to TEXT DEFAULT NULL,
        forwarded_from TEXT DEFAULT NULL,
        is_system BOOLEAN DEFAULT FALSE, pinned BOOLEAN DEFAULT FALSE,
        timestamp BIGINT DEFAULT 0
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS reactions (
        id SERIAL PRIMARY KEY, message_id TEXT, user_id TEXT, emoji TEXT,
        UNIQUE(message_id, user_id)
    )''')

    conn.commit()

    # Safe migrations
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS flux_coins INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium BOOLEAN DEFAULT FALSE",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to TEXT DEFAULT NULL",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS forwarded_from TEXT DEFAULT NULL",
        "ALTER TABLE messages DROP COLUMN IF EXISTS media_url",
        "ALTER TABLE messages DROP COLUMN IF EXISTS media_type",
    ]
    for m in migrations:
        try:
            cur.execute(m); conn.commit()
        except: conn.rollback()

    cur.execute('SELECT id FROM chats WHERE id=%s', ('community',))
    if not cur.fetchone():
        cur.execute('''INSERT INTO chats (id,type,name,description,icon,username,creator_id,pinned,verified,created_at)
                       VALUES ('community','group','Flux Community','Глобальный чат','⚡','community',NULL,TRUE,TRUE,%s)''', (now(),))
        cur.execute('INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,is_system,timestamp) VALUES (%s,%s,NULL,NULL,%s,TRUE,%s)',
                    (gid(),'community','⚡ Добро пожаловать в Flux Community!',now()))
        conn.commit()
    conn.close()

# ── RESET BLOODY ──────────────────────────────
@app.route('/api/reset-bloody')
def reset_bloody():
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username=%s', ('bloody',))
    rows = cur.fetchall(); deleted = [r['id'] for r in rows]
    for uid in deleted:
        cur.execute('DELETE FROM chat_members WHERE user_id=%s', (uid,))
        cur.execute('DELETE FROM users WHERE id=%s', (uid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': deleted})

# ── REGISTER ──────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    password = d.get('password','')
    if not all([email,nick,username,password]):
        return jsonify({'error':'Заполните все поля'}), 400
    if len(password) < 6:
        return jsonify({'error':'Пароль минимум 6 символов'}), 400
    if len(username) < 3:
        return jsonify({'error':'Username минимум 3 символа'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE email=%s', (email,))
    if cur.fetchone(): conn.close(); return jsonify({'error':'Email уже занят'}), 400
    cur.execute('SELECT id FROM users WHERE username=%s', (username,))
    if cur.fetchone(): conn.close(); return jsonify({'error':'Username уже занят'}), 400
    role = 'creator' if username == 'bloody' else 'user'
    uid = gid(); fid = make_flux_id()
    cur.execute('''INSERT INTO users (id,flux_id,email,username,nick,password,role,avatar,
                   banned,muted,online,last_seen,created_at,linked_services,privacy,bio,flux_coins,premium)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,FALSE,FALSE,TRUE,%s,%s,'[]','{}','',0,FALSE)''',
                (uid,fid,email,username,nick,hp(password),role,now(),now()))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                ('community',uid,role=='creator'))
    if role == 'creator':
        cur.execute('UPDATE chats SET creator_id=%s WHERE id=%s', (uid,'community'))
    conn.commit(); conn.close()
    sys_msg('community', f'👋 @{username} присоединился к Flux Community!')
    session.permanent = True; session['uid'] = uid
    return jsonify({'ok':True,'user':get_user(uid)})

# ── LOGIN ──────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email = d.get('email','').strip().lower()
    password = d.get('password','')
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE email=%s', (email,))
    u = cur.fetchone()
    if not u: conn.close(); return jsonify({'error':'Аккаунт не найден'}), 400
    u = dict(u)
    if u.get('banned'): conn.close(); return jsonify({'error':'Аккаунт заблокирован'}), 403
    if u['password'] != hp(password): conn.close(); return jsonify({'error':'Неверный пароль'}), 400
    cur.execute('UPDATE users SET online=TRUE,last_seen=%s WHERE id=%s', (now(),u['id']))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,FALSE) ON CONFLICT DO NOTHING',
                ('community',u['id']))
    conn.commit(); conn.close()
    session.permanent = True; session['uid'] = u['id']
    return jsonify({'ok':True,'user':get_user(u['id'])})

@app.route('/api/logout', methods=['POST'])
@auth
def logout(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE users SET online=FALSE,last_seen=%s WHERE id=%s', (now(),me['id']))
    conn.commit(); conn.close()
    session.clear()
    return jsonify({'ok':True})

@app.route('/api/me')
@auth
def get_me(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE users SET online=TRUE,last_seen=%s WHERE id=%s', (now(),me['id']))
    conn.commit(); conn.close()
    return jsonify(get_user(me['id']))

@app.route('/api/users/heartbeat', methods=['POST'])
@auth
def heartbeat(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE users SET online=TRUE,last_seen=%s WHERE id=%s', (now(),me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/users')
@auth
def get_users(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id!=%s', (me['id'],))
    users = cur.fetchall(); conn.close()
    result = []
    for u in users:
        d = dict(u); d.pop('password',None)
        d['online'] = bool(d.get('online') and now()-(d.get('last_seen') or 0)<15000)
        d['linked_services'] = json.loads(d.get('linked_services') or '[]')
        d['privacy'] = json.loads(d.get('privacy') or '{}')
        d['flux_coins'] = d.get('flux_coins') or 0
        d['premium'] = bool(d.get('premium'))
        d['bio'] = d.get('bio') or ''
        result.append(d)
    return jsonify(result)

@app.route('/api/users/<uid>')
@auth
def get_user_route(me, uid):
    u = get_user(uid)
    if not u: return jsonify({'error':'Not found'}), 404
    return jsonify(u)

# ── PROFILE UPDATE ────────────────────────────
@app.route('/api/users/me/profile', methods=['PUT'])
@auth
def update_profile(me):
    d = request.json or {}
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    avatar   = d.get('avatar')
    bio      = d.get('bio','').strip()[:200]
    privacy  = d.get('privacy')
    if not nick or not username:
        return jsonify({'error':'Заполните поля'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username=%s AND id!=%s', (username,me['id']))
    if cur.fetchone(): conn.close(); return jsonify({'error':'Username занят'}), 400
    cur.execute('UPDATE users SET nick=%s,username=%s,bio=%s WHERE id=%s', (nick,username,bio,me['id']))
    if avatar is not None:
        cur.execute('UPDATE users SET avatar=%s WHERE id=%s', (avatar,me['id']))
    if privacy is not None:
        cur.execute('UPDATE users SET privacy=%s WHERE id=%s', (json.dumps(privacy),me['id']))
    conn.commit(); conn.close()
    return jsonify(get_user(me['id']))

# ── CHANGE PASSWORD ───────────────────────────
@app.route('/api/users/me/change-password', methods=['POST'])
@auth
def change_password(me):
    d = request.json or {}
    old_pass = d.get('old_password','')
    new_pass = d.get('new_password','')
    if not old_pass or not new_pass:
        return jsonify({'error':'Заполните поля'}), 400
    if len(new_pass) < 6:
        return jsonify({'error':'Пароль минимум 6 символов'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT password FROM users WHERE id=%s', (me['id'],))
    u = cur.fetchone()
    if not u or u['password'] != hp(old_pass):
        conn.close(); return jsonify({'error':'Неверный текущий пароль'}), 400
    cur.execute('UPDATE users SET password=%s WHERE id=%s', (hp(new_pass),me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

# ── CHANGE EMAIL ──────────────────────────────
@app.route('/api/users/me/change-email', methods=['POST'])
@auth
def change_email(me):
    d = request.json or {}
    password = d.get('password','')
    new_email = d.get('new_email','').strip().lower()
    if not password or not new_email:
        return jsonify({'error':'Заполните поля'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT password FROM users WHERE id=%s', (me['id'],))
    u = cur.fetchone()
    if not u or u['password'] != hp(password):
        conn.close(); return jsonify({'error':'Неверный пароль'}), 400
    cur.execute('SELECT id FROM users WHERE email=%s AND id!=%s', (new_email,me['id']))
    if cur.fetchone():
        conn.close(); return jsonify({'error':'Email уже занят'}), 400
    cur.execute('UPDATE users SET email=%s WHERE id=%s', (new_email,me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

# ── FLUX PREMIUM ──────────────────────────────
@app.route('/api/users/me/buy-premium', methods=['POST'])
@auth
def buy_premium(me):
    if me.get('premium'):
        return jsonify({'error':'У вас уже есть Flux Premium'}), 400
    if me.get('flux_coins',0) < PREMIUM_PRICE:
        return jsonify({'error':f'Недостаточно Flux Coins. Нужно {PREMIUM_PRICE}'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE users SET premium=TRUE,flux_coins=flux_coins-%s WHERE id=%s',
                (PREMIUM_PRICE,me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'user':get_user(me['id'])})

# ── GIVE FLUX COINS (bloody only) ─────────────
@app.route('/api/admin/give-coins', methods=['POST'])
@auth
def give_coins(me):
    if me.get('username') != 'bloody':
        return jsonify({'error':'Forbidden'}), 403
    d = request.json or {}
    target_username = d.get('username','').strip().lstrip('@')
    amount = d.get('amount',0)
    if not target_username or amount <= 0:
        return jsonify({'error':'Укажи username и количество'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id,username,flux_coins FROM users WHERE username=%s', (target_username,))
    target = cur.fetchone()
    if not target:
        conn.close(); return jsonify({'error':f'Пользователь @{target_username} не найден'}), 404
    cur.execute('UPDATE users SET flux_coins=flux_coins+%s WHERE id=%s', (amount,target['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'message':f'Выдано {amount} Flux Coins пользователю @{target_username}'})

# ── ADMIN ACTIONS ─────────────────────────────
@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@auth
def admin_action(me, uid):
    if me['role'] not in ('admin','creator'):
        return jsonify({'error':'Forbidden'}), 403
    target = get_user(uid)
    if not target: return jsonify({'error':'Not found'}), 404
    if target['role'] == 'creator' and me.get('username') != 'bloody':
        return jsonify({'error':'Нельзя'}), 403
    d = request.json or {}; a = d.get('action')
    conn = get_db(); cur = conn.cursor()
    if   a == 'ban':    cur.execute('UPDATE users SET banned=TRUE WHERE id=%s',(uid,))
    elif a == 'unban':  cur.execute('UPDATE users SET banned=FALSE WHERE id=%s',(uid,))
    elif a == 'mute':   cur.execute('UPDATE users SET muted=TRUE WHERE id=%s',(uid,))
    elif a == 'unmute': cur.execute('UPDATE users SET muted=FALSE WHERE id=%s',(uid,))
    elif a == 'verify_premium':
        cur.execute('UPDATE users SET premium=TRUE WHERE id=%s',(uid,))
    elif a == 'give_role':
        r = d.get('role')
        if r not in ('user','admin','creator','tester'):
            conn.close(); return jsonify({'error':'Неверная роль'}), 400
        if r == 'creator' and me.get('username') != 'bloody':
            conn.close(); return jsonify({'error':'Только bloody'}), 403
        cur.execute('UPDATE users SET role=%s WHERE id=%s',(r,uid))
    else: conn.close(); return jsonify({'error':'Unknown'}), 400
    conn.commit(); conn.close()
    return jsonify({'ok':True,'user':get_user(uid)})

# ── CHATS ─────────────────────────────────────
@app.route('/api/chats')
@auth
def get_chats(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('''SELECT cm.pinned as member_pinned, c.* FROM chat_members cm
                   JOIN chats c ON c.id=cm.chat_id
                   WHERE cm.user_id=%s ORDER BY cm.pinned DESC, c.created_at DESC''', (me['id'],))
    chat_ids = [(r['id'], r['member_pinned']) for r in cur.fetchall()]
    conn.close()
    result = []
    for cid, pinned in chat_ids:
        c = get_chat(cid)
        if c: c['member_pinned'] = pinned; result.append(c)
    return jsonify(result)

@app.route('/api/chats', methods=['POST'])
@auth
def create_chat(me):
    d = request.json or {}
    t = d.get('type','group'); name = d.get('name','').strip()
    ch_username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower()) if t=='channel' else None
    icon = d.get('icon','').strip() or ('📢' if t=='channel' else '👥')
    if not name: return jsonify({'error':'Укажите название'}), 400
    if t == 'channel' and not ch_username:
        return jsonify({'error':'Укажите username канала'}), 400
    if ch_username:
        conn = get_db(); cur = conn.cursor()
        cur.execute('SELECT id FROM chats WHERE username=%s', (ch_username,))
        if cur.fetchone(): conn.close(); return jsonify({'error':'Username канала занят'}), 400
        conn.close()
    cid = gid()
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO chats (id,type,name,description,icon,username,creator_id,pinned,verified,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE,%s)',
                (cid,t,name,d.get('description',''),icon,ch_username,me['id'],now()))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,TRUE)', (cid,me['id']))
    conn.commit(); conn.close()
    sys_msg(cid, f'{"Канал" if t=="channel" else "Группа"} "{name}" создан(а)')
    return jsonify(get_chat(cid))

@app.route('/api/chats/dm', methods=['POST'])
@auth
def create_dm(me):
    oid = (request.json or {}).get('user_id')
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE id=%s', (oid,))
    if not cur.fetchone(): conn.close(); return jsonify({'error':'User not found'}), 404
    cur.execute('''SELECT cm1.chat_id FROM chat_members cm1
                   JOIN chat_members cm2 ON cm1.chat_id=cm2.chat_id
                   JOIN chats c ON c.id=cm1.chat_id
                   WHERE cm1.user_id=%s AND cm2.user_id=%s AND c.type='dm' ''', (me['id'],oid))
    ex = cur.fetchone()
    if ex: conn.close(); return jsonify(get_chat(ex['chat_id']))
    cid = gid()
    cur.execute('INSERT INTO chats (id,type,name,description,icon,username,creator_id,pinned,verified,created_at) VALUES (%s,%s,NULL,%s,%s,NULL,%s,FALSE,FALSE,%s)',
                (cid,'dm','','',me['id'],now()))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,FALSE)', (cid,me['id']))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,FALSE)', (cid,oid))
    conn.commit(); conn.close()
    return jsonify(get_chat(cid))

@app.route('/api/chats/<cid>', methods=['PUT'])
@auth
def update_chat(me, cid):
    if not is_chat_admin(me, cid): return jsonify({'error':'Forbidden'}), 403
    d = request.json or {}
    conn = get_db(); cur = conn.cursor()
    for k in ('name','description','icon'):
        if k in d: cur.execute(f'UPDATE chats SET {k}=%s WHERE id=%s', (d[k],cid))
    conn.commit(); conn.close()
    return jsonify(get_chat(cid))

@app.route('/api/chats/<cid>', methods=['DELETE'])
@auth
def delete_chat(me, cid):
    if me['role'] not in ('admin','creator') and not is_chat_admin(me,cid):
        return jsonify({'error':'Forbidden'}), 403
    conn = get_db(); cur = conn.cursor()
    cur.execute('DELETE FROM reactions WHERE message_id IN (SELECT id FROM messages WHERE chat_id=%s)', (cid,))
    cur.execute('DELETE FROM messages WHERE chat_id=%s', (cid,))
    cur.execute('DELETE FROM chat_members WHERE chat_id=%s', (cid,))
    cur.execute('DELETE FROM chats WHERE id=%s', (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/pin-chat', methods=['POST'])
@auth
def pin_chat(me, cid):
    pinned = (request.json or {}).get('pinned', True)
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE chat_members SET pinned=%s WHERE chat_id=%s AND user_id=%s', (pinned,cid,me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/verify', methods=['POST'])
@auth
def verify_chat(me, cid):
    if me.get('username') != 'bloody': return jsonify({'error':'Forbidden'}), 403
    verified = (request.json or {}).get('verified', True)
    conn = get_db(); cur = conn.cursor()
    cur.execute('UPDATE chats SET verified=%s WHERE id=%s', (verified,cid))
    conn.commit(); conn.close()
    sys_msg(cid, '✅ Канал верифицирован' if verified else '❌ Верификация снята')
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/members', methods=['POST'])
@auth
def add_member(me, cid):
    if not is_chat_admin(me,cid): return jsonify({'error':'Forbidden'}), 403
    uid = (request.json or {}).get('user_id')
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT username FROM users WHERE id=%s', (uid,))
    u = cur.fetchone()
    if not u: conn.close(); return jsonify({'error':'User not found'}), 404
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,FALSE) ON CONFLICT DO NOTHING', (cid,uid))
    conn.commit(); conn.close()
    sys_msg(cid, f'➕ @{u["username"]} добавлен в чат')
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/leave', methods=['POST'])
@auth
def leave_chat(me, cid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('DELETE FROM chat_members WHERE chat_id=%s AND user_id=%s', (cid,me['id']))
    conn.commit(); conn.close()
    sys_msg(cid, f'🚪 @{me["username"]} покинул(а) чат')
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/clear', methods=['POST'])
@auth
def clear_chat(me, cid):
    if not is_chat_admin(me,cid): return jsonify({'error':'Forbidden'}), 403
    conn = get_db(); cur = conn.cursor()
    cur.execute('DELETE FROM reactions WHERE message_id IN (SELECT id FROM messages WHERE chat_id=%s)', (cid,))
    cur.execute('DELETE FROM messages WHERE chat_id=%s', (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

# ── MESSAGES ──────────────────────────────────
@app.route('/api/chats/<cid>/messages')
@auth
def get_messages(me, cid):
    if not is_member(me['id'],cid): return jsonify({'error':'Not a member'}), 403
    since = request.args.get('since',0,type=int)
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM messages WHERE chat_id=%s AND timestamp>%s ORDER BY timestamp ASC', (cid,since))
    msgs = cur.fetchall()
    result = []
    for m in msgs:
        d = dict(m); d['system'] = d.pop('is_system',False)
        cur.execute('SELECT emoji,COUNT(*) as cnt FROM reactions WHERE message_id=%s GROUP BY emoji', (m['id'],))
        d['reactions'] = [dict(r) for r in cur.fetchall()]
        cur.execute('SELECT emoji FROM reactions WHERE message_id=%s AND user_id=%s', (m['id'],me['id']))
        my_r = cur.fetchone()
        d['my_reaction'] = my_r['emoji'] if my_r else None
        # Fetch reply_to message
        if d.get('reply_to'):
            cur.execute('SELECT id,sender_nick,text FROM messages WHERE id=%s', (d['reply_to'],))
            rep = cur.fetchone()
            d['reply_to_msg'] = dict(rep) if rep else None
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/chats/<cid>/messages', methods=['POST'])
@auth
def send_message(me, cid):
    if not is_member(me['id'],cid): return jsonify({'error':'Not a member'}), 403
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM chats WHERE id=%s', (cid,))
    c = cur.fetchone(); conn.close()
    if not c: return jsonify({'error':'Chat not found'}), 404
    if c['type'] == 'channel' and not is_chat_admin(me,cid):
        return jsonify({'error':'Only admins can post'}), 403
    if me.get('muted') and me['role'] not in ('admin','creator'):
        return jsonify({'error':'Вы замьючены'}), 403
    d = request.json or {}
    text = d.get('text','').strip()
    reply_to = d.get('reply_to')
    forwarded_from = d.get('forwarded_from')
    if not text: return jsonify({'error':'Empty'}), 400
    if text.startswith('/') and me['role'] in ('admin','creator'):
        return jsonify(handle_cmd(me,cid,text))
    mid = gid()
    conn = get_db(); cur = conn.cursor()
    cur.execute('''INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,reply_to,forwarded_from,is_system,pinned,timestamp)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE,%s)''',
                (mid,cid,me['id'],me['nick'],text,reply_to,forwarded_from,now()))
    conn.commit()
    cur.execute('SELECT * FROM messages WHERE id=%s', (mid,))
    msg = dict(cur.fetchone()); conn.close()
    msg['system'] = msg.pop('is_system',False)
    msg['reactions'] = []; msg['my_reaction'] = None
    # Fetch reply_to
    if msg.get('reply_to'):
        rep = get_message_brief(msg['reply_to'])
        msg['reply_to_msg'] = rep
    return jsonify(msg)

# ── FORWARD MESSAGE ───────────────────────────
@app.route('/api/messages/<mid>/forward', methods=['POST'])
@auth
def forward_message(me, mid):
    d = request.json or {}
    target_cids = d.get('chat_ids', [])
    if not target_cids: return jsonify({'error':'Укажи чаты'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM messages WHERE id=%s', (mid,))
    orig = cur.fetchone()
    if not orig: conn.close(); return jsonify({'error':'Not found'}), 404
    forwarded = []
    for tcid in target_cids[:5]:  # Max 5 chats at once
        if not is_member(me['id'], tcid): continue
        new_mid = gid()
        forward_text = orig['text']
        orig_nick = orig['sender_nick'] or 'Пользователь'
        cur.execute('''INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,forwarded_from,is_system,pinned,timestamp)
                       VALUES (%s,%s,%s,%s,%s,%s,FALSE,FALSE,%s)''',
                    (new_mid,tcid,me['id'],me['nick'],forward_text,orig_nick,now()))
        forwarded.append(tcid)
    conn.commit(); conn.close()
    return jsonify({'ok':True,'forwarded_to':forwarded})

def get_message_brief(mid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id,sender_nick,text FROM messages WHERE id=%s', (mid,))
    r = cur.fetchone(); conn.close()
    return dict(r) if r else None

@app.route('/api/messages/<mid>/delete', methods=['POST'])
@auth
def delete_message(me, mid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM messages WHERE id=%s', (mid,))
    msg = cur.fetchone()
    if not msg: conn.close(); return jsonify({'error':'Not found'}), 404
    if msg['sender_id'] != me['id'] and not is_chat_admin(me, msg['chat_id']):
        conn.close(); return jsonify({'error':'Forbidden'}), 403
    cur.execute('DELETE FROM reactions WHERE message_id=%s', (mid,))
    cur.execute('DELETE FROM messages WHERE id=%s', (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/messages/<mid>/pin', methods=['POST'])
@auth
def pin_message(me, mid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM messages WHERE id=%s', (mid,))
    msg = cur.fetchone()
    if not msg: conn.close(); return jsonify({'error':'Not found'}), 404
    if not is_chat_admin(me, msg['chat_id']): conn.close(); return jsonify({'error':'Forbidden'}), 403
    pinned = (request.json or {}).get('pinned', True)
    cur.execute('UPDATE messages SET pinned=%s WHERE id=%s', (pinned,mid))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/messages/<mid>/react', methods=['POST'])
@auth
def react_message(me, mid):
    emoji = (request.json or {}).get('emoji','')
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT emoji FROM reactions WHERE message_id=%s AND user_id=%s', (mid,me['id']))
    existing = cur.fetchone()
    if existing:
        if existing['emoji'] == emoji:
            cur.execute('DELETE FROM reactions WHERE message_id=%s AND user_id=%s', (mid,me['id']))
        else:
            cur.execute('UPDATE reactions SET emoji=%s WHERE message_id=%s AND user_id=%s', (emoji,mid,me['id']))
    else:
        cur.execute('INSERT INTO reactions (message_id,user_id,emoji) VALUES (%s,%s,%s)', (mid,me['id'],emoji))
    conn.commit()
    cur.execute('SELECT emoji,COUNT(*) as cnt FROM reactions WHERE message_id=%s GROUP BY emoji', (mid,))
    reactions = [dict(r) for r in cur.fetchall()]
    cur.execute('SELECT emoji FROM reactions WHERE message_id=%s AND user_id=%s', (mid,me['id']))
    my_r = cur.fetchone()
    conn.close()
    return jsonify({'ok':True,'reactions':reactions,'my_reaction':my_r['emoji'] if my_r else None})

# ── COMMANDS ──────────────────────────────────
def handle_cmd(me, cid, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    a1 = parts[1] if len(parts)>1 else None
    a2 = parts[2] if len(parts)>2 else None
    conn = get_db(); cur = conn.cursor()

    def fu(name):
        if not name: return None
        n = name.lstrip('@')
        cur.execute('SELECT * FROM users WHERE username=%s OR id=%s', (n,n))
        u = cur.fetchone()
        return dict(u) if u else None

    simple = {
        'ban':    ('banned',True,  '🔨 @{u} заблокирован'),
        'unban':  ('banned',False, '✅ @{u} разблокирован'),
        'mute':   ('muted', True,  '🔇 @{u} замьючен'),
        'unmute': ('muted', False, '🔊 @{u} размьючен'),
    }
    if cmd in simple:
        t = fu(a1)
        if not t: conn.close(); return {'error':'Не найден'}
        if t['role']=='creator' and me.get('username')!='bloody': conn.close(); return {'error':'Нельзя'}
        field,val,tmpl = simple[cmd]
        cur.execute(f'UPDATE users SET {field}=%s WHERE id=%s',(val,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid, tmpl.replace('{u}',t['username']))
        return {'ok':True,'command':cmd}

    if cmd == 'give_role':
        t = fu(a1)
        if not t or not a2: conn.close(); return {'error':'Укажи @user и роль'}
        if a2 not in ('user','admin','creator','tester'): conn.close(); return {'error':'user/admin/creator/tester'}
        if a2=='creator' and me.get('username')!='bloody': conn.close(); return {'error':'Только bloody'}
        cur.execute('UPDATE users SET role=%s WHERE id=%s',(a2,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid,f'👑 @{t["username"]} → роль: {a2}')
        return {'ok':True,'command':cmd}

    if cmd == 'give_coins':
        if me.get('username') != 'bloody': conn.close(); return {'error':'Только bloody'}
        t = fu(a1)
        if not t or not a2: conn.close(); return {'error':'Укажи @user и количество'}
        try: amount = int(a2)
        except: conn.close(); return {'error':'Неверное количество'}
        cur.execute('UPDATE users SET flux_coins=flux_coins+%s WHERE id=%s',(amount,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid,f'⚡ @{t["username"]} получил {amount} Flux Coins!')
        return {'ok':True,'command':cmd}

    if cmd == 'verify':
        t_chat = a1
        if not t_chat: conn.close(); return {'error':'Укажи ID или username'}
        cur.execute('UPDATE chats SET verified=TRUE WHERE id=%s OR username=%s',(t_chat,t_chat))
        conn.commit(); conn.close()
        sys_msg(cid,'✅ Канал верифицирован')
        return {'ok':True,'command':cmd}

    if cmd == 'announce':
        conn.close()
        sys_msg('community','📢 Объявление: '+' '.join(parts[1:]))
        return {'ok':True,'command':cmd}

    if cmd == 'kick':
        t = fu(a1)
        if not t: conn.close(); return {'error':'Не найден'}
        cur.execute('DELETE FROM chat_members WHERE chat_id=%s AND user_id=%s',(cid,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid,f'👢 @{t["username"]} исключён')
        return {'ok':True,'command':cmd}

    if cmd == 'pin':
        cur.execute('SELECT id FROM messages WHERE chat_id=%s ORDER BY timestamp DESC LIMIT 1',(cid,))
        msg = cur.fetchone()
        if msg:
            cur.execute('UPDATE messages SET pinned=TRUE WHERE id=%s',(msg['id'],))
            conn.commit()
        conn.close()
        sys_msg(cid,'📌 Сообщение закреплено')
        return {'ok':True,'command':cmd}

    if cmd == 'rename':
        new_name = ' '.join(parts[1:])
        if new_name:
            cur.execute('UPDATE chats SET name=%s WHERE id=%s',(new_name,cid))
            conn.commit()
        conn.close()
        sys_msg(cid,f'✏️ Переименован: {new_name}')
        return {'ok':True,'command':cmd}

    if cmd == 'stats':
        cur.execute('SELECT COUNT(*) as cnt FROM users')
        u_cnt = cur.fetchone()['cnt']
        cur.execute('SELECT COUNT(*) as cnt FROM messages WHERE is_system=FALSE')
        m_cnt = cur.fetchone()['cnt']
        conn.close()
        sys_msg(cid,f'📊 {u_cnt} юзеров | {m_cnt} сообщений')
        return {'ok':True,'command':cmd}

    if cmd == 'broadcast':
        msg_text = ' '.join(parts[1:])
        if msg_text:
            cur.execute('SELECT DISTINCT chat_id FROM chat_members')
            chat_ids = [r['chat_id'] for r in cur.fetchall()]
            conn.close()
            for chat_id in chat_ids:
                sys_msg(chat_id,f'📢 Broadcast: {msg_text}')
        else:
            conn.close()
        return {'ok':True,'command':cmd}

    if cmd == 'delete_chat':
        target = a1 or cid
        cur.execute('DELETE FROM reactions WHERE message_id IN (SELECT id FROM messages WHERE chat_id=%s)',(target,))
        cur.execute('DELETE FROM messages WHERE chat_id=%s',(target,))
        cur.execute('DELETE FROM chat_members WHERE chat_id=%s',(target,))
        cur.execute('DELETE FROM chats WHERE id=%s',(target,))
        conn.commit(); conn.close()
        return {'ok':True,'command':cmd,'deleted_chat':target}

    conn.close()
    return {'error':f'Неизвестная команда: /{cmd}'}

# ── STATIC ────────────────────────────────────
@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    sd = os.path.join(BASE,'static')
    if path and os.path.exists(os.path.join(sd,path)):
        return send_from_directory(sd,path)
    return send_from_directory(sd,'index.html')

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0',port=port,debug=False)
