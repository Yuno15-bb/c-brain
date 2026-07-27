#!/usr/bin/env python3
"""inject_recall — UserPromptSubmit hook: automatic recall of relevant memory.

On EVERY user message, runs brain_recall on the request and injects the
contexte les 2-3 fiches du Claude Brain les plus pertinentes (nom + description + chemin).
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
        return  # too short to be a real query

    try:
        results = recall.BM25(recall.load_corpus()).search(prompt, TOP_K)
    except Exception:
        return
    results = [(s, d) for s, d in results if s >= MIN_SCORE]
    if not results:
        return

    lines = ["<brain-recall> Notes from your trunk that may be relevant "
             "for this request (read them if useful, ignore otherwise):"]
    for s, d in results:
        desc = (" — " + d["desc"][:120]) if d["desc"] else ""
        lines.append(f"- {d['name']} ({d['path']}){desc}")
    lines.append("</brain-recall>")
    # a UserPromptSubmit hook's stdout = context added to the session
    print("\n".join(lines))

    # truth loop: log what was SURFACED (so usefulness can be measured)
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
