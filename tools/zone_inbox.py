# Odpovědi klientů ze zón (pořadí videí, potvrzení / jiný termín natáčení), které zóna uloží napřímo.
# Zóna je zašifruje klíčem klienta a pošle do Google formuláře „CRM – zápis ze zón“; odpovědi jsou v tabulce
# „CRM – zápis ze zón (odpovědi)“ (cakl.solutions@gmail.com, list „Odpovědi formuláře 1“, sloupec B = <slug>.<data>).
#
# python3 tools/zone_inbox.py <crm_data.json> <rows.json> [--edits edits.json]           → vypíše, co by se změnilo
# python3 tools/zone_inbox.py <crm_data.json> <rows.json> [--edits edits.json] --apply   → zapíše do crm_data.json
#   rows.json = výstup Google Sheets get_values (objekt s "values") nebo rovnou seznam řádků.
# Výstup: JSON {"applied":[{c,kind,msg}], "info":[...], "bad":N}. Zpracovaná id jdou do zoneDone (nic se nepromítne dvakrát).
# Podvržený nebo poškozený řádek se nedá dešifrovat klíčem klienta, takže se ignoruje. Klíče nikdy nevypisuj.
import json, sys, base64, hashlib, datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

argv = sys.argv[1:]
apply = '--apply' in argv
if apply: argv.remove('--apply')
edits = {}
if '--edits' in argv:
    i = argv.index('--edits')
    try: edits = json.load(open(argv[i + 1])) or {}
    except Exception: edits = {}
    del argv[i:i + 2]
path, rows_f = argv[0], argv[1]
d = json.load(open(path))
rows = json.load(open(rows_f))
if isinstance(rows, dict): rows = rows.get('values') or []

def b64u(s): return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
by_slug = {}
for c in d['clients']:
    w = c.get('web') or {}
    if w.get('slug') and w.get('key'): by_slug[w['slug']] = (c, AESGCM(b64u(w['key'])))

today = datetime.date.today().isoformat()
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
done = list(d.get('zoneDone') or [])
d.setdefault('shoots', []); d.setdefault('shootsOff', []); d.setdefault('asks', [])
DN = ['pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle']
def when(dt, tm):
    try: x = datetime.date.fromisoformat(dt); s = f"{DN[x.weekday()]} {x.day}. {x.month}."
    except Exception: s = dt
    return s + (f" v {tm}" if tm else '')
def nick(c): return c.get('nick') or c['name'].split(' ')[0]
def ask_key(a): return a.get('u') or (a.get('date', '') + '|' + (a.get('time') or ''))
def current_ask(cid):
    al = [a for a in (d.get('asks') or []) + (edits.get('asks') or []) if a.get('c') == cid]
    al.sort(key=lambda a: a.get('u') or '')
    a = al[-1] if al else None
    if not a: return None
    sh = [s for s in (d.get('shoots') or []) + (edits.get('shoots') or []) if s.get('c') == cid and (s.get('u') or '') >= (a.get('u') or '') and s.get('date', '') >= today]
    return None if sh else a

ops, bad = [], 0
for r in rows:
    if not r or len(r) < 2: continue
    v = str(r[1]).strip()
    if '.' not in v: continue
    slug, data = v.split('.', 1)
    if slug not in by_slug: bad += 1; continue
    c, k = by_slug[slug]
    try:
        b = b64u(data); o = json.loads(k.decrypt(b[:12], b[12:], None))
    except Exception:
        bad += 1; continue
    if o.get('c') != c['id']: bad += 1; continue
    o['_id'] = str(o.get('id') or hashlib.sha256(v.encode()).hexdigest()[:20])
    o['_c'] = c; o['_at'] = r[0]
    ops.append(o)
ops.sort(key=lambda o: o.get('u') or '')

applied, info = [], []
items_of = {c['id']: {i['id'] for i in c.get('items', [])} for c in d['clients']}
for o in ops:
    if o['_id'] in done: continue
    c = o['_c']; cid = c['id']; u = o.get('u') or now
    if o.get('t') == 'ping':
        pass  # test spojení ze zóny, nic se nemění
    elif o.get('t') == 'order' and isinstance(o.get('ids'), list):
        ids = [str(x) for x in o['ids'] if str(x) in items_of[cid]][:100]
        eo = (edits.get('order') or {}).get(cid) or {}
        if not ids: info.append({'c': cid, 'msg': 'pořadí videí bez známých videí – přeskočeno'})
        elif (c.get('orderU') or '') >= u or (eo.get('u') or '') >= u:
            info.append({'c': cid, 'msg': f'{nick(c)} poslal pořadí, ale novější už je zapsané – přeskočeno'})
        else:
            rest = [x for x in (c.get('order') or []) if x not in ids and x in items_of[cid]]
            c['order'] = ids + rest; c['orderU'] = u; c['orderBy'] = 'client'
            applied.append({'c': cid, 'kind': 'order', 'msg': f'{nick(c)} poslal pořadí videí ({len(ids)}) – plán je podle něj'})
    elif o.get('t') == 'reply' and o.get('kind') in ('ok', 'alt') and o.get('date'):
        a = current_ask(cid)
        if o['kind'] == 'ok':
            if a and (o.get('k') == ask_key(a) or (o.get('date') == a.get('date') and (o.get('time') or '') == (a.get('time') or ''))):
                dt, tm, nt = a['date'], a.get('time') or o.get('time') or '', a.get('note') or o.get('note') or ''
                for s in [s for s in d['shoots'] if s.get('c') == cid and s.get('date', '') >= today and s.get('date') != dt]:
                    d['shootsOff'].append({'c': cid, 'date': s['date'], 'u': u})
                d['shoots'] = [s for s in d['shoots'] if not (s.get('c') == cid and s.get('date', '') >= today)]
                d['shoots'].append({'c': cid, 'date': dt, 'time': tm, 'note': nt, 'u': u, 'by': 'client'})
                d['asks'] = [x for x in d['asks'] if x.get('c') != cid]
                applied.append({'c': cid, 'kind': 'shoot', 'msg': f'Domluveno: {c["name"]} {when(dt, tm)} (potvrdil v zóně)'})
            else:
                info.append({'c': cid, 'msg': f'{nick(c)} potvrdil {when(o["date"], o.get("time"))}, ale návrh se mezitím změnil – nic nezapsáno'})
        else:
            d['asks'] = [x for x in d['asks'] if x.get('c') != cid]
            d['asks'].append({'c': cid, 'date': o['date'], 'time': o.get('time') or '', 'note': o.get('note') or '', 'from': 'client', 'at': u, 'u': u})
            applied.append({'c': cid, 'kind': 'alt', 'msg': f'{nick(c)} navrhuje {when(o["date"], o.get("time"))} – appka → Natáčení → Beru'})
    else:
        info.append({'c': cid, 'msg': 'neznámý typ záznamu ze zóny – přeskočeno'})
    done.append(o['_id'])

if apply:
    d['zoneDone'] = done[-500:]
    d['shootsOff'] = d['shootsOff'][-200:]
    json.dump(d, open(path, 'w'), ensure_ascii=False, indent=1)
print(json.dumps({'applied': applied, 'info': info, 'bad': bad, 'rows': len(rows), 'new': len(applied) + len(info)}, ensure_ascii=False))
