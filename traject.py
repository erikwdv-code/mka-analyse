"""
traject.py — Opleidingstrajecten voor MKA medewerkers
Bijhoudt voortgang fase 1 (meekijken) en fase 2 (zelfstandig met supervisie)
"""
import re
import json
import os
from analyse import naam_schoon
from rooster import normaliseer_dienst, extraheer_dienst

_DAGNAMEN = ['maandag','dinsdag','woensdag','donderdag','vrijdag','zaterdag','zondag']
_MAANDEN  = ['','januari','februari','maart','april','mei','juni',
             'juli','augustus','september','oktober','november','december']

# ── Trajectdefinities ──────────────────────────────────────────────────────────
TRAJECTEN = {
    'b_spoed': {
        'naam':        'B Spoed',
        'omschrijving': '5x meekijken + 5x zelf draaien op spoeduitgifte B',
        'doel_diensten': {'7:00-15:00 B', '15:00-23:00 B', '23:00-7:00 B'},
        'begeleider_skill': 'spoed_b',
        'fase1_nodig': 5,
        'fase2_nodig': 5,
    },
    'b_besteld': {
        'naam':        'B Besteld vervoer',
        'omschrijving': '5x meekijken + 5x zelf draaien op besteld vervoer B',
        'doel_diensten': {'7:30-15:30 B', '15:30-23:30 B'},
        'begeleider_skill': 'uitgifte_b',
        'fase1_nodig': 5,
        'fase2_nodig': 5,
    },
    'c_aanname': {
        'naam':        'C Aanname',
        'omschrijving': '5x meekijken + 5x zelf draaien op aanname C diensten',
        'doel_diensten': {
            '7:00-15:00 C1', '7:00-15:00 C2', '7:30-15:30 C',
            '10:00-18:00 C', '11:00-19:00 C', '14:00-22:00 C',
            '15:00-23:00 C1', '15:00-23:00 C2', '15:30-23:30 C',
            '22:00-6:00 C', '23:00-7:00 C',
        },
        'begeleider_skill': 'triage_c',
        'fase1_nodig': 5,
        'fase2_nodig': 5,
    },
    'bp1': {
        'naam':        'BP1',
        'omschrijving': '5x meekijken + 5x zelf draaien op BP1/A met ervaren senior',
        'doel_diensten': {'7:00-15:00 A', '15:00-23:00 A', '23:00-7:00 A'},
        'begeleider_skill': 'bp1_a',
        'fase1_nodig': 5,
        'fase2_nodig': 5,
    },
}

OPSLAG_PAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_trajecten.json')


# ── Tijdhelpers ────────────────────────────────────────────────────────────────
def _begintijd(dienst):
    m = re.search(r'(\d{1,2}):(\d{2})', dienst or '')
    if not m: return None
    h = int(m.group(1))
    return (h + 24 if h < 7 else h) * 60 + int(m.group(2))

def _eindtijd(dienst):
    matches = re.findall(r'(\d{1,2}):(\d{2})', dienst or '')
    if len(matches) < 2: return None
    h, mi = int(matches[1][0]), int(matches[1][1])
    b = _begintijd(dienst)
    e = (h + 24 if h < 7 else h) * 60 + mi
    if e and b and e <= b: e += 24 * 60
    return e

def _overlapt(d1, d2):
    """Controleer of twee diensten in tijd overlappen."""
    b1, e1 = _begintijd(d1), _eindtijd(d1)
    b2, e2 = _begintijd(d2), _eindtijd(d2)
    if None in (b1, e1, b2, e2): return False
    return b1 < e2 and b2 < e1

def _datum_nl(datum):
    import pandas as pd
    dt = pd.Timestamp(datum)
    return f"{_DAGNAMEN[dt.weekday()]} {dt.day} {_MAANDEN[dt.month]} {dt.year}"


