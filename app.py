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
    cur.execute('''INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,is_system,timestamp)
                   VALUES (%s,%s,NULL,NULL,%s,TRUE,%s)''', (gid(), cid, text, now()))
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
    return d

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, flux_id TEXT, email TEXT UNIQUE,
        username TEXT UNIQUE, nick TEXT, password TEXT,
        role TEXT DEFAULT 'user', avatar TEXT,
        banned BOOLEAN DEFAULT FALSE, muted BOOLEAN DEFAULT FALSE,
        online BOOLEAN DEFAULT FALSE, last_seen BIGINT DEFAULT 0,
        created_at BIGINT DEFAULT 0, linked_services TEXT DEFAULT '[]'
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY, type TEXT, name TEXT, description TEXT,
        icon TEXT, creator_id TEXT, pinned BOOLEAN DEFAULT FALSE,
        created_at BIGINT DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS chat_members (
        id SERIAL PRIMARY KEY, chat_id TEXT, user_id TEXT,
        is_admin BOOLEAN DEFAULT FALSE, UNIQUE(chat_id,user_id)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY, chat_id TEXT, sender_id TEXT,
        sender_nick TEXT, text TEXT, is_system BOOLEAN DEFAULT FALSE,
        timestamp BIGINT DEFAULT 0
    )''')
    conn.commit()
    cur.execute('SELECT id FROM chats WHERE id=%s', ('community',))
    if not cur.fetchone():
        cur.execute('''INSERT INTO chats (id,type,name,description,icon,creator_id,pinned,created_at)
                       VALUES ('community','group','Flux Community','Глобальный чат для всех','⚡',NULL,TRUE,%s)''', (now(),))
        cur.execute('''INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,is_system,timestamp)
                       VALUES (%s,'community',NULL,NULL,'⚡ Добро пожаловать в Flux Community!',TRUE,%s)''', (gid(), now()))
        conn.commit()
    conn.close()

@app.route('/api/reset-bloody')
def reset_bloody():
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username=%s', ('bloody',))
    rows = cur.fetchall()
    deleted = [r['id'] for r in rows]
    for uid in deleted:
        cur.execute('DELETE FROM chat_members WHERE user_id=%s', (uid,))
        cur.execute('DELETE FROM users WHERE id=%s', (uid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': deleted})

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
    cur.execute('''INSERT INTO users (id,flux_id,email,username,nick,password,role,avatar,banned,muted,online,last_seen,created_at,linked_services)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,FALSE,FALSE,TRUE,%s,%s,'[]')''',
                (uid,fid,email,username,nick,hp(password),role,now(),now()))
    cur.execute('INSERT INTO chat_members (chat_id,user_id,is_admin) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                ('community',uid,role=='creator'))
    if role == 'creator':
        cur.execute('UPDATE chats SET creator_id=%s WHERE id=%s', (uid,'community'))
    conn.commit(); conn.close()
    sys_msg('community', f'👋 @{username} присоединился к Flux Community!')
    session.permanent = True; session['uid'] = uid
    return jsonify({'ok':True,'user':get_user(uid)})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
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
        result.append(d)
    return jsonify(result)

@app.route('/api/users/<uid>')
@auth
def get_user_route(me, uid):
    u = get_user(uid)
    if not u: return jsonify({'error':'Not found'}), 404
    return jsonify(u)

@app.route('/api/users/me/profile', methods=['PUT'])
@auth
def update_profile(me):
    d = request.json or {}
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    avatar   = d.get('avatar')
    if not nick or not username: return jsonify({'error':'Заполните поля'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username=%s AND id!=%s', (username,me['id']))
    if cur.fetchone(): conn.close(); return jsonify({'error':'Username занят'}), 400
    if avatar is not None:
        cur.execute('UPDATE users SET nick=%s,username=%s,avatar=%s WHERE id=%s', (nick,username,avatar,me['id']))
    else:
        cur.execute('UPDATE users SET nick=%s,username=%s WHERE id=%s', (nick,username,me['id']))
    conn.commit(); conn.close()
    return jsonify(get_user(me['id']))

@app.route('/api/users/me/link-service', methods=['POST'])
@auth
def link_service(me):
    d = request.json or {}
    service = d.get('service','').strip()
    value   = d.get('value','').strip()
    if not service or not value: return jsonify({'error':'Укажите сервис и значение'}), 400
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT linked_services FROM users WHERE id=%s', (me['id'],))
    u = cur.fetchone()
    services = json.loads(u['linked_services'] or '[]')
    services = [s for s in services if s['service'] != service]
    services.append({'service':service,'value':value})
    cur.execute('UPDATE users SET linked_services=%s WHERE id=%s', (json.dumps(services),me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'user':get_user(me['id'])})

@app.route('/api/users/me/unlink-service', methods=['POST'])
@auth
def unlink_service(me):
    service = (request.json or {}).get('service','')
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT linked_services FROM users WHERE id=%s', (me['id'],))
    u = cur.fetchone()
    services = [s for s in json.loads(u['linked_services'] or '[]') if s['service'] != service]
    cur.execute('UPDATE users SET linked_services=%s WHERE id=%s', (json.dumps(services),me['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'user':get_user(me['id'])})

@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@auth
def admin_action(me, uid):
    if me['role'] not in ('admin','creator'): return jsonify({'error':'Forbidden'}), 403
    target = get_user(uid)
    if not target: return jsonify({'error':'Not found'}), 404
    if target['role']=='creator' and me['role']!='creator': return jsonify({'error':'Нельзя'}), 403
    d = request.json or {}; a = d.get('action')
    conn = get_db(); cur = conn.cursor()
    if   a=='ban':    cur.execute('UPDATE users SET banned=TRUE WHERE id=%s',(uid,))
    elif a=='unban':  cur.execute('UPDATE users SET banned=FALSE WHERE id=%s',(uid,))
    elif a=='mute':   cur.execute('UPDATE users SET muted=TRUE WHERE id=%s',(uid,))
    elif a=='unmute': cur.execute('UPDATE users SET muted=FALSE WHERE id=%s',(uid,))
    elif a=='give_role':
        r = d.get('role')
        if r not in ('user','admin','creator'): conn.close(); return jsonify({'error':'Неверная роль'}), 400
        if r=='creator' and me['role']!='creator': conn.close(); return jsonify({'error':'Только создатель'}), 403
        cur.execute('UPDATE users SET role=%s WHERE id=%s',(r,uid))
    else: conn.close(); return jsonify({'error':'Unknown'}), 400
    conn.commit(); conn.close()
    return jsonify({'ok':True,'user':get_user(uid)})

@app.route('/api/chats')
@auth
def get_chats(me):
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT chat_id FROM chat_members WHERE user_id=%s', (me['id'],))
    ids = [r['chat_id'] for r in cur.fetchall()]; conn.close()
    return jsonify([c for c in [get_chat(cid) for cid in ids] if c])

@app.route('/api/chats', methods=['POST'])
@auth
def create_chat(me):
    d = request.json or {}
    t = d.get('type','group'); name = d.get('name','').strip()
    icon = d.get('icon','').strip() or ('📢' if t=='channel' else '👥')
    if not name: return jsonify({'error':'Укажите название'}), 400
    cid = gid()
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO chats (id,type,name,description,icon,creator_id,pinned,created_at) VALUES (%s,%s,%s,%s,%s,%s,FALSE,%s)',
                (cid,t,name,d.get('description',''),icon,me['id'],now()))
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
    cur.execute('INSERT INTO chats (id,type,name,description,icon,creator_id,pinned,created_at) VALUES (%s,%s,NULL,%s,%s,%s,FALSE,%s)',
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
    cur.execute('DELETE FROM messages WHERE chat_id=%s', (cid,))
    cur.execute('DELETE FROM chat_members WHERE chat_id=%s', (cid,))
    cur.execute('DELETE FROM chats WHERE id=%s', (cid,))
    conn.commit(); conn.close()
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
    cur.execute('DELETE FROM messages WHERE chat_id=%s', (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/messages')
@auth
def get_messages(me, cid):
    if not is_member(me['id'],cid): return jsonify({'error':'Not a member'}), 403
    since = request.args.get('since',0,type=int)
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM messages WHERE chat_id=%s AND timestamp>%s ORDER BY timestamp ASC', (cid,since))
    msgs = cur.fetchall(); conn.close()
    result = []
    for m in msgs:
        d = dict(m); d['system'] = d.pop('is_system',False)
        result.append(d)
    return jsonify(result)

@app.route('/api/chats/<cid>/messages', methods=['POST'])
@auth
def send_message(me, cid):
    if not is_member(me['id'],cid): return jsonify({'error':'Not a member'}), 403
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM chats WHERE id=%s', (cid,))
    c = cur.fetchone(); conn.close()
    if not c: return jsonify({'error':'Chat not found'}), 404
    if c['type']=='channel' and not is_chat_admin(me,cid):
        return jsonify({'error':'Only admins can post'}), 403
    if me.get('muted') and me['role'] not in ('admin','creator'):
        return jsonify({'error':'Вы замьючены'}), 403
    text = (request.json or {}).get('text','').strip()
    if not text: return jsonify({'error':'Empty'}), 400
    if text.startswith('/') and me['role'] in ('admin','creator'):
        return jsonify(handle_cmd(me,cid,text))
    mid = gid()
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO messages (id,chat_id,sender_id,sender_nick,text,is_system,timestamp) VALUES (%s,%s,%s,%s,%s,FALSE,%s)',
                (mid,cid,me['id'],me['nick'],text,now()))
    conn.commit()
    cur.execute('SELECT * FROM messages WHERE id=%s', (mid,))
    msg = dict(cur.fetchone()); conn.close()
    msg['system'] = msg.pop('is_system',False)
    return jsonify(msg)

def handle_cmd(me, cid, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    a1 = parts[1] if len(parts)>1 else None
    a2 = parts[2] if len(parts)>2 else None
    def fu(name):
        if not name: return None
        n = name.lstrip('@')
        conn = get_db(); cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username=%s OR id=%s', (n,n))
        u = cur.fetchone(); conn.close()
        return dict(u) if u else None
    simple = {
        'ban':   ('banned',True, '🔨 @{u} заблокирован'),
        'unban': ('banned',False,'✅ @{u} разблокирован'),
        'mute':  ('muted', True, '🔇 @{u} замьючен'),
        'unmute':('muted', False,'🔊 @{u} размьючен'),
    }
    if cmd in simple:
        t = fu(a1)
        if not t: return {'error':'Не найден'}
        if t['role']=='creator' and me['role']!='creator': return {'error':'Нельзя'}
        field,val,tmpl = simple[cmd]
        conn = get_db(); cur = conn.cursor()
        cur.execute(f'UPDATE users SET {field}=%s WHERE id=%s', (val,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid, tmpl.replace('{u}',t['username']))
        return {'ok':True,'command':cmd}
    if cmd=='give_role':
        t = fu(a1)
        if not t or not a2: return {'error':'Укажи @user и роль'}
        if a2 not in ('user','admin','creator'): return {'error':'user/admin/creator'}
        if a2=='creator' and me['role']!='creator': return {'error':'Только создатель'}
        conn = get_db(); cur = conn.cursor()
        cur.execute('UPDATE users SET role=%s WHERE id=%s', (a2,t['id']))
        conn.commit(); conn.close()
        sys_msg(cid, f'👑 @{t["username"]} → роль: {a2}')
        return {'ok':True,'command':cmd}
    if cmd=='announce':
        sys_msg('community','📢 Объявление: '+' '.join(parts[1:]))
        return {'ok':True,'command':cmd}
    if cmd=='delete_chat':
        target = a1 or cid
        conn = get_db(); cur = conn.cursor()
        cur.execute('DELETE FROM messages WHERE chat_id=%s',(target,))
        cur.execute('DELETE FROM chat_members WHERE chat_id=%s',(target,))
        cur.execute('DELETE FROM chats WHERE id=%s',(target,))
        conn.commit(); conn.close()
        return {'ok':True,'command':cmd,'deleted_chat':target}
    return {'error':f'Неизвестная команда: /{cmd}'}

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

