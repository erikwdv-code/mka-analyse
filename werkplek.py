"""
werkplek.py — Werkplekbezetting berekening voor MKA
Toewijzing van diensten aan fysieke werkplekken + maandoverzicht
"""
import re
from rooster import normaliseer_dienst, extraheer_dienst
from analyse import naam_schoon

# Werkplekken
WERKPLEKKEN = ['uitgifte_B', 'spoed_B', 'A', 'C']
MAX_C = 3  # C1, C2, C3 vooraan (C4 zijkant = gedetacheerden)

_DAGNAMEN = ['maandag','dinsdag','woensdag','donderdag','vrijdag','zaterdag','zondag']
_MAANDEN  = ['','januari','februari','maart','april','mei','juni',
             'juli','augustus','september','oktober','november','december']


def werkplek_type(dienst_norm):
    """Geef werkplek type terug op basis van genormaliseerde dienstnaam."""
    if not dienst_norm:
        return None
    d = dienst_norm.lower().strip()
    if d.startswith('x'):
        d = d[1:]  # strip x prefix voor matching
    if d.endswith(' a'):
        return 'A'
    if re.search(r'^(7|15|23):00.*\bb\b', d):
        return 'spoed_B'
    if re.search(r'^(7|15):30.*\bb\b', d):
        return 'uitgifte_B'
    if re.search(r'\bc\d?\b', d):
        return 'C'
    # A2 brede triage = neemt een C werkplek in
    if 'a2 brede triage' in d:
        return 'C'
    return None


