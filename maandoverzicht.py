"""
maandoverzicht.py — Maandoverzicht alle medewerkers per dienst
Rijen = diensten op tijd, kolommen = dagen, cellen = medewerker met kleur
"""
import re
from analyse import naam_schoon
from rooster import normaliseer_dienst, extraheer_dienst

_DAGNAMEN = ['maandag','dinsdag','woensdag','donderdag','vrijdag','zaterdag','zondag']
_MAANDEN  = ['','januari','februari','maart','april','mei','juni',
             'juli','augustus','september','oktober','november','december']

# Kleurpaletten per groep (hex zonder #, licht naar donker)
KLEUREN = {
    'senior': [
        'FECACA','FCA5A5','F87171','EF4444','DC2626',
        'B91C1C','991B1B','7F1D1D','FED7D7','FBBFBF','F9A8A8'
    ],
    'vpcmk': [
        'BBF7D0','86EFAC','4ADE80','22C55E','16A34A',
        '15803D','166534','14532D','D1FAE5','A7F3D0','6EE7B7'
    ],
    'uitgifte': [
        'BFDBFE','93C5FD','60A5FA','3B82F6','2563EB',
        '1D4ED8','1E40AF','1E3A8A','DBEAFE','BAE6FD','7DD3FC'
    ],
}

# Tekstkleur per achtergrond (donker/licht)
def tekst_kleur(bg_hex):
    r = int(bg_hex[0:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:6], 16)
    lum = (0.299*r + 0.587*g + 0.114*b)
    return '1A2530' if lum > 160 else 'FFFFFF'


def begintijd_min(dienst_str):
    """Begintijd in minuten voor sortering (x-diensten sorteren mee op tijd)."""
    d = (normaliseer_dienst(dienst_str) or dienst_str).lstrip('x').strip()
    m = re.search(r'(\d{1,2}):(\d{2})', d)
    if not m:
        return 9999
    uur = int(m.group(1))
    # Nachtdiensten na middernacht (0-6u) sorteren achteraan
    if uur < 7:
        uur += 24
    return uur * 60 + int(m.group(2))


def dienst_label(dienst_norm):
    """Korte weergave van dienstnaam."""
    if not dienst_norm:
        return ''
    d = dienst_norm.strip()
    # Strip MKA suffix
    d = re.sub(r'\s*MKA\s*$', '', d, flags=re.IGNORECASE).strip()
    return d


def bouw_omgekeerde_lookup(mw_db):
    """Bouw lookup voor naam matching rapport → medewerker db."""
    directe = {ns: mw for ns, mw in mw_db.items()}
    # Voornaam index (eerste woord db key = voornaam, want db = "voornaam achternaam")
    voornaam_idx = {}
    for ns, mw in mw_db.items():
        vn = ns.split()[0]  # eerste woord = voornaam in db
        voornaam_idx.setdefault(vn, []).append(mw)
    # Woord index voor score matching
    woord_idx = {}
    for ns, mw in mw_db.items():
        for woord in ns.split():
            if len(woord) > 3:
                woord_idx.setdefault(woord, []).append(mw)
    return {'directe': directe, 'voornaam': voornaam_idx, 'woord': woord_idx}


def zoek_mw(naam, lookup):
    """Zoek medewerker op naam uit rapport via score-matching."""
    ns = naam_schoon(naam)
    # Directe match
    if ns in lookup['directe']:
        return lookup['directe'][ns]
    woorden = [w for w in ns.split() if len(w) > 2]
    if not woorden:
        return None
    # Score: tel overlappende woorden met elke db naam
    beste_score = 0
    beste_match = None
    for db_ns, mw in lookup['directe'].items():
        db_woorden = db_ns.split()
        score = sum(1 for w in woorden if w in db_woorden)
        if score > beste_score:
            beste_score = score
            beste_match = mw
    # Minimaal 2 woorden moeten matchen (voorkomt false positives op gemeenschappelijke voornamen)
    if beste_score >= 2:
        return beste_match
    # Fallback: voornaam (laatste woord rapport) moet UNIEK zijn in db
    # EN achternaam (eerste woord rapport) moet ook voorkomen in de db naam
    vn = woorden[-1]
    ach_check = woorden[0] if len(woorden) > 1 else ''
    kandidaten = lookup['voornaam'].get(vn, [])
    if len(kandidaten) == 1:
        # Verifieer dat achternaam overeenkomt
        if not ach_check or ach_check in kandidaten[0]['naam_schoon']:
            return kandidaten[0]
    # Fallback 2: partial voornaam match (eerste 5 letters) voor spellingsvarianten
    # Alleen als achternaam ook overeenkomt (voorkomt false positives op veelvoorkomende voornamen)
    vn_partial = vn[:5]
    ach_rapport = woorden[0] if len(woorden) > 1 else ''
    for db_vn, db_kand in lookup['voornaam'].items():
        if db_vn[:5] == vn_partial and len(db_kand) == 1:
            if ach_rapport and ach_rapport in db_kand[0]['naam_schoon']:
                return db_kand[0]
    return None





