import os, json, time, hashlib, secrets, re
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'flux_secret_bloody_2025_xkq9')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
CORS(app, supports_credentials=True, origins='*')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
os.makedirs(DATA, exist_ok=True)

def load(name):
    p = os.path.join(DATA, name + '.json')
    if not os.path.exists(p): return {}
    try:
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save(name, data):
    with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def hp(p): return hashlib.sha256((p + 'flux_salt_2025').encode()).hexdigest()
def gid(): return secrets.token_hex(10)
def now(): return int(time.time() * 1000)
def flux_id(): return 'FLX-' + secrets.token_hex(4).upper()

def auth(f):
    @wraps(f)
    def w(*a, **kw):
        uid = session.get('uid')
        if not uid: return jsonify({'error': 'Unauthorized'}), 401
        u = load('users').get(uid)
        if not u: return jsonify({'error': 'Unauthorized'}), 401
        return f(u, *a, **kw)
    return w

def sys_msg(cid, text):
    msgs = load('messages')
    msgs.setdefault(cid, []).append({
        'id': gid(), 'chat_id': cid, 'sender_id': None,
        'sender_nick': None, 'text': text, 'system': True, 'timestamp': now()
    })
    save('messages', msgs)

def chat_admin(u, c):
    return (u['role'] in ('admin','creator') or
            u['id'] in c.get('admins',[]) or
            u['id'] == c.get('creator_id'))

def is_online(u):
    return bool(u.get('online') and now() - u.get('last_seen',0) < 15000)

def seed():
    chats = load('chats')
    if 'community' not in chats:
        chats['community'] = {
            'id': 'community', 'type': 'group',
            'name': 'Flux Community', 'description': 'Глобальный чат для всех',
            'icon': '⚡', 'creator_id': None, 'pinned': True,
            'members': [], 'admins': [], 'created_at': now()
        }
        save('chats', chats)
        msgs = load('messages')
        msgs['community'] = [{
            'id': gid(), 'chat_id': 'community', 'sender_id': None,
            'sender_nick': None, 'text': '⚡ Добро пожаловать в Flux Community!',
            'system': True, 'timestamp': now()
        }]
        save('messages', msgs)

# ── RESET BLOODY (временный роут для сброса) ──
@app.route('/api/reset-bloody')
def reset_bloody():
    users = load('users')
    deleted = [uid for uid,u in list(users.items()) if u.get('username') == 'bloody']
    for uid in deleted: del users[uid]
    save('users', users)
    chats = load('chats')
    for c in chats.values():
        c['members'] = [m for m in c.get('members',[]) if m not in deleted]
        c['admins']  = [m for m in c.get('admins',[])  if m not in deleted]
        if c.get('creator_id') in deleted: c['creator_id'] = None
    save('chats', chats)
    return jsonify({'ok': True, 'deleted': deleted})

