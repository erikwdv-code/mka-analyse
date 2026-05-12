"""
MKA Analyse App — startpunt
Dubbelklik op dit bestand (of run: python start.py)
"""
import sys
import os
import json
import threading

# Zorg dat de juiste map in het pad staat
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

GITHUB_RAW = "https://raw.githubusercontent.com/erikwdv-code/mka-analyse/main"
VERSIE_URL = f"{GITHUB_RAW}/version.json"
LOKALE_VERSIE_PAD = os.path.join(BASE_DIR, "version.json")

def laad_lokale_versie():
    try:
        with open(LOKALE_VERSIE_PAD, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"versie": "0.0.0"}

def check_update():
    """Controleer in achtergrond of er een nieuwe versie is."""
    try:
        import urllib.request
        with urllib.request.urlopen(VERSIE_URL, timeout=5) as r:
            remote = json.loads(r.read().decode('utf-8'))
        lokaal = laad_lokale_versie()

        def versie_tuple(v):
            return tuple(int(x) for x in v.split('.'))

        if versie_tuple(remote['versie']) > versie_tuple(lokaal['versie']):
            # Sla remote versie op zodat server hem kan serveren
            update_pad = os.path.join(BASE_DIR, "update_beschikbaar.json")
            with open(update_pad, 'w', encoding='utf-8') as f:
                json.dump(remote, f, ensure_ascii=False)
            print(f"  ✓ Update beschikbaar: versie {remote['versie']}")
        else:
            # Verwijder oude update melding als die er is
            update_pad = os.path.join(BASE_DIR, "update_beschikbaar.json")
            if os.path.exists(update_pad):
                os.remove(update_pad)
            print(f"  ✓ App is up-to-date (versie {lokaal['versie']})")
    except Exception as e:
        print(f"  ℹ Update check overgeslagen ({e})")

from server import start_server

if __name__ == '__main__':
    lokaal = laad_lokale_versie()
    print("=" * 50)
    print(f"  MKA Analyse App — versie {lokaal['versie']}")
    print("  Opent automatisch in je browser...")
    print("  Sluit dit venster om de app te stoppen.")
    print("=" * 50)

    # Check update op de achtergrond
    threading.Thread(target=check_update, daemon=True).start()

    start_server(poort=5757)
