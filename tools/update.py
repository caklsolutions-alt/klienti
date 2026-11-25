# Aktualizace webu klientských zón (spouští ji automatická kontrola CRM).
# python3 tools/update.py <crm_data.json> <zony_dir> [thumbs_dir] [strat_dir] [--edits edits.json]
#   zony_dir/<idKlienta>/data.json  = data zóny (stejná jako v artefaktu zóny)
#   thumbs_dir/<id>.webp            = nové náhledovky (zkopírují se, jen když v repu chybí)
#   strat_dir/<idKlienta>/strategie.pdf + p1.png… = nová strategie (zašifruje se, jen když v repu chybí)
#   --edits edits.json = dokument crm/edits z databáze CRM (Sebastiánovy ruční úpravy); jde jen do jeho appky
# Sebastiánova appka (celé CRM jen na čtení) = složka webAdmin.slug, data šifrovaná klíčem webAdmin.key.
# Klíče jsou jen v CRM (clients[].web.key, webAdmin.key), do repozitáře se nikdy nedostanou.
import json, os, sys, base64, shutil, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[1:]; edits_f = None
if '--edits' in argv: i = argv.index('--edits'); edits_f = argv[i + 1]; del argv[i:i + 2]
crm = json.load(open(argv[0])); zones = argv[1]
thumbs = argv[2] if len(argv) > 2 else None
strat = argv[3] if len(argv) > 3 else None

def key(s): k = base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)); assert len(k) == 32; return k
def enc(k, b): iv = os.urandom(12); return iv + AESGCM(k).encrypt(iv, b, None)

done = []
for c in crm['clients']:
    w = c.get('web')
    src = os.path.join(zones, c['id'], 'data.json')
    if not w or not os.path.exists(src): continue
    slug = w['slug']; assert re.fullmatch(r'[a-z0-9-]+', slug)
    zd = os.path.join(ROOT, slug)
    if not os.path.exists(os.path.join(zd, 'index.html')):
        print('SKIP', c['id'], '– zóna na webu ještě není postavená'); continue
    k = key(w['key'])
    d = json.load(open(src))
    assert [x['id'] for x in d['clients']] == [c['id']], 'zóna smí obsahovat jen svého klienta'
    for f in ('web', 'zoneUrl', 'refBy', 'refActive', 'refEnd', 'statsMc'): d['clients'][0].pop(f, None)
    open(os.path.join(zd, 'data.enc'), 'wb').write(enc(k, json.dumps(d, ensure_ascii=False).encode()))
    for it in d['clients'][0].get('items', []):
        t = it.get('thumb')
        if t and thumbs and not os.path.exists(os.path.join(zd, t)):
            s = os.path.join(thumbs, os.path.basename(t))
            if os.path.exists(s): os.makedirs(os.path.join(zd, 'thumbs'), exist_ok=True); shutil.copy(s, os.path.join(zd, t))
    st = d['clients'][0].get('strategy')
    if st and strat:
        for p in [st.get('file', 'strategie.pdf')] + list(st.get('pages', [])):
            out = os.path.join(zd, re.sub(r'\.(pdf|png)$', '.enc', p))
            s = os.path.join(strat, c['id'], os.path.basename(p))
            if not os.path.exists(out) and os.path.exists(s):
                os.makedirs(os.path.dirname(out), exist_ok=True); open(out, 'wb').write(enc(k, open(s, 'rb').read()))
    done.append(slug)
wa = crm.get('webAdmin')
if wa and re.fullmatch(r'[a-z0-9-]+', wa.get('slug', '')) and os.path.exists(os.path.join(ROOT, wa['slug'], 'index.html')):
    ad = os.path.join(ROOT, wa['slug']); k = key(wa['key'])
    ed = {}
    if edits_f and os.path.exists(edits_f):
        try:
            ed = json.load(open(edits_f))
            if not isinstance(ed, dict): ed = {}
        except Exception: ed = {}
    import datetime
    blob = dict(crm); blob['_edits'] = ed; blob['_stamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    open(os.path.join(ad, 'data.enc'), 'wb').write(enc(k, json.dumps(blob, ensure_ascii=False).encode()))
    zslugs = [c['web']['slug'] for c in crm['clients'] if c.get('web')]
    for c in crm['clients']:
        for it in c.get('items', []):
            t = it.get('thumb')
            if not t or os.path.exists(os.path.join(ad, t)): continue
            cands = ([os.path.join(thumbs, os.path.basename(t))] if thumbs else []) + [os.path.join(ROOT, s, t) for s in zslugs]
            for s in cands:
                if os.path.exists(s): os.makedirs(os.path.join(ad, 'thumbs'), exist_ok=True); shutil.copy(s, os.path.join(ad, t)); break
    done.append(wa['slug'] + ' (appka)')
print('OK', ' '.join(done))
