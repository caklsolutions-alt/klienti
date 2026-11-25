# Úpravy z mobilní appky CRM (Sebastián je ukládá šifrovaně do crm/inbox/*.enc přes GitHub API).
# python3 tools/inbox.py <crm_data.json>            → vypíše dešifrované úpravy (JSON), nic nemění
# python3 tools/inbox.py <crm_data.json> --apply    → promítne je do crm_data.json (shoots, shootsOff, asks, pořadí videí clients[].order, položky, invMarks),
#                                                      zapíše jejich id do inboxDone a smaže zpracované soubory z crm/inbox/
# Klíč je webAdmin.key v crm_data.json (nikdy ho nevypisuj).
import json, os, sys, base64, glob, datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = sys.argv[1]; apply = '--apply' in sys.argv
d = json.load(open(path))
wa = d.get('webAdmin') or {}
if not wa.get('key'): print('[]'); sys.exit(0)
k = base64.urlsafe_b64decode(wa['key'] + '=' * (-len(wa['key']) % 4))
files = sorted(glob.glob(os.path.join(ROOT, wa.get('slug', 'crm'), 'inbox', '*.enc')))
ops, bad = [], []
for f in files:
    b = open(f, 'rb').read()
    try:
        op = json.loads(AESGCM(k).decrypt(b[:12], b[12:], None)); op['_file'] = f; ops.append(op)
    except Exception:
        bad.append(f)
ops.sort(key=lambda o: o.get('u', ''))
if not apply:
    print(json.dumps([{x: v for x, v in o.items() if x != '_file'} for o in ops], ensure_ascii=False, indent=1))
    if bad: print('NEČITELNÉ:', len(bad), file=sys.stderr)
    sys.exit(0)

today = datetime.date.today().isoformat()
done = list(d.get('inboxDone') or [])
d.setdefault('shoots', []); d.setdefault('shootsOff', []); d.setdefault('invMarks', {}); d.setdefault('asks', [])
items = {it['id']: it for c in d['clients'] for it in c.get('items', [])}
log = []
for op in ops:
    t, u = op.get('t'), op.get('u', '')
    if op.get('id') in done: pass
    elif t == 'order' and op.get('c') and isinstance(op.get('ids'), list):
        cc = next((x for x in d['clients'] if x['id'] == op['c']), None)
        if cc is not None and (cc.get('orderU') or '') <= u:
            cc['order'] = [str(x) for x in op['ids']][:100]; cc['orderU'] = u; cc['orderBy'] = op.get('by') or 'seb'
            log.append(f"pořadí videí {op['c']} ({cc['orderBy']}, {len(cc['order'])})")
    elif t == 'ask' and op.get('c') and op.get('date'):
        d['asks'] = [x for x in d['asks'] if x.get('c') != op['c']]
        d['asks'].append({'c': op['c'], 'date': op['date'], 'time': op.get('time', ''), 'note': op.get('note', ''), 'from': op.get('from', ''), 'at': u, 'u': u})
        log.append(f"návrh natáčení {op['c']} {op['date']} {op.get('time','')}")
    elif t == 'shoot' and op.get('c') and op.get('date'):
        d['asks'] = [x for x in d['asks'] if x.get('c') != op['c'] or (x.get('u') or '') > u]
        for s in [s for s in d['shoots'] if s.get('c') == op['c'] and s.get('date', '') >= today and s.get('date') != op['date']]:
            d['shootsOff'].append({'c': s['c'], 'date': s['date'], 'u': u})
        d['shoots'] = [s for s in d['shoots'] if not (s.get('c') == op['c'] and (s.get('date') == op['date'] or s.get('date', '') >= today))]
        d['shoots'].append({'c': op['c'], 'date': op['date'], 'time': op.get('time', ''), 'note': op.get('note', ''), 'u': u})
        log.append(f"natáčení {op['c']} {op['date']} {op.get('time','')}")
    elif t == 'unshoot' and op.get('c') and op.get('date'):
        d['asks'] = [x for x in d['asks'] if x.get('c') != op['c'] or (x.get('u') or '') > u]
        d['shoots'] = [s for s in d['shoots'] if not (s.get('c') == op['c'] and s.get('date') == op['date'])]
        d['shootsOff'].append({'c': op['c'], 'date': op['date'], 'u': u}); log.append(f"zrušeno natáčení {op['c']} {op['date']}")
    elif t == 'item' and op.get('item') in items and isinstance(op.get('patch'), dict):
        it = items[op['item']]
        if (it.get('u') or '') <= u:
            for kk in ('s', 'date', 'bill'):
                if kk in op['patch']: it[kk] = op['patch'][kk]
            it['u'] = u; log.append(f"položka {op['item']} → {op['patch'].get('s','')}")
    elif t == 'inv' and op.get('key') and isinstance(op.get('patch'), dict):
        m = d['invMarks'].get(op['key'], {}); m.update({kk: bool(v) for kk, v in op['patch'].items() if kk in ('approved', 'paid')}); m['u'] = u
        d['invMarks'][op['key']] = m; log.append(f"faktura {op['key']} {op['patch']}")
    done.append(op.get('id'))
    os.remove(op['_file'])
d['inboxDone'] = [x for x in done if x][-300:]
d['shootsOff'] = d['shootsOff'][-200:]
json.dump(d, open(path, 'w'), ensure_ascii=False, indent=1)
print('APPLIED', len(ops), '; '.join(log), ('| NEČITELNÉ ' + str(len(bad))) if bad else '')
