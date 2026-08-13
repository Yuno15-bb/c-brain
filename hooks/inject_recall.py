#!/usr/bin/env python3
"""inject_recall — hook UserPromptSubmit : rappel automatique de mémoire pertinente.

À CHAQUE message de l'utilisateur, lance brain_recall sur la demande et injecte en
contexte les 2-3 fiches du C Brain les plus pertinentes (nom + description + chemin).
→ Le bon souvenir remonte tout seul, au bon moment, sans charger tout MEMORY.md.

C'est le payoff du Volet 2 · Horizon 1 : un retriever branché, pas juste une CLI.

Garde-fous :
  - n'injecte QUE si la pertinence dépasse un seuil (pas de bruit sur les prompts triviaux),
  - silencieux et non bloquant : sort toujours 0, n'injecte rien en cas de souci,
  - léger : pointeurs (nom/desc/chemin), pas le contenu intégral → coût en tokens minime.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall
except Exception:
    recall = None
try:
    from context_usage import read_context_tokens
except Exception:
    def read_context_tokens(_transcript_path):
        return None

sys.path.insert(0, os.path.expanduser("~/brain-v3-lab/lab"))
try:
    import moteur                      # le dispatcher : LUI seul décide
except Exception:
    moteur = None

TOP_K = 3
MIN_SCORE = 4.0   # en dessous : pas assez pertinent → on n'injecte rien
CONTEXT_WARN_TOKENS = 300_000


def context_notice(data):
    """Alerte indépendante du rappel ; aucune erreur ne doit bloquer le prompt."""
    try:
        used = read_context_tokens((data or {}).get("transcript_path"))
    except Exception:
        return None
    if used is None or used <= CONTEXT_WARN_TOKENS:
        return None
    return (
        f"<contexte> {used//1000}k tokens — privilégie les lectures ciblées, "
        "propose /clear si le chantier change. </contexte>"
    )


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    lines = []
    notice = context_notice(data)
    if notice:
        lines.append(notice)

    prompt = (data.get("prompt") or data.get("user_prompt") or "").strip()

    # UNE seule décision, prise ici. Avant, ce hook appelait BM25 en dur : le
    # pointeur `state/MOTEUR` ne commandait rien, et « basculer » se réduisait à
    # réécrire un fichier que personne ne lisait.
    choix = moteur.choisir() if moteur is not None else {"moteur": "v2"}

    results = []
    if len(prompt) >= 8:
        if choix["moteur"] == "v3":
            try:
                from serveur import demander
                r = demander(prompt, k=TOP_K)
                # Un index périmé ou un repli ne sont PAS le moteur V3 : plutôt
                # que d'injecter en se faisant passer pour lui, on redescend.
                if r.get("perime") or r.get("repli"):
                    choix = {"moteur": "v2", "demande": "v3",
                             "raison": r.get("perime") or r.get("repli")}
                else:
                    results = [(None, {"name": os.path.basename(f)[:-3], "path": f,
                                       "desc": ""}) for f in (r.get("resultats") or [])]
            except Exception:
                choix = {"moteur": "v2", "demande": "v3", "raison": "V3 injoignable"}
        if choix["moteur"] == "v2" and recall is not None:
            try:
                brut = recall.BM25(recall.load_corpus()).search(prompt, TOP_K)
            except Exception:
                brut = []
            results = [(s, d) for s, d in brut if s >= MIN_SCORE]

    if choix.get("force"):
        # Le contournement du gate ne doit jamais passer inaperçu.
        lines.append("<brain-moteur> ⚠️ MOTEUR V3 FORCÉ, gate court-circuité "
                     "(BRAIN_GATE_FORCE_VERT) — mode test uniquement </brain-moteur>")

    if results:
        lines += ["<brain-recall> Fiches du C Brain potentiellement pertinentes "
                  "pour cette demande (lis-les si utile, ignore sinon) :"]
        for s, d in results:
            desc = (" — " + d["desc"][:120]) if d["desc"] else ""
            lines.append(f"- {d['name']} ({d['path']}){desc}")
        lines.append("</brain-recall>")

    # stdout d'un hook UserPromptSubmit = contexte ajouté à la session
    if lines:
        print("\n".join(lines))

    # boucle de vérité (H3) : journaliser ce qui a été REMONTÉ (pour mesurer l'utilité)
    if results:
        try:
            import time
            sid = data.get("session_id") or ""
            log = os.path.join(recall.BRAIN, "state", "recall_log.jsonl")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                for s, d in results:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid,
                                        "path": d["path"],
                                        "score": round(s, 2) if s is not None else None,
                                        "moteur": choix["moteur"]},
                                       ensure_ascii=False) + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
