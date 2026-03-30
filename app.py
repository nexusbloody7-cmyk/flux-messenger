import os, json, time, hashlib, secrets, re
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'flux_bloody_secret_2025')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
CORS(app, supports_credentials=True, origins='*')

# ── ХРАНИЛИЩЕ ──────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def load(name):
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save(name, data):
    p = os.path.join(DATA_DIR, f'{name}.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def hp(p):
    return hashlib.sha256((p + 'flux_salt_2025').encode()).hexdigest()

def gid():
    return secrets.token_hex(10)

def ms():
    return int(time.time() * 1000)

# ── AUTH ДЕКОРАТОР ─────────────────────────────────────
def auth(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        uid = session.get('uid')
        if not uid:
            return jsonify({'error': 'Unauthorized'}), 401
        users = load('users')
        u = users.get(uid)
        if not u:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(u, *args, **kwargs)
    return wrap

def sys_msg(chat_id, text):
    msgs = load('messages')
    msgs.setdefault(chat_id, [])
    msgs[chat_id].append({
        'id': gid(), 'chat_id': chat_id,
        'sender_id': None, 'sender_nick': None,
        'text': text, 'system': True, 'timestamp': ms()
    })
    save('messages', msgs)

def is_admin(user, chat):
    return (user['role'] in ('admin','creator') or
            user['id'] in chat.get('admins',[]) or
            user['id'] == chat.get('creator_id'))

# ── SEED ───────────────────────────────────────────────
def seed():
    users = load('users')
    if 'creator_bloody' not in users:
        users['creator_bloody'] = {
            'id': 'creator_bloody',
            'email': 'nexusbloody7@gmail.com',
            'username': 'bloody',
            'nick': 'bloody',
            'password': hp('Zavoz7152'),
            'role': 'creator',
            'avatar': None,
            'banned': False,
            'muted': False,
            'online': False,
            'last_seen': ms(),
            'created_at': ms(),
        }
        save('users', users)

    chats = load('chats')
    if 'community' not in chats:
        chats['community'] = {
            'id': 'community',
            'type': 'group',
            'name': 'Flux Community',
            'description': 'Глобальный чат для всех',
            'icon': '⚡',
            'creator_id': 'creator_bloody',
            'pinned': True,
            'members': ['creator_bloody'],
            'admins': ['creator_bloody'],
            'created_at': ms(),
        }
        save('chats', chats)
        msgs = load('messages')
        msgs['community'] = [{
            'id': gid(), 'chat_id': 'community',
            'sender_id': 'creator_bloody', 'sender_nick': 'bloody',
            'text': '⚡ Добро пожаловать в Flux Community!',
            'system': False, 'timestamp': ms()
        }]
        save('messages', msgs)
    else:
        # Убедимся что bloody всегда в community
        if 'creator_bloody' not in chats['community'].get('members', []):
            chats['community'].setdefault('members', []).append('creator_bloody')
            save('chats', chats)

# ── REGISTER ───────────────────────────────────────────
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

    uid = gid()
    users[uid] = {
        'id': uid, 'email': email, 'username': username, 'nick': nick,
        'password': hp(password), 'role': 'user',
        'avatar': None, 'banned': False, 'muted': False,
        'online': True, 'last_seen': ms(), 'created_at': ms(),
    }
    save('users', users)

    # Добавить в community
    chats = load('chats')
    if 'community' in chats:
        if uid not in chats['community'].get('members', []):
            chats['community'].setdefault('members', []).append(uid)
            save('chats', chats)
        sys_msg('community', f'👋 @{username} присоединился к Flux Community!')

    session.permanent = True
    session['uid'] = uid
    out = users[uid].copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── LOGIN ──────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    password = d.get('password','')

    users = load('users')
    u = next((v for v in users.values() if v['email'] == email), None)
    if not u:
        return jsonify({'error': 'Аккаунт не найден'}), 400
    if u.get('banned'):
        return jsonify({'error': 'Аккаунт заблокирован'}), 403
    if u['password'] != hp(password):
        return jsonify({'error': 'Неверный пароль'}), 400

    u['online'] = True
    u['last_seen'] = ms()

    # Убедиться что в community
    chats = load('chats')
    if 'community' in chats:
        if u['id'] not in chats['community'].get('members', []):
            chats['community'].setdefault('members', []).append(u['id'])
            save('chats', chats)

    save('users', users)
    session.permanent = True
    session['uid'] = u['id']
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── LOGOUT ─────────────────────────────────────────────
@app.route('/api/logout', methods=['POST'])
@auth
def logout(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = False
        users[me['id']]['last_seen'] = ms()
        save('users', users)
    session.clear()
    return jsonify({'ok': True})

# ── ME ─────────────────────────────────────────────────
@app.route('/api/me', methods=['GET'])
@auth
def get_me(me):
    users = load('users')
    u = users.get(me['id'], me)
    u['online'] = True
    u['last_seen'] = ms()
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify(out)

# ── HEARTBEAT ──────────────────────────────────────────
@app.route('/api/users/heartbeat', methods=['POST'])
@auth
def heartbeat(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = True
        users[me['id']]['last_seen'] = ms()
        save('users', users)
    return jsonify({'ok': True})

# ── USERS ──────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@auth
def get_users(me):
    users = load('users')
    result = []
    for u in users.values():
        if u['id'] == me['id']:
            continue
        out = u.copy(); out.pop('password', None)
        out['online'] = u.get('online') and (ms() - u.get('last_seen',0) < 15000)
        result.append(out)
    return jsonify(result)

@app.route('/api/users/<uid>', methods=['GET'])
@auth
def get_user(me, uid):
    users = load('users')
    u = users.get(uid)
    if not u:
        return jsonify({'error': 'Not found'}), 404
    out = u.copy(); out.pop('password', None)
    out['online'] = u.get('online') and (ms() - u.get('last_seen',0) < 15000)
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
    if any(u['username']==username and u['id']!=me['id'] for u in users.values()):
        return jsonify({'error': 'Username занят'}), 400
    users[me['id']]['nick'] = nick
    users[me['id']]['username'] = username
    if avatar is not None:
        users[me['id']]['avatar'] = avatar
    save('users', users)
    out = users[me['id']].copy(); out.pop('password', None)
    return jsonify(out)

# ── ADMIN ──────────────────────────────────────────────
@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@auth
def admin_action(me, uid):
    if me['role'] not in ('admin','creator'):
        return jsonify({'error': 'Forbidden'}), 403
    users = load('users')
    t = users.get(uid)
    if not t:
        return jsonify({'error': 'Not found'}), 404
    if t['role'] == 'creator' and me['role'] != 'creator':
        return jsonify({'error': 'Нельзя'}), 403
    d = request.json or {}
    a = d.get('action')
    if a == 'ban':        t['banned'] = True
    elif a == 'unban':    t['banned'] = False
    elif a == 'mute':     t['muted']  = True
    elif a == 'unmute':   t['muted']  = False
    elif a == 'give_role':
        r = d.get('role')
        if r not in ('user','admin','creator'):
            return jsonify({'error': 'Неверная роль'}), 400
        if r == 'creator' and me['role'] != 'creator':
            return jsonify({'error': 'Только создатель'}), 403
        t['role'] = r
    else:
        return jsonify({'error': 'Unknown action'}), 400
    save('users', users)
    out = t.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})

# ── CHATS ──────────────────────────────────────────────
@app.route('/api/chats', methods=['GET'])
@auth
def get_chats(me):
    chats = load('chats')
    result = [c for c in chats.values() if me['id'] in c.get('members',[])]
    return jsonify(result)

@app.route('/api/chats', methods=['POST'])
@auth
def create_chat(me):
    d = request.json or {}
    t    = d.get('type','group')
    name = d.get('name','').strip()
    icon = d.get('icon','').strip() or ('📢' if t=='channel' else '👥')
    if not name:
        return jsonify({'error': 'Укажите название'}), 400
    cid = gid()
    chats = load('chats')
    chats[cid] = {
        'id': cid, 'type': t, 'name': name,
        'description': d.get('description',''), 'icon': icon,
        'creator_id': me['id'], 'pinned': False,
        'members': [me['id']], 'admins': [me['id']],
        'created_at': ms(),
    }
    save('chats', chats)
    sys_msg(cid, f'{"Канал" if t=="channel" else "Группа"} "{name}" создан(а)')
    return jsonify(chats[cid])

@app.route('/api/chats/dm', methods=['POST'])
@auth
def create_dm(me):
    d = request.json or {}
    oid = d.get('user_id')
    users = load('users')
    if oid not in users:
        return jsonify({'error': 'User not found'}), 404
    chats = load('chats')
    for c in chats.values():
        if c['type'] == 'dm':
            m = c.get('members',[])
            if me['id'] in m and oid in m:
                return jsonify(c)
    cid = gid()
    chats[cid] = {
        'id': cid, 'type': 'dm', 'name': None,
        'description': '', 'icon': '',
        'creator_id': me['id'], 'pinned': False,
        'members': [me['id'], oid], 'admins': [],
        'created_at': ms(),
    }
    save('chats', chats)
    return jsonify(chats[cid])

@app.route('/api/chats/<cid>', methods=['PUT'])
@auth
def update_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not is_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    d = request.json or {}
    for k in ('name','description','icon'):
        if k in d: c[k] = d[k]
    save('chats', chats)
    return jsonify(c)

@app.route('/api/chats/<cid>', methods=['DELETE'])
@auth
def delete_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['role'] not in ('admin','creator') and not is_admin(me, c):
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
    if not is_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    d = request.json or {}
    uid = d.get('user_id')
    users = load('users')
    u = users.get(uid)
    if not u: return jsonify({'error': 'User not found'}), 404
    if uid not in c['members']:
        c['members'].append(uid)
        save('chats', chats)
        sys_msg(cid, f'➕ @{u["username"]} добавлен в чат')
    return jsonify({'ok': True})

@app.route('/api/chats/<cid>/leave', methods=['POST'])
@auth
def leave_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] in c.get('members',[]):
        c['members'].remove(me['id'])
        save('chats', chats)
        sys_msg(cid, f'🚪 @{me["username"]} покинул(а) чат')
    return jsonify({'ok': True})

@app.route('/api/chats/<cid>/clear', methods=['POST'])
@auth
def clear_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not is_admin(me, c): return jsonify({'error': 'Forbidden'}), 403
    msgs = load('messages')
    msgs[cid] = []
    save('messages', msgs)
    return jsonify({'ok': True})

# ── MESSAGES ───────────────────────────────────────────
@app.route('/api/chats/<cid>/messages', methods=['GET'])
@auth
def get_messages(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] not in c.get('members',[]):
        return jsonify({'error': 'Not a member'}), 403
    since = request.args.get('since', 0, type=int)
    msgs = load('messages')
    result = [m for m in msgs.get(cid,[]) if m['timestamp'] > since]
    return jsonify(result)

@app.route('/api/chats/<cid>/messages', methods=['POST'])
@auth
def send_message(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error': 'Chat not found'}), 404
    if me['id'] not in c.get('members',[]):
        return jsonify({'error': 'Not a member'}), 403
    if c['type'] == 'channel' and not is_admin(me, c):
        return jsonify({'error': 'Only admins can post'}), 403
    if me.get('muted') and me['role'] not in ('admin','creator'):
        return jsonify({'error': 'Вы замьючены'}), 403

    d = request.json or {}
    text = d.get('text','').strip()
    if not text: return jsonify({'error': 'Empty'}), 400

    # Команды
    if text.startswith('/') and me['role'] in ('admin','creator'):
        return jsonify(handle_cmd(me, cid, text))

    msg = {
        'id': gid(), 'chat_id': cid,
        'sender_id': me['id'], 'sender_nick': me['nick'],
        'text': text, 'system': False, 'timestamp': ms()
    }
    msgs = load('messages')
    msgs.setdefault(cid, [])
    msgs[cid].append(msg)
    save('messages', msgs)
    return jsonify(msg)

def handle_cmd(me, cid, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    a1 = parts[1] if len(parts)>1 else None
    a2 = parts[2] if len(parts)>2 else None
    users = load('users')

    def fu(name):
        if not name: return None, None
        n = name.lstrip('@')
        for uid,u in users.items():
            if u['username']==n or u['id']==n: return uid,u
        return None, None

    simple = {
        'ban':    ('banned',True, '🔨 @{u} заблокирован'),
        'unban':  ('banned',False,'✅ @{u} разблокирован'),
        'mute':   ('muted', True, '🔇 @{u} замьючен'),
        'unmute': ('muted', False,'🔊 @{u} размьючен'),
    }
    if cmd in simple:
        uid,t = fu(a1)
        if not t: return {'error':'Не найден'}
        if t['role']=='creator' and me['role']!='creator': return {'error':'Нельзя'}
        f,v,tmpl = simple[cmd]
        t[f]=v; save('users',users)
        sys_msg(cid, tmpl.replace('{u}',t['username']))
        return {'ok':True,'command':cmd}

    if cmd == 'give_role':
        uid,t = fu(a1)
        if not t or not a2: return {'error':'Укажи user и роль'}
        if a2 not in ('user','admin','creator'): return {'error':'user/admin/creator'}
        if a2=='creator' and me['role']!='creator': return {'error':'Только создатель'}
        t['role']=a2; save('users',users)
        sys_msg(cid, f'👑 @{t["username"]} → {a2}')
        return {'ok':True,'command':cmd}

    if cmd == 'announce':
        sys_msg('community','📢 '+' '.join(parts[1:]))
        return {'ok':True,'command':cmd}

    if cmd == 'delete_chat':
        target = a1 or cid
        chats = load('chats')
        if target in chats: del chats[target]; save('chats',chats)
        msgs = load('messages')
        if target in msgs: del msgs[target]; save('messages',msgs)
        return {'ok':True,'command':cmd,'deleted_chat':target}

    return {'error':f'Неизвестная команда: /{cmd}'}

# ── STATIC ─────────────────────────────────────────────
@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if path and os.path.exists(os.path.join(sd, path)):
        return send_from_directory(sd, path)
    return send_from_directory(sd, 'index.html')

# ── MAIN ───────────────────────────────────────────────
if __name__ == '__main__':
    seed()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

