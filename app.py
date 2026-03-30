import os, json, time, hashlib, secrets, re
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from datetime import timedelta
from functools import wraps

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'flux_bloody_secret_2025')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
CORS(app, supports_credentials=True, origins='*')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def load(name):
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p): return {}
    try:
        with open(p, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save(name, data):
    with open(os.path.join(DATA_DIR, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def hp(p): return hashlib.sha256((p+'flux_salt_2025').encode()).hexdigest()
def gid(): return secrets.token_hex(10)
def ms(): return int(time.time()*1000)

def auth(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        uid = session.get('uid')
        if not uid: return jsonify({'error':'Unauthorized'}), 401
        u = load('users').get(uid)
        if not u: return jsonify({'error':'Unauthorized'}), 401
        return f(u, *args, **kwargs)
    return wrap

def sys_msg(cid, text):
    msgs = load('messages')
    msgs.setdefault(cid, [])
    msgs[cid].append({'id':gid(),'chat_id':cid,'sender_id':None,'sender_nick':None,'text':text,'system':True,'timestamp':ms()})
    save('messages', msgs)

def is_chat_admin(u, c):
    return u['role'] in ('admin','creator') or u['id'] in c.get('admins',[]) or u['id']==c.get('creator_id')

def seed():
    chats = load('chats')
    if 'community' not in chats:
        chats['community'] = {
            'id':'community','type':'group','name':'Flux Community',
            'description':'Глобальный чат для всех','icon':'⚡',
            'creator_id':None,'pinned':True,'members':[],'admins':[],
            'created_at':ms(),
        }
        save('chats', chats)
        msgs = load('messages')
        msgs['community'] = [{'id':gid(),'chat_id':'community','sender_id':None,'sender_nick':None,'text':'⚡ Добро пожаловать в Flux Community!','system':True,'timestamp':ms()}]
        save('messages', msgs)

# ── REGISTER ───────────────────────────────────────────
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

    users = load('users')
    if any(u['email']==email for u in users.values()):
        return jsonify({'error':'Email уже занят'}), 400
    if any(u['username']==username for u in users.values()):
        return jsonify({'error':'Username уже занят'}), 400

    # username bloody = автоматически creator
    CREATOR_USERNAMES = ['bloody']
    role = 'creator' if username in CREATOR_USERNAMES else 'user'

    uid = gid()
    users[uid] = {
        'id':uid,'email':email,'username':username,'nick':nick,
        'password':hp(password),'role':role,
        'avatar':None,'banned':False,'muted':False,
        'online':True,'last_seen':ms(),'created_at':ms(),
    }
    save('users', users)

    chats = load('chats')
    if 'community' in chats:
        if uid not in chats['community'].get('members',[]):
            chats['community']['members'].append(uid)
        if role == 'creator':
            if uid not in chats['community'].get('admins',[]):
                chats['community']['admins'].append(uid)
            chats['community']['creator_id'] = uid
        save('chats', chats)
    sys_msg('community', f'👋 @{username} присоединился к Flux Community!')

    session.permanent = True
    session['uid'] = uid
    out = users[uid].copy(); out.pop('password', None)
    return jsonify({'ok':True,'user':out})

# ── LOGIN ──────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    password = d.get('password','')

    users = load('users')
    u = next((v for v in users.values() if v['email']==email), None)
    if not u: return jsonify({'error':'Аккаунт не найден'}), 400
    if u.get('banned'): return jsonify({'error':'Аккаунт заблокирован'}), 403
    if u['password'] != hp(password): return jsonify({'error':'Неверный пароль'}), 400

    u['online'] = True
    u['last_seen'] = ms()

    chats = load('chats')
    if 'community' in chats:
        if u['id'] not in chats['community'].get('members',[]):
            chats['community']['members'].append(u['id'])
            save('chats', chats)

    save('users', users)
    session.permanent = True
    session['uid'] = u['id']
    out = u.copy(); out.pop('password', None)
    return jsonify({'ok':True,'user':out})

@app.route('/api/logout', methods=['POST'])
@auth
def logout(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = False
        users[me['id']]['last_seen'] = ms()
        save('users', users)
    session.clear()
    return jsonify({'ok':True})

@app.route('/api/me', methods=['GET'])
@auth
def get_me(me):
    users = load('users')
    u = users.get(me['id'], me)
    u['online'] = True; u['last_seen'] = ms()
    save('users', users)
    out = u.copy(); out.pop('password', None)
    return jsonify(out)

@app.route('/api/users/heartbeat', methods=['POST'])
@auth
def heartbeat(me):
    users = load('users')
    if me['id'] in users:
        users[me['id']]['online'] = True
        users[me['id']]['last_seen'] = ms()
        save('users', users)
    return jsonify({'ok':True})

@app.route('/api/users', methods=['GET'])
@auth
def get_users(me):
    users = load('users')
    result = []
    for u in users.values():
        if u['id'] == me['id']: continue
        out = u.copy(); out.pop('password', None)
        out['online'] = u.get('online') and (ms()-u.get('last_seen',0)<15000)
        result.append(out)
    return jsonify(result)

@app.route('/api/users/<uid>', methods=['GET'])
@auth
def get_user(me, uid):
    u = load('users').get(uid)
    if not u: return jsonify({'error':'Not found'}), 404
    out = u.copy(); out.pop('password', None)
    out['online'] = u.get('online') and (ms()-u.get('last_seen',0)<15000)
    return jsonify(out)

@app.route('/api/users/me/profile', methods=['PUT'])
@auth
def update_profile(me):
    d = request.json or {}
    nick     = d.get('nick','').strip()
    username = re.sub(r'[^a-z0-9_]','', d.get('username','').strip().lower())
    avatar   = d.get('avatar')
    if not nick or not username: return jsonify({'error':'Заполните поля'}), 400
    users = load('users')
    if any(u['username']==username and u['id']!=me['id'] for u in users.values()):
        return jsonify({'error':'Username занят'}), 400
    users[me['id']]['nick'] = nick
    users[me['id']]['username'] = username
    if avatar is not None: users[me['id']]['avatar'] = avatar
    save('users', users)
    out = users[me['id']].copy(); out.pop('password', None)
    return jsonify(out)

@app.route('/api/admin/users/<uid>/action', methods=['POST'])
@auth
def admin_action(me, uid):
    if me['role'] not in ('admin','creator'): return jsonify({'error':'Forbidden'}), 403
    users = load('users')
    t = users.get(uid)
    if not t: return jsonify({'error':'Not found'}), 404
    if t['role']=='creator' and me['role']!='creator': return jsonify({'error':'Нельзя'}), 403
    d = request.json or {}
    a = d.get('action')
    if a=='ban':       t['banned']=True
    elif a=='unban':   t['banned']=False
    elif a=='mute':    t['muted']=True
    elif a=='unmute':  t['muted']=False
    elif a=='give_role':
        r = d.get('role')
        if r not in ('user','admin','creator'): return jsonify({'error':'Неверная роль'}), 400
        if r=='creator' and me['role']!='creator': return jsonify({'error':'Только создатель'}), 403
        t['role']=r
    else: return jsonify({'error':'Unknown'}), 400
    save('users', users)
    out = t.copy(); out.pop('password', None)
    return jsonify({'ok':True,'user':out})

@app.route('/api/chats', methods=['GET'])
@auth
def get_chats(me):
    chats = load('chats')
    return jsonify([c for c in chats.values() if me['id'] in c.get('members',[])])

@app.route('/api/chats', methods=['POST'])
@auth
def create_chat(me):
    d = request.json or {}
    t = d.get('type','group')
    name = d.get('name','').strip()
    icon = d.get('icon','').strip() or ('📢' if t=='channel' else '👥')
    if not name: return jsonify({'error':'Укажите название'}), 400
    cid = gid()
    chats = load('chats')
    chats[cid] = {'id':cid,'type':t,'name':name,'description':d.get('description',''),'icon':icon,'creator_id':me['id'],'pinned':False,'members':[me['id']],'admins':[me['id']],'created_at':ms()}
    save('chats', chats)
    sys_msg(cid, f'{"Канал" if t=="channel" else "Группа"} "{name}" создан(а)')
    return jsonify(chats[cid])

@app.route('/api/chats/dm', methods=['POST'])
@auth
def create_dm(me):
    d = request.json or {}
    oid = d.get('user_id')
    if oid not in load('users'): return jsonify({'error':'User not found'}), 404
    chats = load('chats')
    for c in chats.values():
        if c['type']=='dm' and me['id'] in c.get('members',[]) and oid in c.get('members',[]):
            return jsonify(c)
    cid = gid()
    chats[cid] = {'id':cid,'type':'dm','name':None,'description':'','icon':'','creator_id':me['id'],'pinned':False,'members':[me['id'],oid],'admins':[],'created_at':ms()}
    save('chats', chats)
    return jsonify(chats[cid])

@app.route('/api/chats/<cid>', methods=['PUT'])
@auth
def update_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if not is_chat_admin(me, c): return jsonify({'error':'Forbidden'}), 403
    d = request.json or {}
    for k in ('name','description','icon'):
        if k in d: c[k]=d[k]
    save('chats', chats)
    return jsonify(c)

@app.route('/api/chats/<cid>', methods=['DELETE'])
@auth
def delete_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if me['role'] not in ('admin','creator') and not is_chat_admin(me,c): return jsonify({'error':'Forbidden'}), 403
    del chats[cid]; save('chats', chats)
    msgs = load('messages')
    if cid in msgs: del msgs[cid]; save('messages', msgs)
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/members', methods=['POST'])
@auth
def add_member(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if not is_chat_admin(me,c): return jsonify({'error':'Forbidden'}), 403
    uid = (request.json or {}).get('user_id')
    u = load('users').get(uid)
    if not u: return jsonify({'error':'User not found'}), 404
    if uid not in c['members']:
        c['members'].append(uid); save('chats', chats)
        sys_msg(cid, f'➕ @{u["username"]} добавлен в чат')
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/leave', methods=['POST'])
@auth
def leave_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if me['id'] in c.get('members',[]):
        c['members'].remove(me['id']); save('chats', chats)
        sys_msg(cid, f'🚪 @{me["username"]} покинул(а) чат')
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/clear', methods=['POST'])
@auth
def clear_chat(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if not is_chat_admin(me,c): return jsonify({'error':'Forbidden'}), 403
    msgs = load('messages'); msgs[cid]=[]; save('messages', msgs)
    return jsonify({'ok':True})

@app.route('/api/chats/<cid>/messages', methods=['GET'])
@auth
def get_messages(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Not found'}), 404
    if me['id'] not in c.get('members',[]): return jsonify({'error':'Not a member'}), 403
    since = request.args.get('since', 0, type=int)
    msgs = load('messages')
    return jsonify([m for m in msgs.get(cid,[]) if m['timestamp']>since])

@app.route('/api/chats/<cid>/messages', methods=['POST'])
@auth
def send_message(me, cid):
    chats = load('chats')
    c = chats.get(cid)
    if not c: return jsonify({'error':'Chat not found'}), 404
    if me['id'] not in c.get('members',[]): return jsonify({'error':'Not a member'}), 403
    if c['type']=='channel' and not is_chat_admin(me,c): return jsonify({'error':'Only admins'}), 403
    if me.get('muted') and me['role'] not in ('admin','creator'): return jsonify({'error':'Замьючен'}), 403
    text = (request.json or {}).get('text','').strip()
    if not text: return jsonify({'error':'Empty'}), 400
    if text.startswith('/') and me['role'] in ('admin','creator'):
        return jsonify(handle_cmd(me, cid, text))
    msg = {'id':gid(),'chat_id':cid,'sender_id':me['id'],'sender_nick':me['nick'],'text':text,'system':False,'timestamp':ms()}
    msgs = load('messages'); msgs.setdefault(cid,[]); msgs[cid].append(msg); save('messages', msgs)
    return jsonify(msg)

def handle_cmd(me, cid, text):
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ''
    a1 = parts[1] if len(parts)>1 else None
    a2 = parts[2] if len(parts)>2 else None
    users = load('users')
    def fu(n):
        if not n: return None,None
        n=n.lstrip('@')
        for uid,u in users.items():
            if u['username']==n or u['id']==n: return uid,u
        return None,None
    simple={'ban':('banned',True,'🔨 @{u} заблокирован'),'unban':('banned',False,'✅ @{u} разблокирован'),'mute':('muted',True,'🔇 @{u} замьючен'),'unmute':('muted',False,'🔊 @{u} размьючен')}
    if cmd in simple:
        uid,t=fu(a1)
        if not t: return {'error':'Не найден'}
        if t['role']=='creator' and me['role']!='creator': return {'error':'Нельзя'}
        f,v,tmpl=simple[cmd]; t[f]=v; save('users',users)
        sys_msg(cid,tmpl.replace('{u}',t['username']))
        return {'ok':True,'command':cmd}
    if cmd=='give_role':
        uid,t=fu(a1)
        if not t or not a2: return {'error':'Укажи user и роль'}
        if a2 not in ('user','admin','creator'): return {'error':'user/admin/creator'}
        if a2=='creator' and me['role']!='creator': return {'error':'Только создатель'}
        t['role']=a2; save('users',users); sys_msg(cid,f'👑 @{t["username"]} → {a2}')
        return {'ok':True,'command':cmd}
    if cmd=='announce':
        sys_msg('community','📢 '+' '.join(parts[1:]))
        return {'ok':True,'command':cmd}
    if cmd=='delete_chat':
        target=a1 or cid
        chats=load('chats')
        if target in chats: del chats[target]; save('chats',chats)
        msgs=load('messages')
        if target in msgs: del msgs[target]; save('messages',msgs)
        return {'ok':True,'command':cmd,'deleted_chat':target}
    return {'error':f'Неизвестная команда: /{cmd}'}

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    if path and os.path.exists(os.path.join(sd,path)): return send_from_directory(sd,path)
    return send_from_directory(sd,'index.html')

if __name__ == '__main__':
    seed()
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0', port=port, debug=False)

