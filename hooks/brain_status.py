#!/usr/bin/env python3
"""
Statut partagé du Claude Brain — écrit state/status.json que la capsule lit.
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

STATE_DIR = os.path.expanduser("~/claude-brain/state")
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

if __name__ == "__main__":
    a = sys.argv
    if len(a) > 1 and a[1] == "touch":
        touch_status()
    else:
        write_status(a[1] if len(a) > 1 else "idle",
                     a[2] if len(a) > 2 else None,
                     a[3] if len(a) > 3 else None)