def functiegroep(mw):
    """Bepaal kleurgroep van medewerker."""
    if mw['skills']['bp1_a']:
        return 'senior'
    if (mw['skills']['spoed_b'] and not mw['skills']['triage_c']) or \
       'uitgifte' in mw.get('functie', '').lower():
        return 'uitgifte'
    return 'vpcmk'


def bouw_mw_kleuren(mw_db):
    """Wijs aan elke medewerker een vaste kleur toe binnen zijn groep."""
    groepen = {'senior': [], 'vpcmk': [], 'uitgifte': []}
    for ns, mw in mw_db.items():
        groepen[functiegroep(mw)].append(ns)

    mw_kleur = {}
    for fg, leden in groepen.items():
        palet = KLEUREN[fg]
        for i, ns in enumerate(sorted(leden)):
            bg = palet[i % len(palet)]
            mw_kleur[ns] = {
                'groep': fg,
                'bg':    bg,
                'fg':    tekst_kleur(bg),
                'idx':   i,
            }
    return mw_kleur


def bouw_maandoverzicht(df, mw_db):
    """Bouw volledig maandoverzicht."""
    import pandas as pd

    lookup   = bouw_omgekeerde_lookup(mw_db)
    mw_kleur = bouw_mw_kleuren(mw_db)

    # Stap 1: Verzamel alle diensten met tijdpatroon uit het rapport
    alle_diensten = set()
    for _, r in df.iterrows():
        d     = extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or '').strip())
        inzet = str(r.get('Inzet', '') or '')
        if not d or d == '-':
            continue
        dn = normaliseer_dienst(d) or d
        if not re.search(r'\d{1,2}:\d{2}', dn):
            continue
        # Inzet 2 zonder tijdpatroon = overwerk, sla over
        if inzet == 'Inzet 2' and not re.search(r'\d{1,2}[.:]\d{2}', d):
            continue
        alle_diensten.add(dn)

    diensten_gesorteerd = sorted(alle_diensten, key=begintijd_min)

    # Stap 2: Verzamel datums
    datums = sorted(df['Datum'].dropna().unique())

    # Stap 3: Bouw matrix per datum per dienst
    matrix = {}  # datum_str -> dienst -> [medewerker_info]

    for datum in datums:
        datum_str = pd.Timestamp(datum).strftime('%Y-%m-%d')
        dag_df    = df[df['Datum'] == datum]
        matrix[datum_str] = {d: [] for d in diensten_gesorteerd}

        for _, r in dag_df.iterrows():
            naam  = str(r.get('Naam', '') or '').strip()
            d_raw = extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or '').strip())
            inzet = str(r.get('Inzet', '') or '')

            if not d_raw or d_raw == '-':
                continue
            if inzet == 'Inzet 2' and not re.search(r'\d{1,2}[.:]\d{2}', d_raw):
                continue

            dn = normaliseer_dienst(d_raw) or d_raw
            if dn not in matrix[datum_str]:
                continue

            # Zoek medewerker
            mw  = zoek_mw(naam, lookup)
            kleur = mw_kleur.get(mw['naam_schoon']) if mw else None

            # Voornaam
            if mw:
                delen = mw['naam_schoon'].split()
                vnaam = delen[-1].capitalize() if delen else naam
            else:
                delen = naam.split()
                vnaam = delen[-1] if delen else naam

            matrix[datum_str][dn].append({
                'naam':   naam,
                'vnaam':  vnaam,
                'bg':     kleur['bg'] if kleur else 'E8ECF0',
                'fg':     kleur['fg'] if kleur else '1A2530',
                'groep':  kleur['groep'] if kleur else 'onbekend',
            })

    # Stap 4: Dag info
    dag_info = {}
    for datum in datums:
        dt = pd.Timestamp(datum)
        datum_str = dt.strftime('%Y-%m-%d')
        dag_info[datum_str] = {
            'dag_nr':  dt.day,
            'weekdag': _DAGNAMEN[dt.weekday()],
            'maand':   _MAANDEN[dt.month],
            'jaar':    dt.year,
            'is_we':   dt.weekday() >= 5,
        }

    return {
        'diensten':  diensten_gesorteerd,
        'datums':    [pd.Timestamp(d).strftime('%Y-%m-%d') for d in datums],
        'dag_info':  dag_info,
        'matrix':    matrix,
        'mw_kleur':  {v['bg']: True for v in mw_kleur.values()},  # voor legenda
        'legenda':   _bouw_legenda(mw_db, mw_kleur),
    }


def _bouw_legenda(mw_db, mw_kleur):
    """Bouw legenda: per medewerker naam + kleur."""
    legenda = []
    for ns, mw in sorted(mw_db.items(), key=lambda x: x[1]['naam']):
        kleur = mw_kleur.get(ns)
        if kleur:
            legenda.append({
                'naam':  mw['naam'],
                'vnaam': ns.split()[-1].capitalize(),
                'bg':    kleur['bg'],
                'fg':    kleur['fg'],
                'groep': kleur['groep'],
            })
    return legenda