# ── REGISTER ──
@app.route('/api/register', methods=['POST'])
def register():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    password = d.get('password','')

    if not all([email, nick, username, password]):
        return jsonify({'error': 'Заполните все поля'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль минимум 6 символов'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Username минимум 3 символа'}), 400

    users = load('users')
    if any(u['email'] == email for u in users.values()):
        return jsonify({'error': 'Email уже занят'}), 400
    if any(u['username'] == username for u in users.values()):
        return jsonify({'error': 'Username уже занят'}), 400

    role = 'creator' if username == 'bloody' else 'user'
    uid  = gid()
    fid  = flux_id()

    users[uid] = {
        'id': uid, 'flux_id': fid,
        'email': email, 'username': username, 'nick': nick,
        'password': hp(password), 'role': role, 'avatar': None,
        'banned': False, 'muted': False,
        'online': True, 'last_seen': now(), 'created_at': now(),
        'linked_services': []
    }
    save('users', users)

    chats = load('chats')
    comm  = chats.get('community', {})
    if uid not in comm.get('members', []):
        comm.setdefault('members', []).append(uid)
    if role == 'creator':
        if uid not in comm.get('admins', []):
            comm.setdefault('admins', []).append(uid)
        comm['creator_id'] = uid
    chats['community'] = comm
    save('chats', chats)
    sys_msg('community', f'👋 @{username} присоединился к Flux Community!')

    session.permanent = True
    session['uid'] = uid
    out = users[uid].copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── LOGIN ──
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    password = d.get('password','')

    users = load('users')
    uid = next((k for k,v in users.items() if v['email'] == email), None)
    if not uid: return jsonify({'error': 'Аккаунт не найден'}), 400
    u = users[uid]
    if u.get('banned'): return jsonify({'error': 'Аккаунт заблокирован'}), 403
    if u['password'] != hp(password): return jsonify({'error': 'Неверный пароль'}), 400

    u['online'] = True
    u['last_seen'] = now()
    if not u.get('flux_id'): u['flux_id'] = flux_id()
    if 'linked_services' not in u: u['linked_services'] = []

    chats = load('chats')
    comm = chats.get('community', {})
    if uid not in comm.get('members', []):
        comm.setdefault('members', []).append(uid)
        chats['community'] = comm
        save('chats', chats)

    save('users', users)
    session.permanent = True
    session['uid'] = uid
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

