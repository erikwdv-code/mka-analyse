"""
traject_optimizer.py — Optimalisatie van inwerktrajecten
Vindt kansen om inwerkers sneller door hun traject te helpen via wisselkandidaten
"""
import re
import json
import os
from datetime import date, timedelta
from traject import TRAJECTEN, _datum_nl, _overlapt
from rooster import normaliseer_dienst, extraheer_dienst
from maandoverzicht import zoek_mw

ACTIEVE_TRAJECTEN_PAD = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'data_actieve_trajecten.json'
)

# ── Persistente opslag actieve trajecten ───────────────────────────────────────
def laad_actieve_trajecten():
    if os.path.exists(ACTIEVE_TRAJECTEN_PAD):
        with open(ACTIEVE_TRAJECTEN_PAD, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def sla_actieve_trajecten_op(data):
    with open(ACTIEVE_TRAJECTEN_PAD, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Wisselkandidaten detectie ──────────────────────────────────────────────────
def _is_wisselbaar(dienst_raw):
    """Kan deze medewerker zijn dienst afstaan? X-dienst of niet-essentieel."""
    dn = normaliseer_dienst(extraheer_dienst(dienst_raw)) or ''
    return dn.startswith('x') or dn.startswith('X')

def _dienst_type(dienst_raw):
    dn = normaliseer_dienst(extraheer_dienst(dienst_raw)) or ''
    return dn

def _kan_overnemen(kandidaat_dienst, over_te_nemen_dienst):
    """Check of tijden overlappen (kandidaat moet vrij zijn op dat moment)."""
    return not _overlapt(kandidaat_dienst, over_te_nemen_dienst)

# ── Hoofdfunctie: analyseer kansen voor actief traject ────────────────────────
def analyseer_traject_kansen(df, mw_db, lookup, actief_traject, al_gedaan_fase1=0, al_gedaan_fase2=0):
    """
    Analyseer het rapport en geef kansen terug voor dit traject.
    - directe_kansen: inwerker staat vrij/X, begeleider aanwezig
    - wissel_kansen:  inwerker staat op andere dienst, wisselkandidaat beschikbaar
    - upgrade_kansen: inwerker staat al op doeldienst met begeleider (fase1),
                      maar fase1 is vol → begeleider elders inzetten = fase2
    """
    import pandas as pd

    kandidaat_ns = actief_traject['naam_schoon']
    traject_key  = actief_traject['traject']
    traject      = TRAJECTEN[traject_key]
    doel         = traject['doel_diensten']
    begel_sk     = traject['begeleider_skill']

    nog_fase1 = max(0, traject['fase1_nodig'] - al_gedaan_fase1)
    nog_fase2 = max(0, traject['fase2_nodig'] - al_gedaan_fase2)

    begeleiders = {ns for ns, mw in mw_db.items()
                   if mw['skills'].get(begel_sk) and ns != kandidaat_ns}

    vandaag = date.today()
    directe_kansen = []
    wissel_kansen  = []
    upgrade_kansen = []

    # Bouw set van datums die al geteld zijn in de historische analyse
    from traject import analyseer_traject
    al_geteld = set()
    if al_gedaan_fase1 > 0 or al_gedaan_fase2 > 0:
        hist = analyseer_traject(df, mw_db, kandidaat_ns, traject_key, lookup)
        al_geteld = {r['datum'] for r in hist if r['datum'] <= vandaag.isoformat()}

    for datum, dag_df in df.groupby('Datum'):
        if pd.isna(datum): continue
        if datum.date() <= vandaag: continue
        if datum.strftime('%Y-%m-%d') in al_geteld: continue  # al geteld in historische analyse

        datum_str = datum.strftime('%Y-%m-%d')
        datum_nl  = _datum_nl(datum)

        # Wat doet de inwerker deze dag?
        kandidaat_dienst = None
        kandidaat_wisselbaar = False
        for _, r in dag_df.iterrows():
            mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
            if not mw_info or mw_info['naam_schoon'] != kandidaat_ns: continue
            dn_raw = str(r.get('Dienst(en) realisatie','') or '')
            dn = normaliseer_dienst(extraheer_dienst(dn_raw)) or ''
            if dn and dn != '-':
                kandidaat_dienst = dn
                kandidaat_wisselbaar = _is_wisselbaar(dn_raw) or dn.startswith('x')
            break

        # Welke begeleiders draaien een doeldienst?
        begel_op_doel = {}  # dienst -> [naam_schoon]
        for _, r in dag_df.iterrows():
            mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
            if not mw_info or mw_info['naam_schoon'] not in begeleiders: continue
            dn = normaliseer_dienst(extraheer_dienst(
                str(r.get('Dienst(en) realisatie','') or ''))) or ''
            dn_clean = dn.lstrip('x').strip()
            if dn_clean in doel:
                begel_op_doel.setdefault(dn_clean, []).append(mw_info['naam_schoon'])

        fase = 'fase1' if nog_fase1 > 0 else ('fase2' if nog_fase2 > 0 else None)
        if not fase and not (kandidaat_dienst and kandidaat_dienst.lstrip('x').strip() in doel):
            continue

        kandidaat_clean = (kandidaat_dienst or '').lstrip('x').strip()

        # ── UPGRADE KANS ──────────────────────────────────────────────────────
        # Inwerker staat al op doeldienst MET begeleider (fase1 situatie gepland)
        # maar fase1 is al vol → begeleider kan elders worden ingezet = fase2
        # Toon dit voor alle toekomstige geplande diensten waar dit van toepassing is
        if (fase in ('fase2', None) and kandidaat_clean in doel
                and kandidaat_clean in begel_op_doel):
            begel_samen_ns = begel_op_doel[kandidaat_clean]
            begel_namen = [mw_db[ns]['naam'] for ns in begel_samen_ns if ns in mw_db]

            # Zoek alternatief voor de begeleider die dag
            alternatief = 'kan op X-dienst of andere rol worden gezet'
            for _, r in dag_df.iterrows():
                mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
                if not mw_info or mw_info['naam_schoon'] not in set(begel_samen_ns): continue
                dn_raw = str(r.get('Dienst(en) realisatie','') or '')
                dn = normaliseer_dienst(extraheer_dienst(dn_raw)) or ''
                if _is_wisselbaar(dn_raw):
                    alternatief = f'staat al op X-dienst ({dn}) — eenvoudig te regelen'
                    break

            # Zoek ook of er iemand is met een X-dienst die de begeleider positie kan innemen
            andere_opties = []
            for _, r in dag_df.iterrows():
                mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
                if not mw_info or mw_info['naam_schoon'] == kandidaat_ns: continue
                if mw_info['naam_schoon'] in set(begel_samen_ns): continue
                dn_raw = str(r.get('Dienst(en) realisatie','') or '')
                if _is_wisselbaar(dn_raw):
                    dn = normaliseer_dienst(extraheer_dienst(dn_raw)) or ''
                    dn_c = dn.lstrip('x').strip()
                    if _kan_overnemen(kandidaat_clean, dn_c):
                        andere_opties.append(mw_info['naam'])

            upgrade_kansen.append({
                'datum':       datum_str,
                'datum_nl':    datum_nl,
                'dienst':      kandidaat_clean,
                'fase':        'fase2',
                'begeleiders': begel_namen,
                'alternatief': alternatief,
                'andere_opties': andere_opties[:2],
                'uitleg':      (f'{", ".join(begel_namen)} naar andere rol ({alternatief}) → '
                               f'inwerker draait {kandidaat_clean} zelfstandig'),
            })
            if nog_fase2 > 0: nog_fase2 = max(0, nog_fase2 - 1)
            continue

        if not begel_op_doel: continue

        if not fase: continue

        # ── DIRECTE KANS ─────────────────────────────────────────────────────
        # Alleen als inwerker al staat op een X-dienst (wisselbaar) — vrij = geen kans
        if kandidaat_dienst and kandidaat_wisselbaar:
            for dienst, begels in begel_op_doel.items():
                begel_namen = [mw_db[ns]['naam'] for ns in begels if ns in mw_db]
                directe_kansen.append({
                    'datum':       datum_str,
                    'datum_nl':    datum_nl,
                    'dienst':      dienst,
                    'fase':        fase,
                    'begeleiders': begel_namen,
                    'uitleg':      ('Meekijken' if fase=='fase1' else 'Zelfstandig') + ' met ' + ', '.join(begel_namen),
                    'kandidaat_huidige_dienst': kandidaat_dienst or '—',
                })
                if fase == 'fase1': nog_fase1 = max(0, nog_fase1 - 1)
                else: nog_fase2 = max(0, nog_fase2 - 1)
                break

        # ── WISSEL KANS ──────────────────────────────────────────────────────
        elif kandidaat_dienst and not kandidaat_wisselbaar and kandidaat_clean not in doel:
            wisselkandidaten = []
            for _, r in dag_df.iterrows():
                mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
                if not mw_info or mw_info['naam_schoon'] == kandidaat_ns: continue
                dn_raw = str(r.get('Dienst(en) realisatie','') or '')
                dn = normaliseer_dienst(extraheer_dienst(dn_raw)) or ''
                if _is_wisselbaar(dn_raw) and _kan_overnemen(dn, kandidaat_clean):
                    wisselkandidaten.append({'naam': mw_info['naam'], 'huidige_dienst': dn})

            if wisselkandidaten:
                for dienst, begels in begel_op_doel.items():
                    begel_namen = [mw_db[ns]['naam'] for ns in begels if ns in mw_db]
                    wissel_kansen.append({
                        'datum':            datum_str,
                        'datum_nl':         datum_nl,
                        'doel_dienst':      dienst,
                        'fase':             fase,
                        'begeleiders':      begel_namen,
                        'kandidaat_dienst': kandidaat_clean,
                        'wisselkandidaten': wisselkandidaten[:3],
                        'uitleg':           (wisselkandidaten[0]['naam'] + ' neemt ' +
                                            kandidaat_clean + ' over → inwerker ' +
                                            ('meekijken' if fase=='fase1' else 'zelfstandig') +
                                            ' op ' + dienst + ' met ' + (begel_namen[0] if begel_namen else '?')),
                    })
                    if fase == 'fase1': nog_fase1 = max(0, nog_fase1 - 1)
                    else: nog_fase2 = max(0, nog_fase2 - 1)
                    break

    return {
        'directe_kansen': directe_kansen,
        'wissel_kansen':  wissel_kansen,
        'upgrade_kansen': upgrade_kansen,
        'nog_fase1':      nog_fase1,
        'nog_fase2':      nog_fase2,
    }



# ── Dashboard signalen: vrijgekomen plekken ────────────────────────────────────
def signaleer_vrijgekomen_plekken(df, mw_db, lookup, actieve_trajecten):
    """
    Vergelijk rapport met actieve trajecten en geef meldingen voor
    vrijgekomen doeldiensten die matchen met een lopend traject.
    """
    import pandas as pd

    vandaag = date.today()
    over14  = vandaag + timedelta(days=14)
    meldingen = []

    for actief in actieve_trajecten:
        kandidaat_ns = actief['naam_schoon']
        traject_key  = actief['traject']
        traject      = TRAJECTEN[traject_key]
        doel         = traject['doel_diensten']
        begel_sk     = traject['begeleider_skill']

        begeleiders = {ns for ns, mw in mw_db.items()
                       if mw['skills'].get(begel_sk) and ns != kandidaat_ns}

        for datum, dag_df in df.groupby('Datum'):
            if pd.isna(datum): continue
            if not (vandaag <= datum.date() <= over14): continue

            # Begeleider aanwezig op doeldienst?
            for _, r in dag_df.iterrows():
                mw_info = zoek_mw(str(r.get('Naam','')).strip(), lookup)
                if not mw_info or mw_info['naam_schoon'] not in begeleiders: continue
                dn = normaliseer_dienst(extraheer_dienst(
                    str(r.get('Dienst(en) realisatie','') or ''))) or ''
                if dn.lstrip('x').strip() not in doel: continue

                # Staat inwerker al ingepland op die dag?
                inwerker_bezet = False
                for _, r2 in dag_df.iterrows():
                    mw2 = zoek_mw(str(r2.get('Naam','')).strip(), lookup)
                    if not mw2 or mw2['naam_schoon'] != kandidaat_ns: continue
                    dn2 = normaliseer_dienst(extraheer_dienst(
                        str(r2.get('Dienst(en) realisatie','') or ''))) or ''
                    if dn2 and dn2 != '-' and not dn2.startswith('x'):
                        inwerker_bezet = True
                    break

                if not inwerker_bezet:
                    meldingen.append({
                        'kandidaat':   actief['naam'],
                        'traject':     traject['naam'],
                        'datum':       datum.strftime('%Y-%m-%d'),
                        'datum_nl':    _datum_nl(datum),
                        'dienst':      dn.lstrip('x').strip(),
                        'begeleider':  mw_info['naam'],
                    })
                    break  # max 1 melding per dag per traject

    return meldingen