# ── Kern analyse ───────────────────────────────────────────────────────────────
def analyseer_traject(df, mw_db, kandidaat_ns, traject_key, lookup):
    """
    Analyseer het traject van een kandidaat over alle data in df.
    Geeft per dag terug: fase1/fase2/None
    """
    from maandoverzicht import zoek_mw
    import pandas as pd

    traject   = TRAJECTEN[traject_key]
    doel      = traject['doel_diensten']
    begel_sk  = traject['begeleider_skill']

    # Begeleiders = iedereen met de skill (exclusief de kandidaat zelf)
    begeleiders = {ns for ns, mw in mw_db.items()
                   if mw['skills'].get(begel_sk) and ns != kandidaat_ns}

    resultaten = []

    for datum, dag_df in df.groupby('Datum'):
        if pd.isna(datum):
            continue

        # Heeft kandidaat een doeldienst?
        kandidaat_dienst = None
        kandidaat_inzet  = None
        for _, r in dag_df.iterrows():
            n  = str(r.get('Naam', '') or '').strip()
            mw = zoek_mw(n, lookup)
            if not mw or mw['naam_schoon'] != kandidaat_ns:
                continue
            dn    = normaliseer_dienst(extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or ''))) or ''
            inzet = str(r.get('Inzet', '') or '')
            dn_clean = dn.lstrip('x').strip()
            if dn_clean in doel:
                kandidaat_dienst = dn_clean
                kandidaat_inzet  = inzet
                break

        if not kandidaat_dienst:
            continue

        # Welke begeleiders overlappen in tijd op een doeldienst?
        begeleiders_dag = []
        for _, r in dag_df.iterrows():
            n  = str(r.get('Naam', '') or '').strip()
            mw = zoek_mw(n, lookup)
            if not mw or mw['naam_schoon'] == kandidaat_ns:
                continue
            if mw['naam_schoon'] not in begeleiders:
                continue
            dn = normaliseer_dienst(extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or ''))) or ''
            dn_clean = dn.lstrip('x').strip()
            # Begeleider moet op doeldienst staan EN overlappen in tijd
            if dn_clean in doel and _overlapt(kandidaat_dienst, dn_clean):
                begeleiders_dag.append(mw['naam'])

        # Geen overlappende begeleider = dag telt niet mee
        if not begeleiders_dag:
            continue

        # Eerste 5 = fase1 (meekijken), volgende 5 = fase2 (zelfstandig maar begeleider aanwezig)
        fase = 'fase1' if len([r for r in resultaten if r['fase'] == 'fase1']) < traject['fase1_nodig'] else 'fase2'
        begel_namen = begeleiders_dag
        resultaten.append({
            'datum':       datum.strftime('%Y-%m-%d'),
            'datum_nl':    _datum_nl(datum),
            'dienst':      kandidaat_dienst,
            'fase':        fase,
            'begeleiders': begel_namen,
            'inzet':       kandidaat_inzet or '',
        })

    return resultaten


def samenvatting(resultaten, traject_key):
    """Geef voortgangssamenvatting terug."""
    traject = TRAJECTEN[traject_key]
    fase1 = [r for r in resultaten if r['fase'] == 'fase1']
    fase2 = [r for r in resultaten if r['fase'] == 'fase2']
    return {
        'traject_naam':  traject['naam'],
        'fase1_gedaan':  len(fase1),
        'fase1_nodig':   traject['fase1_nodig'],
        'fase2_gedaan':  len(fase2),
        'fase2_nodig':   traject['fase2_nodig'],
        'fase1_resterend': max(0, traject['fase1_nodig'] - len(fase1)),
        'fase2_resterend': max(0, traject['fase2_nodig'] - len(fase2)),
        'fase1_klaar':   len(fase1) >= traject['fase1_nodig'],
        'fase2_klaar':   len(fase2) >= traject['fase2_nodig'],
        'klaar':         len(fase1) >= traject['fase1_nodig'] and
                         len(fase2) >= traject['fase2_nodig'],
        'diensten':      resultaten,
    }


