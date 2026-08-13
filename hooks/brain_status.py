#!/usr/bin/env python3
"""
Statut partagé du C Brain — écrit state/status.json que la capsule lit.
Best-effort : n'échoue jamais, ne bloque jamais un hook.

Activités possibles (mappées à une animation dans la capsule) :
  distilling   ⚗️  extraction de fiches (distillateur)
  gardening    🌱  rangement global de l'arbre (jardinier)
  filing       📁  classement d'une fiche
  correcting   ✏️  correction / masquage de secret
  mapping      🗺️  mise à jour de la carte
  committing   💾  sauvegarde git
  challenging  🔴  mise à l'épreuve (challenger)
  archiving    🍂  tri du froid / archivage (archiviste)
  synthesizing 🕸️  tissage transverse (synthétiseur)
  auditing     🔧  audit/réparation de la machine (mécanicien)
  architecting 🏗️  cohésion globale / ponts inter-domaines (architecte)
  idle             au repos (Tamagotchi qui dort)

Usage CLI :  python3 brain_status.py <state> [activity] [detail]
"""
import json, os, time, sys

STATE_DIR = os.path.expanduser("~/.c-brain/trunk/state")
STATUS = os.path.join(STATE_DIR, "status.json")

def write_status(state, activity=None, detail=None, source=None):
    if source is None:
        source = "agent" if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1" else "you"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": state, "activity": activity, "detail": detail,
                       "source": source, "ts": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, STATUS)  # écriture atomique
    except Exception:
        pass

def touch_status():
    """HEARTBEAT : rafraîchit seulement `ts` du statut courant, sans toucher
    state/activity/detail. Appelé en boucle par auto_maintain pendant les longues
    passes d'agent (un `claude -p` dure des minutes) → la capsule reste « busy »
    tout du long au lieu de clignoter en idle quand sa fenêtre de fraîcheur expire.
    No-op si le fichier n'existe pas / est illisible (best-effort, ne casse rien)."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            cur = json.load(f)
        cur["ts"] = time.time()
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

ETATS = ("busy", "idle")   # le 1er argument est un ÉTAT ; l'activité est le 2e


def show_status():
    """AFFICHE le statut courant. Ne l'écrit JAMAIS.

    Existe depuis le 2026-08-04. Avant : `brain status` appelait `brain_status.py show`,
    or ce fichier n'était qu'un ÉCRIVAIN — « show » était donc pris pour un état et
    ENREGISTRÉ dans status.json. Résultat : la commande phare du CLI n'affichait rien
    (sortie vide, code 0, donc les replis `||` du script `brain` ne partaient pas) et
    corrompait au passage l'état que lit la capsule. Deux fautes en une ligne."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("(aucun statut : state/status.json absent)")
        return 0
    except Exception as e:
        print(f"(statut illisible : {e})")
        return 1
    age = time.time() - (s.get("ts") or 0)
    frais = age < 120
    etat = s.get("state") or "?"
    if etat not in ETATS:
        etat += "  ⚠️ état inconnu (status.json a été corrompu par un appel fautif)"
    print(f"état     : {etat}")
    print(f"activité : {s.get('activity') or '—'}")
    print(f"détail   : {s.get('detail') or '—'}")
    print(f"source   : {s.get('source') or '—'}")
    quand = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.get('ts') or 0))
    print(f"depuis   : {quand}  ({int(age)} s — {'frais' if frais else 'PÉRIMÉ, la capsule le lit comme idle'})")
    return 0


if __name__ == "__main__":
    a = sys.argv
    cmd = a[1] if len(a) > 1 else "idle"
    if cmd == "touch":
        touch_status()
    elif cmd in ("show", "status"):
        sys.exit(show_status())
    elif cmd in ETATS:
        write_status(cmd, a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else None)
    else:
        # REFUSER plutôt qu'enregistrer : n'importe quel mot était accepté comme état, donc
        # une faute de frappe empoisonnait silencieusement le fichier que lit la capsule.
        print(f"état inconnu : {cmd!r} — attendu {' | '.join(ETATS)} (ou touch / show).",
              file=sys.stderr)
        print("Usage : brain_status.py <busy|idle> [activité] [détail]  ·  ... touch  ·  ... show",
              file=sys.stderr)
        sys.exit(2)
