#!/usr/bin/env python3
"""quota_probe — la sonde de crédit : « est-ce que je peux dépenser MAINTENANT ? »

Pourquoi elle existe (2026-08-13, demande de l'auteur) : le garde-fou quota posait un
délai d'attente DEVINÉ à partir du message d'erreur (1 h, 2 h, 4 h… cf.
[[account-quota-resilience]]). Ce délai ne peut pas savoir que l'utilisateur vient de
RECHARGER son plafond ou de CHANGER DE COMPTE. Résultat vécu ce matin : plafond
relevé à 08:35, mais la maintenance restait gelée jusqu'à 09:32 pour rien, et il
a fallu effacer le marqueur à la main.

Le principe : ne plus DEVINER, DEMANDER. Une requête d'un seul token porte les
en-têtes `anthropic-ratelimit-unified-*` qui donnent l'état exact du compte et
l'heure exacte de reset.

Coût mesuré : 22 tokens d'entrée + 1 de sortie sur Haiku ≈ 0,00003 $. Sondée
toutes les 15 min, une journée entière de blocage coûte moins d'un centime — à
comparer au relancement à l'aveugle d'un agent complet (~1 $ le coup), qui est
précisément la boucle morte que le recul progressif avait dû éteindre.

D'où la séparation à garder en tête si on touche à ce fichier :
  - la SONDE est gratuite  → cadence fixe (15 min), elle peut se répéter ;
  - l'AGENT coûte cher     → il ne part QUE sur un feu vert observé, jamais sur
    l'expiration d'un délai supposé.

Usage en ligne de commande (lisible, c'est l'observable du contrôle n°2) :
    python3 quota_probe.py
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.anthropic.com/v1/messages"
MODELE = "claude-haiku-4-5-20251001"      # le moins cher : la sonde ne juge pas, elle teste l'accès
KEYCHAIN = "Claude Code-credentials"
TIMEOUT = 20

# L'API OAuth de Claude Code exige ce premier bloc système, sinon elle refuse le jeton.
SYSTEME = "You are Claude Code, Anthropic's official CLI for Claude."


def _jeton() -> str:
    """Le jeton OAuth du compte actif, lu dans le Keychain. Jamais journalisé."""
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN, "-w"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return ""
        return json.loads(out.stdout)["claudeAiOauth"]["accessToken"]
    except Exception:
        return ""


def empreinte_compte() -> str:
    """Empreinte du compte ACTIF, dérivée du jeton — pas le jeton lui-même.

    Signal immédiat et gratuit : l'auteur change de compte → le jeton change → cette
    empreinte change. Plus fiable que de lire l'accountUuid d'un transcript
    (cf. account_fingerprint dans brain_guard), qui ne bouge qu'après qu'une
    session ait déjà tourné sur le nouveau compte."""
    t = _jeton()
    return hashlib.sha256(t.encode()).hexdigest()[:12] if t else ""


def _entetes_limites(headers) -> dict:
    """Les compteurs unifiés, en clair. Absents = plan/route sans limite déclarée."""
    d = {}
    for h in headers:
        hl = h.lower()
        if hl.startswith("anthropic-ratelimit-unified-"):
            d[hl.replace("anthropic-ratelimit-unified-", "")] = headers[h]
    return d


def sonde() -> dict:
    """Une requête d'un token. Renvoie un verdict exploitable :

      {"ok": bool,          # True = une vraie requête vient de PASSER, on peut dépenser
       "http": int|None,    # code HTTP (429 = refusé, 401 = jeton périmé, None = réseau)
       "motif": str,        # lisible par un humain
       "reset": float|None, # epoch exact du retour, donné par l'API (plus de devinette)
       "limites": {...},    # compteurs bruts (5h, 7d, overage…)
       "empreinte": str,    # compte sondé
       "ts": float}

    `ok` vaut True sur HTTP 200 même si l'en-tête `unified-status` dit "rejected" :
    c'est exactement l'état de ce matin — fenêtre 5 h épuisée MAIS overage actif,
    donc les requêtes passent. Ce qui compte n'est pas ce que le compteur annonce,
    c'est qu'une requête réelle vient d'aboutir. (Contrôle n°2 : l'observable est
    la requête qui passe, pas le compteur qui commente.)"""
    base = {"ok": False, "http": None, "motif": "", "reset": None,
            "limites": {}, "empreinte": "", "ts": time.time()}
    jeton = _jeton()
    if not jeton:
        base["motif"] = "jeton illisible (Keychain verrouillé ou compte déconnecté)"
        return base
    base["empreinte"] = hashlib.sha256(jeton.encode()).hexdigest()[:12]

    corps = json.dumps({
        "model": MODELE,
        "max_tokens": 1,
        "system": [{"type": "text", "text": SYSTEME}],
        "messages": [{"role": "user", "content": "."}],
    }).encode()
    req = urllib.request.Request(API, data=corps, method="POST", headers={
        "authorization": "Bearer " + jeton,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "content-type": "application/json",
    })
    try:
        r = urllib.request.urlopen(req, timeout=TIMEOUT)
        base.update(ok=True, http=r.status, motif="crédit disponible",
                    limites=_entetes_limites(r.headers))
    except urllib.error.HTTPError as e:
        lim = _entetes_limites(e.headers)
        try:
            msg = json.loads(e.read())["error"]["message"][:200]
        except Exception:
            msg = f"HTTP {e.code}"
        base.update(http=e.code, motif=msg, limites=lim)
        if e.code == 401:
            # jeton périmé : ce n'est PAS un verdict sur le crédit. On ne débloque
            # pas, mais on ne resserre rien non plus — le CLI rafraîchira le jeton.
            base["motif"] = "jeton périmé (401) — sonde sans verdict"
    except Exception as e:
        base["motif"] = f"réseau injoignable ({type(e).__name__})"
        return base

    for cle in ("reset", "5h-reset", "7d-reset"):
        if cle in base["limites"]:
            try:
                base["reset"] = float(base["limites"][cle])
                break
            except Exception:
                pass
    return base


def _pct(v):
    try:
        return f"{float(v) * 100:.0f} %"
    except Exception:
        return str(v)


if __name__ == "__main__":
    v = sonde()
    print("crédit disponible :", "OUI" if v["ok"] else "NON",
          f"(HTTP {v['http']}) — {v['motif']}")
    lim = v["limites"]
    if lim:
        print("compte", v["empreinte"], "—", "overage actif" if lim.get("overage-in-use") == "true" else "overage inactif")
        for fen, nom in (("5h", "fenêtre 5 h"), ("7d", "fenêtre 7 j"), ("overage", "overage")):
            u, s, rs = lim.get(f"{fen}-utilization"), lim.get(f"{fen}-status"), lim.get(f"{fen}-reset")
            if u is None and s is None:
                continue
            quand = time.strftime("%d/%m %H:%M", time.localtime(float(rs))) if rs else "?"
            print(f"  {nom:<12} {_pct(u):>6}  {s or '':<16} repart {quand}")
    sys.exit(0 if v["ok"] else 7)
