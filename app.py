import os, json, time, hashlib, secrets, re
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'flux_super_secret_key_2025_bloody')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True)

# ─────────────────────────────────────────────
# JSON хранилище — папка data/ рядом с app.py
# ─────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def _path(name):
    return os.path.join(DATA_DIR, f'{name}.json')

def load(name):
    p = _path(name)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save(name, data):
    with open(_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def hash_pass(p):
    return hashlib.sha256((p + 'flux_salt_2025').encode()).hexdigest()

def gen_id():
    return secrets.token_hex(10)

def now_ms():
    return int(time.time() * 1000)

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        uid = session.get('user_id')
        users = load('users')
        u = users.get(uid)
        if not u:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(u, *args, **kwargs)
    return wrap

def is_online(u):
    return u.get('online') and (now_ms() - u.get('last_seen', 0) < 15000)

def _is_chat_admin(user, chat):
    return (user['role'] in ('admin', 'creator') or
            user['id'] in chat.get('admins', []) or
            user['id'] == chat.get('creator_id'))

def _sys_msg(chat_id, text):
    msgs = load('messages')
    msgs.setdefault(chat_id, [])
    msgs[chat_id].append({
        'id': gen_id(), 'chat_id': chat_id,
        'sender_id': None, 'sender_nick': None,
        'text': text, 'system': True, 'timestamp': now_ms(),
    })
    save('messages', msgs)

# ─────────────────────────────────────────────
# SEED
# ─────────────────────────────────────────────
def seed():
    users = load('users')
    if 'creator_bloody' not in users:
        users['creator_bloody'] = {
            'id': 'creator_bloody',
            'email': 'nexusbloody7@gmail.com',
            'username': 'bloody',
            'nick': 'bloody',
            'password': hash_pass('Zavoz7152'),
            'role': 'creator',
            'avatar': None,
            'banned': False,
            'muted': False,
            'online': False,
            'last_seen': now_ms(),
            'created_at': now_ms(),
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
            'created_at': now_ms(),
        }
        save('chats', chats)
        msgs = load('messages')
        msgs['community'] = [{
            'id': gen_id(), 'chat_id': 'community',
            'sender_id': 'creator_bloody', 'sender_nick': 'bloody',
            'text': '⚡ Добро пожаловать в Flux Community!',
            'system': False, 'timestamp': now_ms(),
        }]
        save('messages', msgs)

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    d = request.json or {}
    email    = d.get('email', '').strip().lower()
    nick     = d.get('nick', '').strip()
    username = re.sub(r'[^a-z0-9_]', '', d.get('username', '').strip().lower())
    password = d.get('password', '')

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

    uid = gen_id()
    users[uid] = {
        'id': uid, 'email': email, 'username': username, 'nick': nick,
        'password': hash_pass(password), 'role': 'user',
        'avatar': None, 'banned': False, 'muted': False,
        'online': True, 'last_seen': now_ms(), 'created_at': now_ms(),
    }
    save('users', users)

    chats = load('chats')
    if 'community' in chats and uid not in chats['community']['members']:
        chats['community']['members'].append(uid)
        save('chats', chats)
        _sys_msg('community', f'👋 @{username} присоединился к Flux Community!')

    session.permanent = True
    session['user_id'] = uid
    out = users[uid].copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})


@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email    = d.get('email', '').strip().lower()
    password = d.get('password', '')

    users = load('users')
    u = next((v for v in users.values() if v['email'] == email), None)
    if not u:
        return jsonify({'error': 'Аккаунт не найден'}), 400
    if u.get('banned'):
        return jsonify({'error': 'Аккаунт заблокирован'}), 403
    if u['password'] != hash_pass(password):
        return jsonify({'error': 'Неверный пароль'}), 400

    u['online'] = True
    u['last_seen'] = now_ms()

    chats = load('chats')
    if 'community' in chats and u['id'] not in chats['community']['members']:
        chats['community']['members'].append(u['id'])
        save('chats', chats)

    save('users', users)
    session.permanent = True
    session['user_id'] = u['id']
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})


