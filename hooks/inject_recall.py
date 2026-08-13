#!/usr/bin/env python3
"""inject_recall — UserPromptSubmit hook: automatic recall of relevant memory.

On EVERY user message, runs brain_recall on the request and injects the
contexte les 2-3 fiches du C Brain les plus pertinentes (nom + description + chemin).
→ Le bon souvenir remonte tout seul, au bon moment, sans charger tout MEMORY.md.

This is what makes it a wired-in retriever rather than just a CLI.

Garde-fous :
  - injects ONLY when relevance crosses a threshold (no noise on trivial prompts),
  - silencieux et non bloquant : sort toujours 0, n'injecte rien en cas de souci,
  - lightweight: pointers (name/description/path), not full content → minimal token cost.
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
    import moteur                      # the dispatcher: IT alone decides
except Exception:
    moteur = None

TOP_K = 3
MIN_SCORE = 4.0   # below this: not relevant enough → nothing is injected
CONTEXT_WARN_TOKENS = 300_000


def context_notice(data):
    """Warning independent of recall; no error here may ever block the prompt."""
    try:
        used = read_context_tokens((data or {}).get("transcript_path"))
    except Exception:
        return None
    if used is None or used <= CONTEXT_WARN_TOKENS:
        return None
    return (
        f"<context> {used//1000}k tokens — prefer targeted reads, "
        "suggest /clear if the task at hand has changed. </context>"
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

    # ONE decision, taken here. Before, this hook called BM25 directly: the
    # `state/MOTEUR` pointer commanded nothing, and "switching engines" amounted
    # to rewriting a file nobody read.
    choice = moteur.choisir() if moteur is not None else {"moteur": "v2"}

    results = []
    if len(prompt) >= 8:
        if choice["moteur"] == "v3":
            try:
                from serveur import demander
                r = demander(prompt, k=TOP_K)
                # A stale index or a fallback is NOT the V3 engine: rather than
                # inject while passing for it, we step back down.
                if r.get("perime") or r.get("repli"):
                    choice = {"moteur": "v2", "demande": "v3",
                              "raison": r.get("perime") or r.get("repli")}
                else:
                    results = [(None, {"name": os.path.basename(f)[:-3], "path": f,
                                       "desc": ""}) for f in (r.get("resultats") or [])]
            except Exception:
                choice = {"moteur": "v2", "demande": "v3", "raison": "V3 unreachable"}
        if choice["moteur"] == "v2" and recall is not None:
            try:
                raw = recall.BM25(recall.load_corpus()).search(prompt, TOP_K)
            except Exception:
                raw = []
            results = [(s, d) for s, d in raw if s >= MIN_SCORE]

    if choice.get("force"):
        # Bypassing the gate must never go unnoticed.
        lines.append("<brain-engine> ⚠️ V3 ENGINE FORCED, gate short-circuited "
                     "(BRAIN_GATE_FORCE_VERT) — test mode only </brain-engine>")

    if results:
        lines += ["<brain-recall> Notes from your trunk that may be relevant "
                  "for this request (read them if useful, ignore otherwise):"]
        for s, d in results:
            desc = (" — " + d["desc"][:120]) if d["desc"] else ""
            lines.append(f"- {d['name']} ({d['path']}){desc}")
        lines.append("</brain-recall>")

    # a UserPromptSubmit hook's stdout = context added to the session
    if lines:
        print("\n".join(lines))

    # truth loop: log what was SURFACED (so usefulness can be measured)
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
                                        "moteur": choice["moteur"]},
                                       ensure_ascii=False) + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