@app.route('/api/logout', methods=['POST'])
@auth
def logout(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = False
        users[me['id']]['last_seen'] = now()
        save('users', users)
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me')
@auth
def get_me(me):
    users = load('users')
    u = users.get(me['id'], me)
    u['online'] = True; u['last_seen'] = now()
    if not u.get('flux_id'): u['flux_id'] = flux_id()
    if 'linked_services' not in u: u['linked_services'] = []
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify(out)

@app.route('/api/users/heartbeat', methods=['POST'])
@auth
def heartbeat(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = True
        users[me['id']]['last_seen'] = now()
        save('users', users)
    return jsonify({'ok': True})

@app.route('/api/users')
@auth
def get_users(me):
    result = []
    for u in load('users').values():
        if u['id'] == me['id']: continue
        out = u.copy(); out.pop('password', None)
        out['online'] = is_online(u)
        result.append(out)
    return jsonify(result)

@app.route('/api/users/<uid>')
@auth
def get_user(me, uid):
    u = load('users').get(uid)
    if not u: return jsonify({'error': 'Not found'}), 404
    out = u.copy(); out.pop('password', None)
    out['online'] = is_online(u)
    return jsonify(out)

@app.route('/api/users/me/profile', methods=['PUT'])
@auth
def update_profile(me):
    d = request.json or {}
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    avatar   = d.get('avatar')
    if not nick or not username:
        return jsonify({'error': 'Заполните поля'}), 400
    users = load('users')
    if any(u['username'] == username and u['id'] != me['id'] for u in users.values()):
        return jsonify({'error': 'Username занят'}), 400
    users[me['id']]['nick'] = nick
    users[me['id']]['username'] = username
    if avatar is not None: users[me['id']]['avatar'] = avatar
    save('users', users)
    out = users[me['id']].copy(); out.pop('password', None)
    return jsonify(out)

# ── LINK SERVICE ──
@app.route('/api/users/me/link-service', methods=['POST'])
@auth
def link_service(me):
    d = request.json or {}
    service = d.get('service','').strip()
    value   = d.get('value','').strip()
    if not service or not value:
        return jsonify({'error': 'Укажите сервис и значение'}), 400
    users = load('users')
    u = users[me['id']]
    services = u.get('linked_services', [])
    services = [s for s in services if s['service'] != service]
    services.append({'service': service, 'value': value})
    u['linked_services'] = services
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

@app.route('/api/users/me/unlink-service', methods=['POST'])
@auth
def unlink_service(me):
    service = (request.json or {}).get('service','')
    users = load('users')
    u = users[me['id']]
    u['linked_services'] = [s for s in u.get('linked_services',[]) if s['service'] != service]
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── ADMIN ──
@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@auth
def admin_action(me, uid):
    if me['role'] not in ('admin','creator'):
        return jsonify({'error': 'Forbidden'}), 403
    users = load('users')
    t = users.get(uid)
    if not t: return jsonify({'error': 'Not found'}), 404
    if t['role'] == 'creator' and me['role'] != 'creator':
        return jsonify({'error': 'Нельзя'}), 403
    d = request.json or {}
    a = d.get('action')
    if   a == 'ban':    t['banned'] = True
    elif a == 'unban':  t['banned'] = False
    elif a == 'mute':   t['muted']  = True
    elif a == 'unmute': t['muted']  = False
    elif a == 'give_role':
        r = d.get('role')
        if r not in ('user','admin','creator'):
            return jsonify({'error': 'Неверная роль'}), 400
        if r == 'creator' and me['role'] != 'creator':
            return jsonify({'error': 'Только создатель'}), 403
        t['role'] = r
    else: return jsonify({'error': 'Unknown action'}), 400
    save('users', users)
    out = t.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── CHATS ──
@app.route('/api/chats')
@auth
def get_chats(me):
    return jsonify([c for c in load('chats').values() if me['id'] in c.get('members',[])])

@app.route('/api/chats', methods=['POST'])
@auth
def create_chat(me):
    d = request.json or {}
    t    = d.get('type','group')
    name = d.get('name','').strip()
    icon = d.get('icon','').strip() or ('📢' if t == 'channel' else '👥')
    if not name: return jsonify({'error': 'Укажите название'}), 400
    cid = gid()
    chats = load('chats')
    chats[cid] = {
        'id': cid, 'type': t, 'name': name,
        'description': d.get('description',''), 'icon': icon,
        'creator_id': me['id'], 'pinned': False,
        'members': [me['id']], 'admins': [me['id']], 'created_at': now()
    }
    save('chats', chats)
    sys_msg(cid, f'{"Канал" if t=="channel" else "Группа"} "{name}" создан(а)')
    return jsonify(chats[cid])

@app.route('/api/chats/dm', methods=['POST'])
@auth
def create_dm(me):
    oid = (request.json or {}).get('user_id')
    if not load('users').get(oid):
        return jsonify({'error': 'User not found'}), 404
    chats = load('chats')
    for c in chats.values():
        if c['type'] == 'dm' and set(c.get('members',[])) == {me['id'], oid}:
            return jsonify(c)
    cid = gid()
    chats[cid] = {
        'id': cid, 'type': 'dm', 'name': None, 'description': '',
        'icon': '', 'creator_id': me['id'], 'pinned': False,
        'members': [me['id'], oid], 'admins': [], 'created_at': now()
    }
    save('chats', chats)
    return jsonify(chats[cid])

@app.route('/api/chats/<cid>', methods=['PUT'])
@auth
def update_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not chat_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    for k in ('name','description','icon'):
        if k in (request.json or {}): c[k] = request.json[k]
    save('chats', chats)
    return jsonify(c)

@app.route('/api/chats/<cid>', methods=['DELETE'])
@auth
def delete_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['role'] not in ('admin','creator') and not chat_admin(me,c):
        return jsonify({'error': 'Forbidden'}), 403
    del chats[cid]; save('chats', chats)
    msgs = load('messages')
    if cid in msgs: del msgs[cid]; save('messages', msgs)
    return jsonify({'ok': True})

@app.route('/api/chats/<cid>/members', methods=['POST'])
@auth
def add_member(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not chat_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    uid = (request.json or {}).get('user_id')
    u = load('users').get(uid)
    if not u: return jsonify({'error': 'User not found'}), 404
    if uid not in c['members']:
        c['members'].append(uid); save('chats', chats)
        sys_msg(cid, f'➕ @{u["username"]} добавлен в чат')
    return jsonify({'ok': True})

@app.route('/api/chats/<cid>/leave', methods=['POST'])
@auth
def leave_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] in c.get('members', []):
        c['members'].remove(me['id']); save('chats', chats)
        sys_msg(cid, f'🚪 @{me["username"]} покинул(а) чат')
    return jsonify({'ok': True})

@app.route('/api/chats/<cid>/clear', methods=['POST'])
@auth
def clear_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not chat_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    msgs = load('messages'); msgs[cid] = []; save('messages', msgs)
    return jsonify({'ok': True})

# ── MESSAGES ──
@app.route('/api/chats/<cid>/messages')
@auth
def get_messages(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] not in c.get('members', []):
        return jsonify({'error': 'Not a member'}), 403
    since = request.args.get('since', 0, type=int)
    return jsonify([m for m in load('messages').get(cid,[]) if m['timestamp'] > since])

@app.route('/api/chats/<cid>/messages', methods=['POST'])
@auth
def send_message(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Chat not found'}), 404
    if me['id'] not in c.get('members', []):
        return jsonify({'error': 'Not a member'}), 403
    if c['type'] == 'channel' and not chat_admin(me, c):
        return jsonify({'error': 'Only admins can post'}), 403
    if me.get('muted') and me['role'] not in ('admin','creator'):
        return jsonify({'error': 'Вы замьючены'}), 403
    text = (request.json or {}).get('text','').strip()
    if not text: return jsonify({'error': 'Empty'}), 400
    if text.startswith('/') and me['role'] in ('admin','creator'):
        return jsonify(handle_cmd(me, cid, text))
    msg = {
        'id': gid(), 'chat_id': cid,
        'sender_id': me['id'], 'sender_nick': me['nick'],
        'text': text, 'system': False, 'timestamp': now()
    }
    msgs = load('messages')
    msgs.setdefault(cid, []).append(msg)
    save('messages', msgs)
    return jsonify(msg)

def handle_cmd(me, cid, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    a1 = parts[1] if len(parts) > 1 else None
    a2 = parts[2] if len(parts) > 2 else None
    users = load('users')

    def fu(name):
        if not name: return None, None
        n = name.lstrip('@')
        for k,v in users.items():
            if v['username'] == n or v['id'] == n: return k, v
        return None, None

    simple = {
        'ban':    ('banned', True,  '🔨 @{u} заблокирован'),
        'unban':  ('banned', False, '✅ @{u} разблокирован'),
        'mute':   ('muted',  True,  '🔇 @{u} замьючен'),
        'unmute': ('muted',  False, '🔊 @{u} размьючен'),
    }
    if cmd in simple:
        uid, t = fu(a1)
        if not t: return {'error': 'Не найден'}
        if t['role'] == 'creator' and me['role'] != 'creator': return {'error': 'Нельзя'}
        f, v, tmpl = simple[cmd]; t[f] = v; save('users', users)
        sys_msg(cid, tmpl.replace('{u}', t['username']))
        return {'ok': True, 'command': cmd}

    if cmd == 'give_role':
        uid, t = fu(a1)
        if not t or not a2: return {'error': 'Укажи @user и роль'}
        if a2 not in ('user','admin','creator'): return {'error': 'user/admin/creator'}
        if a2 == 'creator' and me['role'] != 'creator': return {'error': 'Только создатель'}
        t['role'] = a2; save('users', users)
        sys_msg(cid, f'👑 @{t["username"]} → роль: {a2}')
        return {'ok': True, 'command': cmd}

    if cmd == 'announce':
        sys_msg('community', '📢 Объявление: ' + ' '.join(parts[1:]))
        return {'ok': True, 'command': cmd}

    if cmd == 'delete_chat':
        target = a1 or cid
        chats = load('chats')
        if target in chats: del chats[target]; save('chats', chats)
        msgs = load('messages')
        if target in msgs: del msgs[target]; save('messages', msgs)
        return {'ok': True, 'command': cmd, 'deleted_chat': target}

    return {'error': f'Неизвестная команда: /{cmd}'}

# ── STATIC ──
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    sd = os.path.join(BASE, 'static')
    if path and os.path.exists(os.path.join(sd, path)):
        return send_from_directory(sd, path)
    return send_from_directory(sd, 'index.html')

if __name__ == '__main__':
    seed()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