def tijdslot(dienst_norm):
    """Geef begin/eind in minuten sinds middernacht."""
    if not dienst_norm:
        return None
    m = re.search(r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', dienst_norm)
    if not m:
        return None
    bh, bm = int(m.group(1)), int(m.group(2))
    eh, em = int(m.group(3)), int(m.group(4))
    begin_min = bh * 60 + bm
    eind_min  = eh * 60 + em
    if eind_min < begin_min:
        eind_min += 24 * 60
    return {'begin': begin_min, 'eind': eind_min}


def minuten_naar_pct(minuten):
    """Zet minuten om naar percentage van 24u voor tijdlijn."""
    return round(minuten / (24 * 60) * 100, 2)


def blok_type(begin, eind):
    """Geef dag/avond/nacht blok terug voor een dienst."""
    # Dag: 07:00-15:00 (420-900)
    # Avond: 15:00-23:00 (900-1380)
    # Nacht: 23:00-07:00 (1380-1860 of 0-420)
    blokken = []
    if begin < 900 and eind > 420:
        if begin <= 420 and eind >= 900:
            blokken.append('D')
        elif begin < 900:
            blokken.append('D')
    if begin < 1380 and eind > 900:
        if begin <= 900 and eind >= 1380:
            blokken.append('A')
        elif begin < 1380 and eind > 900:
            blokken.append('A')
    if eind > 1380 or begin >= 1380 or begin < 420:
        blokken.append('N')
    return list(dict.fromkeys(blokken))  # uniek, volgorde bewaard


def bouw_dag_bezetting(dag_df):
    """Bereken bezetting voor één dag."""
    bezetting = []
    for _, r in dag_df.iterrows():
        dienst_orig = extraheer_dienst(str(r.get('Dienst(en) realisatie', '') or '').strip())
        naam        = str(r.get('Naam', '') or '').strip()
        inzet       = str(r.get('Inzet', '') or '').strip()

        heeft_tijd = bool(re.search(r'\d{1,2}[.:]\d{2}', dienst_orig))
        if not dienst_orig or dienst_orig in ('-', 'nan') or (inzet == 'Inzet 2' and not heeft_tijd):
            continue

        dn = normaliseer_dienst(dienst_orig) or dienst_orig.strip()

        wp = werkplek_type(dn)
        ts = tijdslot(dn)
        if not wp or not ts:
            continue

        is_deta = '(deta)' in naam.lower()
        is_x    = dienst_orig.lower().startswith('x')

        # Voornaam extraheren
        ns    = naam_schoon(naam)
        delen = ns.split()
        vnaam = delen[-1].capitalize() if delen else naam

        bezetting.append({
            'naam':    naam,
            'voornaam': vnaam,
            'wp':      wp,
            'begin':   ts['begin'],
            'eind':    ts['eind'],
            'dienst':  dn,
            'is_deta': is_deta,
            'is_x':    is_x,
        })

    return bezetting


def bouw_tijdlijn(bezetting):
    """Bouw tijdlijn data per werkplek voor één dag."""
    tijdlijn = {
        'uitgifte_B': [],
        'spoed_B':    [],
        'A':          [],
        'C1':         [],
        'C2':         [],
        'C3':         [],
        'C4_zij':     [],
    }

    # Sorteer C diensten op begintijd
    c_diensten = sorted([b for b in bezetting if b['wp'] == 'C'],
                        key=lambda x: x['begin'])

    c_teller = {'C1': 0, 'C2': 0, 'C3': 0}  # tel gelijktijdige bezetting

    for b in bezetting:
        seg = {
            'begin_pct': minuten_naar_pct(b['begin']),
            'breedte_pct': minuten_naar_pct(b['eind'] - b['begin']),
            'naam': b['voornaam'],
            'is_deta': b['is_deta'],
            'is_x': b['is_x'],
            'dienst': b['dienst'],
        }
        if b['wp'] == 'uitgifte_B':
            tijdlijn['uitgifte_B'].append(seg)
        elif b['wp'] == 'spoed_B':
            tijdlijn['spoed_B'].append(seg)
        elif b['wp'] == 'A':
            tijdlijn['A'].append(seg)

    # C diensten verdelen over C1/C2/C3/C4_zij
    for b in c_diensten:
        seg = {
            'begin_pct': minuten_naar_pct(b['begin']),
            'breedte_pct': minuten_naar_pct(b['eind'] - b['begin']),
            'naam': b['voornaam'],
            'is_deta': b['is_deta'],
            'is_x': b['is_x'],
            'dienst': b['dienst'],
        }
        if b['is_deta']:
            tijdlijn['C4_zij'].append(seg)
        elif len(tijdlijn['C1']) == 0 or _gelijktijdig_bezet(tijdlijn['C1'], b) < 1:
            tijdlijn['C1'].append(seg)
        elif len(tijdlijn['C2']) == 0 or _gelijktijdig_bezet(tijdlijn['C2'], b) < 1:
            tijdlijn['C2'].append(seg)
        elif len(tijdlijn['C3']) == 0 or _gelijktijdig_bezet(tijdlijn['C3'], b) < 1:
            tijdlijn['C3'].append(seg)
        else:
            tijdlijn['C4_zij'].append(seg)

    return tijdlijn


def _gelijktijdig_bezet(segmenten, nieuw):
    """Check of er al een segment is dat overlapt met het nieuwe."""
    for s in segmenten:
        s_begin = s['begin_pct'] / 100 * 1440
        s_eind  = s_begin + s['breedte_pct'] / 100 * 1440
        if nieuw['begin'] < s_eind and nieuw['eind'] > s_begin:
            return 1
    return 0


def bouw_maand_werkplek(df):
    """Bouw maandoverzicht werkplekbezetting per dag."""
    resultaat = {}

    for datum, dag_df in df.groupby('Datum'):
        import pandas as pd
        if pd.isna(datum):
            continue

        datum_str = datum.strftime('%Y-%m-%d')
        dag_naam  = _DAGNAMEN[datum.weekday()]
        datum_nl  = f"{dag_naam} {datum.day} {_MAANDEN[datum.month]}"

        bezetting = bouw_dag_bezetting(dag_df)
        tijdlijn  = bouw_tijdlijn(bezetting)

        # Blok samenvatting D/A/N per werkplek
        def blokken_plek(segs):
            dag_bez = avond_bez = nacht_bez = 0
            for s in segs:
                begin = round(s['begin_pct'] / 100 * 1440)
                eind  = begin + round(s['breedte_pct'] / 100 * 1440)
                if begin < 900 and eind > 420:   dag_bez = 1
                if begin < 1380 and eind > 900:  avond_bez = 1
                if eind > 1380 or (begin < 420 and eind > 0): nacht_bez = 1
            return {'D': dag_bez, 'A': avond_bez, 'N': nacht_bez}

        # Vrije C plekken per blok
        c_plekken = [tijdlijn['C1'], tijdlijn['C2'], tijdlijn['C3']]
        c_vrij = {'D': 0, 'A': 0, 'N': 0}
        for blok in ['D', 'A', 'N']:
            vrij = 0
            for plek in c_plekken:
                b = blokken_plek(plek)
                if b[blok] == 0:
                    vrij += 1
            c_vrij[blok] = vrij

        resultaat[datum_str] = {
            'datum_str':  datum_str,
            'datum_nl':   datum_nl,
            'weekdag':    dag_naam,
            'dag_nr':     datum.day,
            'maand_nr':   datum.month,
            'tijdlijn':   tijdlijn,
            'c_vrij':     c_vrij,
            'c_bezet': {
                'D': 3 - c_vrij['D'],
                'A': 3 - c_vrij['A'],
                'N': 3 - c_vrij['N'],
            },
            'b_uitgifte': blokken_plek(tijdlijn['uitgifte_B']),
            'b_spoed':    blokken_plek(tijdlijn['spoed_B']),
            'b_a':        blokken_plek(tijdlijn['A']),
        }

    return resultaat