# ── Inwerkschema voorstel ──────────────────────────────────────────────────────
def genereer_inwerkschema(df_toekomst, mw_db, kandidaat_ns, traject_key,
                           lookup, samenvatting_huidig):
    """
    Zoek in een toekomstig rapport de beste momenten voor inwerkdiensten.
    Geeft suggesties terug voor fase1 en fase2 diensten.
    """
    from maandoverzicht import zoek_mw
    import pandas as pd

    traject   = TRAJECTEN[traject_key]
    doel      = traject['doel_diensten']
    begel_sk  = traject['begeleider_skill']

    nog_fase1 = samenvatting_huidig['fase1_resterend']
    nog_fase2 = samenvatting_huidig['fase2_resterend']

    if nog_fase1 <= 0 and nog_fase2 <= 0:
        return []

    begeleiders = {ns: mw for ns, mw in mw_db.items()
                   if mw['skills'].get(begel_sk) and ns != kandidaat_ns}

    suggesties = []

    for datum, dag_df in df_toekomst.groupby('Datum'):
        if pd.isna(datum):
            continue

        # Heeft kandidaat al een dienst die dag?
        kandidaat_bezet = False
        for _, r in dag_df.iterrows():
            n  = str(r.get('Naam', '') or '').strip()
            mw = zoek_mw(n, lookup)
            if mw and mw['naam_schoon'] == kandidaat_ns:
                dn = normaliseer_dienst(extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or ''))) or ''
                if dn and dn != '-':
                    kandidaat_bezet = True
                    break

        if kandidaat_bezet:
            continue

        # Welke B-spoed diensten zijn die dag bezet door ervaren begeleiders?
        begel_diensten = {}  # dienst -> [begeleider naam]
        for _, r in dag_df.iterrows():
            n  = str(r.get('Naam', '') or '').strip()
            mw = zoek_mw(n, lookup)
            if not mw or mw['naam_schoon'] not in begeleiders:
                continue
            dn = normaliseer_dienst(extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or ''))) or ''
            dn_clean = dn.lstrip('x').strip()
            if dn_clean in doel:
                begel_diensten.setdefault(dn_clean, []).append(mw['naam'])

        if not begel_diensten:
            continue

        # Zijn er vrije B-spoed plekken? (niet al 3 B medewerkers bezet)
        b_bezet = 0
        for _, r in dag_df.iterrows():
            dn = normaliseer_dienst(extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or ''))) or ''
            if dn.lstrip('x').strip() in doel:
                b_bezet += 1

        for dienst, begeleid_door in begel_diensten.items():
            # Fase 1 suggestie: kandidaat kijkt mee
            if nog_fase1 > 0:
                suggesties.append({
                    'datum':      datum.strftime('%Y-%m-%d'),
                    'datum_nl':   _datum_nl(datum),
                    'dienst':     dienst,
                    'fase':       'fase1',
                    'begeleiders': begeleid_door,
                    'uitleg':     f"Meekijken met {', '.join(begeleid_door)}",
                })
                nog_fase1 -= 1
            elif nog_fase2 > 0:
                suggesties.append({
                    'datum':      datum.strftime('%Y-%m-%d'),
                    'datum_nl':   _datum_nl(datum),
                    'dienst':     dienst,
                    'fase':       'fase2',
                    'begeleiders': begeleid_door,
                    'uitleg':     f"Zelfstandig, supervisie door {', '.join(begeleid_door)}",
                })
                nog_fase2 -= 1

        if nog_fase1 <= 0 and nog_fase2 <= 0:
            break

    return suggesties


# ── Persistente opslag ─────────────────────────────────────────────────────────
def laad_traject_data():
    """Laad opgeslagen trajectdata."""
    if os.path.exists(OPSLAG_PAD):
        with open(OPSLAG_PAD, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'rapporten': [], 'trajecten': {}}


def sla_traject_data_op(data):
    """Sla trajectdata op."""
    with open(OPSLAG_PAD, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