@app.route('/api/logout', methods=['POST'])
@login_required
def logout(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = False
        users[me['id']]['last_seen'] = now_ms()
        save('users', users)
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me', methods=['GET'])
@login_required
def get_me(me):
    users = load('users')
    u = users.get(me['id'], me)
    u['online'] = True; u['last_seen'] = now_ms()
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify(out)


@app.route('/api/users/heartbeat', methods=['POST'])
@login_required
def heartbeat(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = True
        users[me['id']]['last_seen'] = now_ms()
        save('users', users)
    return jsonify({'ok': True})


@app.route('/api/users', methods=['GET'])
@login_required
def get_users(me):
    users = load('users')
    result = []
    for u in users.values():
        if u['id'] == me['id']:
            continue
        out = u.copy(); out.pop('password', None)
        out['online'] = is_online(u)
        result.append(out)
    return jsonify(result)


@app.route('/api/users/<uid>', methods=['GET'])
@login_required
def get_user(me, uid):
    users = load('users')
    u = users.get(uid)
    if not u:
        return jsonify({'error': 'Not found'}), 404
    out = u.copy(); out.pop('password', None)
    out['online'] = is_online(u)
    return jsonify(out)


@app.route('/api/users/me/profile', methods=['PUT'])
@login_required
def update_profile(me):
    d = request.json or {}
    nick     = d.get('nick', '').strip()
    username = re.sub(r'[^a-z0-9_]', '', d.get('username', '').strip().lower())
    avatar   = d.get('avatar')

    if not nick or not username:
        return jsonify({'error': 'Заполните поля'}), 400

    users = load('users')
    if any(u['username'] == username and u['id'] != me['id'] for u in users.values()):
        return jsonify({'error': 'Username занят'}), 400

    users[me['id']]['nick']     = nick
    users[me['id']]['username'] = username
    if avatar is not None:
        users[me['id']]['avatar'] = avatar
    save('users', users)

    out = users[me['id']].copy(); out.pop('password', None)
    return jsonify(out)


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────
@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@login_required
def admin_action(me, uid):
    if me['role'] not in ('admin', 'creator'):
        return jsonify({'error': 'Forbidden'}), 403
    users = load('users')
    target = users.get(uid)
    if not target:
        return jsonify({'error': 'Not found'}), 404
    if target['role'] == 'creator' and me['role'] != 'creator':
        return jsonify({'error': 'Cannot modify creator'}), 403

    d = request.json or {}
    action = d.get('action')

    if action == 'ban':      target['banned'] = True
    elif action == 'unban':  target['banned'] = False
    elif action == 'mute':   target['muted']  = True
    elif action == 'unmute': target['muted']  = False
    elif action == 'give_role':
        role = d.get('role')
        if role not in ('user', 'admin', 'creator'):
            return jsonify({'error': 'Invalid role'}), 400
        if role == 'creator' and me['role'] != 'creator':
            return jsonify({'error': 'Only creator can grant creator role'}), 403
        target['role'] = role
    else:
        return jsonify({'error': 'Unknown action'}), 400

    save('users', users)
    out = target.copy(); out.pop('password', None)
    return jsonify({'ok': True, 'user': out})


# ─────────────────────────────────────────────
# CHATS
# ─────────────────────────────────────────────
@app.route('/api/chats', methods=['GET'])
@login_required
def get_chats(me):
    chats = load('chats')
    result = [c for c in chats.values() if me['id'] in c.get('members', [])]
    return jsonify(result)


@app.route('/api/chats', methods=['POST'])
@login_required
def create_chat(me):
    d = request.json or {}
    chat_type = d.get('type', 'group')
    name = d.get('name', '').strip()
    icon = d.get('icon', '').strip() or ('📢' if chat_type == 'channel' else '👥')

    if not name:
        return jsonify({'error': 'Укажите название'}), 400

    cid = gen_id()
    chats = load('chats')
    chats[cid] = {
        'id': cid, 'type': chat_type, 'name': name,
        'description': d.get('description', ''), 'icon': icon,
        'creator_id': me['id'], 'pinned': False,
        'members': [me['id']], 'admins': [me['id']],
        'created_at': now_ms(),
    }
    save('chats', chats)
    _sys_msg(cid, f'{"Канал" if chat_type=="channel" else "Группа"} "{name}" создан(а)')
    return jsonify(chats[cid])


@app.route('/api/chats/dm', methods=['POST'])
@login_required
def create_dm(me):
    d = request.json or {}
    other_id = d.get('user_id')
    users = load('users')
    if other_id not in users:
        return jsonify({'error': 'User not found'}), 404

    chats = load('chats')
    for c in chats.values():
        if c['type'] == 'dm':
            mems = c.get('members', [])
            if me['id'] in mems and other_id in mems:
                return jsonify(c)

    cid = gen_id()
    chats[cid] = {
        'id': cid, 'type': 'dm', 'name': None,
        'description': '', 'icon': '',
        'creator_id': me['id'], 'pinned': False,
        'members': [me['id'], other_id], 'admins': [],
        'created_at': now_ms(),
    }
    save('chats', chats)
    return jsonify(chats[cid])


@app.route('/api/chats/<chat_id>', methods=['PUT'])
@login_required
def update_chat(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not _is_chat_admin(me, c):
        return jsonify({'error': 'Forbidden'}), 403
    d = request.json or {}
    for key in ('name', 'description', 'icon'):
        if key in d: c[key] = d[key]
    save('chats', chats)
    return jsonify(c)


@app.route('/api/chats/<chat_id>', methods=['DELETE'])
@login_required
def delete_chat_route(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['role'] not in ('admin', 'creator') and not _is_chat_admin(me, c):
        return jsonify({'error': 'Forbidden'}), 403
    del chats[chat_id]
    save('chats', chats)
    msgs = load('messages')
    if chat_id in msgs:
        del msgs[chat_id]
        save('messages', msgs)
    return jsonify({'ok': True})


@app.route('/api/chats/<chat_id>/members', methods=['POST'])
@login_required
def add_member(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not _is_chat_admin(me, c):
        return jsonify({'error': 'Forbidden'}), 403
    d = request.json or {}
    uid = d.get('user_id')
    users = load('users')
    u = users.get(uid)
    if not u: return jsonify({'error': 'User not found'}), 404
    if uid not in c['members']:
        c['members'].append(uid)
        save('chats', chats)
        _sys_msg(chat_id, f'➕ @{u["username"]} добавлен в чат')
    return jsonify({'ok': True})


@app.route('/api/chats/<chat_id>/leave', methods=['POST'])
@login_required
def leave_chat(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] in c['members']:
        c['members'].remove(me['id'])
        save('chats', chats)
        _sys_msg(chat_id, f'🚪 @{me["username"]} покинул(а) чат')
    return jsonify({'ok': True})


@app.route('/api/chats/<chat_id>/clear', methods=['POST'])
@login_required
def clear_chat(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if not _is_chat_admin(me, c):
        return jsonify({'error': 'Forbidden'}), 403
    msgs = load('messages')
    msgs[chat_id] = []
    save('messages', msgs)
    return jsonify({'ok': True})


# ─────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────
@app.route('/api/chats/<chat_id>/messages', methods=['GET'])
@login_required
def get_messages(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Not found'}), 404
    if me['id'] not in c.get('members', []):
        return jsonify({'error': 'Not a member'}), 403
    since = request.args.get('since', 0, type=int)
    msgs = load('messages')
    chat_msgs = msgs.get(chat_id, [])
    result = [m for m in chat_msgs if m['timestamp'] > since]
    return jsonify(result)


@app.route('/api/chats/<chat_id>/messages', methods=['POST'])
@login_required
def send_message(me, chat_id):
    chats = load('chats')
    c = chats.get(chat_id)
    if not c: return jsonify({'error': 'Chat not found'}), 404
    if me['id'] not in c.get('members', []):
        return jsonify({'error': 'Not a member'}), 403
    if c['type'] == 'channel' and not _is_chat_admin(me, c):
        return jsonify({'error': 'Only admins can post in channels'}), 403
    if me.get('muted') and me['role'] not in ('admin', 'creator'):
        return jsonify({'error': 'Вы замьючены'}), 403

    d = request.json or {}
    text = d.get('text', '').strip()
    if not text: return jsonify({'error': 'Empty message'}), 400

    if text.startswith('/') and me['role'] in ('admin', 'creator'):
        return jsonify(_handle_cmd(me, chat_id, text))

    msg = {
        'id': gen_id(), 'chat_id': chat_id,
        'sender_id': me['id'], 'sender_nick': me['nick'],
        'text': text, 'system': False, 'timestamp': now_ms(),
    }
    msgs = load('messages')
    msgs.setdefault(chat_id, [])
    msgs[chat_id].append(msg)
    save('messages', msgs)
    return jsonify(msg)


def _handle_cmd(me, chat_id, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    arg1 = parts[1] if len(parts) > 1 else None
    arg2 = parts[2] if len(parts) > 2 else None
    users = load('users')

    def find_user(name):
        if not name: return None, None
        n = name.lstrip('@')
        for uid, u in users.items():
            if u['username'] == n or u['id'] == n:
                return uid, u
        return None, None

    simple = {
        'ban':    ('banned', True,  '🔨 @{u} заблокирован'),
        'unban':  ('banned', False, '✅ @{u} разблокирован'),
        'mute':   ('muted',  True,  '🔇 @{u} замьючен'),
        'unmute': ('muted',  False, '🔊 @{u} размьючен'),
    }

    if cmd in simple:
        uid, target = find_user(arg1)
        if not target: return {'error': 'Пользователь не найден'}
        if target['role'] == 'creator' and me['role'] != 'creator':
            return {'error': 'Нельзя'}
        field, val, tmpl = simple[cmd]
        target[field] = val
        save('users', users)
        _sys_msg(chat_id, tmpl.replace('{u}', target['username']))
        return {'ok': True, 'command': cmd}

    if cmd == 'give_role':
        uid, target = find_user(arg1)
        role = arg2
        if not target or not role:
            return {'error': 'Укажи пользователя и роль'}
        if role not in ('user', 'admin', 'creator'):
            return {'error': 'Роли: user, admin, creator'}
        if role == 'creator' and me['role'] != 'creator':
            return {'error': 'Только создатель может назначать creator'}
        target['role'] = role
        save('users', users)
        _sys_msg(chat_id, f'👑 @{target["username"]} → роль: {role}')
        return {'ok': True, 'command': cmd}

    if cmd == 'announce':
        _sys_msg('community', '📢 Объявление: ' + ' '.join(parts[1:]))
        return {'ok': True, 'command': cmd}

    if cmd == 'delete_chat':
        cid = arg1 or chat_id
        chats = load('chats')
        if cid in chats:
            del chats[cid]; save('chats', chats)
        msgs_d = load('messages')
        if cid in msgs_d:
            del msgs_d[cid]; save('messages', msgs_d)
        return {'ok': True, 'command': cmd, 'deleted_chat': cid}

    return {'error': f'Неизвестная команда: /{cmd}'}


# ─────────────────────────────────────────────
# STATIC
# ─────────────────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, 'index.html')


if __name__ == '__main__':
    seed()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

