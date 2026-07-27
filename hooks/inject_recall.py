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

TOP_K = 3
MIN_SCORE = 4.0   # en dessous : pas assez pertinent → on n'injecte rien


def main():
    if recall is None:
        return
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    prompt = (data.get("prompt") or data.get("user_prompt") or "").strip()
    if len(prompt) < 8:
        return  # trop court pour être une vraie requête

    try:
        results = recall.BM25(recall.load_corpus()).search(prompt, TOP_K)
    except Exception:
        return
    results = [(s, d) for s, d in results if s >= MIN_SCORE]
    if not results:
        return

    lines = ["<brain-recall> Fiches du C Brain potentiellement pertinentes "
             "pour cette demande (lis-les si utile, ignore sinon) :"]
    for s, d in results:
        desc = (" — " + d["desc"][:120]) if d["desc"] else ""
        lines.append(f"- {d['name']} ({d['path']}){desc}")
    lines.append("</brain-recall>")
    # stdout d'un hook UserPromptSubmit = contexte ajouté à la session
    print("\n".join(lines))

    # boucle de vérité (H3) : journaliser ce qui a été REMONTÉ (pour mesurer l'utilité)
    try:
        import time
        sid = data.get("session_id") or ""
        log = os.path.join(recall.BRAIN, "state", "recall_log.jsonl")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            for s, d in results:
                f.write(json.dumps({"ts": int(time.time()), "sid": sid,
                                    "path": d["path"], "score": round(s, 2)},
                                   ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
