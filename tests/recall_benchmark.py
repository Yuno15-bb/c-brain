#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 l'auteur Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""
recall_benchmark.py — le rappel, il est bon à quel point, au juste ?

POURQUOI ÇA EXISTE. Tout le reste de ce dépôt prouve que la mécanique marche :
l'installeur installe, les migrations se rejouent, les manifestes concordent.
Rien ne mesurait si ce POUR QUOI le produit existe — faire remonter la bonne
fiche au bon moment — fait son travail. Un système de mémoire peut avoir l'air
intelligent en se contentant d'injecter beaucoup de contexte, sans que personne
puisse faire la différence.

CE QU'IL MESURE, et contre quelle vérité. Les vraies fiches ne peuvent pas être
livrées : elles sont personnelles. Le corpus est donc SYNTHÉTIQUE et sa vérité
terrain tient par construction.

⚠ LA PREMIÈRE VERSION DE CE FICHIER NOTAIT 1.00 PARTOUT, et c'était un défaut,
pas un résultat. Elle demandait « lequel de ces 8 thèmes ? », avec des
vocabulaires qui ne se recouvraient pas — une question si facile qu'un mot-clé y
répond, et qui ne dit rien du produit. Un benchmark incapable de mal tourner ne
mesure rien.

La tâche ici est la vraie : trouver LA fiche qui répond, parmi ~120 sœurs du
même thème qui partagent presque tout leur vocabulaire.

  · Chaque fiche porte une SIGNATURE de 4 termes distinctifs — son « fait ».
    Le vivier de signatures est assez petit pour que chaque terme soit réutilisé
    par plusieurs fiches : aucun terme seul n'identifie une fiche, seule la
    combinaison le fait.
  · Une requête paraphrase une fiche : 2 de ses 4 termes de signature (jamais
    les 4), plus 2 mots de son thème, plus un mot vide de sens. Le moteur doit
    intersecter, pas consulter.
  · Les vocabulaires des thèmes SE RECOUVRENT par un vivier technique commun,
    parce que de vraies fiches disent « cache », « file » et « jeton » sur des
    sujets très différents.
  · Les titres ne contiennent jamais les termes de la requête. Ils pèsent ×3, et
    matcher dessus flatterait le score.
  · Les longueurs varient d'un facteur 6, parce que la normalisation de longueur
    de BM25 est exactement le genre de chose qui déraille en silence.

MÉTRIQUES. P@1 / P@3 / P@5 et MRR sont calculés contre UNE fiche correcte, pas
un panier. `useless@3` est la vraie question de l'audit — la part des fiches
injectées qui ne sont ni la réponse ni même son thème, puisque cette part se
paie en contexte à chaque prompt. Latence et tokens injectés sont rapportés à la
valeur réellement livrée (TOP_K=3).

Lancement :
  python3 tests/recall_benchmark.py              # 100 · 500 · 1000 fiches
  python3 tests/recall_benchmark.py --sizes 100  # une seule échelle
  python3 tests/recall_benchmark.py --check      # mode CI : seuils exigés
  python3 tests/recall_benchmark.py --json
"""
import argparse
import importlib.util
import json
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ce que le produit injecte réellement à chaque prompt (hooks/inject_recall.py).
SHIPPED_TOP_K = 3
DESC_BUDGET = 120          # caractères de description injectés par fiche

# Seuils de CI. Volontairement SOUS ce que le moteur obtient aujourd'hui : un
# verrou est là pour attraper une régression, pas pour figer un chiffre qu'une
# amélioration honnête ailleurs pourrait légitimement bouger d'un point.
GATES = {
    "p_at_1": 0.72,             # mesuré 0,79 à 1000 fiches
    "p_at_3": 0.88,             # mesuré 0,93
    "mrr": 0.80,                # mesuré 0,86
    "useless_at_3": 0.30,       # maximum — mesuré 0,24
    "p50_ms": 5.0,              # maximum, par requête — mesuré ~1 ms
    "index_build_ms": 600.0,    # maximum — voir ci-dessous
}

# ⚠ POURQUOI index_build_ms EST VERROUILLÉ. Le hook de rappel tourne à chaque
# prompt, et tant que l'index n'était pas caché il relisait et renotait tout le
# tronc à chaque fois : 233 ms sur le tronc de 241 fiches de l'auteur, ~1,6 s à
# 5000, en croissance linéaire. Ce coût, l'utilisateur le paie à chaque message,
# et aucun test ne l'aurait jamais signalé — le rappel était correct, seulement
# plus lent chaque semaine. La qualité n'est pas la seule chose qui se dégrade
# avec l'échelle.

TOPICS = {
    "cache-deploy": (
        "cache deployment stale artifact browser revalidate purge invalidate "
        "cdn edge served version rollout".split(),
        "a deploy reported as successful still serving the previous build"),
    "offline-queue": (
        "offline queue outbox retry resync connectivity flush pending durable "
        "reconnect drain buffered".split(),
        "writes made without network must survive and resync later"),
    "auth-tokens": (
        "token refresh expiry session credential rotate revoke bearer scope "
        "claim signature issuer".split(),
        "a credential that expires mid-flight and how renewal is handled"),
    "db-migrations": (
        "migration schema column rollback replay idempotent constraint index "
        "backfill downgrade ddl".split(),
        "changing a schema without losing rows or blocking writes"),
    "photo-upload": (
        "photo upload compress thumbnail exif orientation blob multipart "
        "attachment resize gallery".split(),
        "sending images from a device with poor bandwidth"),
    "permissions-rls": (
        "permission policy tenant isolation row grant deny principal "
        "authorization boundary leak".split(),
        "one account must never read another account's rows"),
    "background-jobs": (
        "worker scheduler cron job backlog concurrency lock timeout heartbeat "
        "requeue idle".split(),
        "work that runs without anyone watching it"),
    "ui-layout": (
        "layout viewport breakpoint overflow scroll sticky flex grid spacing "
        "safearea notch".split(),
        "an interface that must hold on a small screen"),
}
TOPIC_NAMES = list(TOPICS)

# Shared, meaningless-on-their-own words. Present everywhere, so a match on them
# carries no signal — this is what stops the corpus from being trivially separable.
FILLER = """
system change value result problem process handle state detail approach method
reason effect number check point moment thing case level order sample content
pattern behaviour issue update record source target output input step branch
""".split()

# Technical words EVERY topic draws on, because real notes about very different
# subjects still say "cache", "retry" and "state". Without this, topics separate
# on vocabulary alone and the benchmark grades a task nobody has.
SHARED_TECH = """
cache retry state sync write read error timeout path config flag log commit
branch file directory hash version client server request response payload
""".split()

# The signature pool. Small on purpose: with ~90 terms and 4 per note, every
# term is reused by many notes at 1000 notes, so no single term identifies
# anything. Only the intersection of two does — which is the actual job.
SIGNATURE_POOL = """
crescent thimble lantern pumice quarry basalt lichen marrow tundra vellum
plinth gantry ferrule sextant ridgeline kilnwork tallow spindle harrow bracken
cobalt gypsum orchard falcon pelican mosaic obelisk cistern trellis granary
alcove bastion citadel dolmen estuary foundry glacier hamlet inlet junction
knoll lagoon meadow nutmeg outcrop paddock quiver ravine saffron thicket
umber viaduct warren yarrow zenith amber birch cedar dune elm fjord grove
heath isle juniper kelp larch moss oak pine quince reed sedge thorn vine
willow yew alder bramble clover dogwood fern gorse hazel ivy laurel myrtle
""".split()


def load_recall():
    """Import the SHIPPED recall module, pointed at the throwaway trunk.

    Loaded by path, not by copying its logic: a benchmark that reimplements the
    thing it measures keeps scoring well after the real code has broken.
    """
    spec = importlib.util.spec_from_file_location(
        "brain_recall", ROOT / "hooks" / "brain_recall.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_corpus(trunk: Path, n_notes: int, rng: random.Random):
    """Write n_notes markdown files.

    Returns (truth, notes) where truth maps a relative path to its topic, and
    notes is the list of (relative path, topic, signature) needed to build a
    query aimed at ONE specific note.
    """
    truth, notes = {}, []
    zones = ["lessons", "projects", "meta", "life"]
    for z in zones:
        (trunk / z).mkdir(parents=True, exist_ok=True)

    for i in range(n_notes):
        topic = TOPIC_NAMES[i % len(TOPIC_NAMES)]
        words, gist = TOPICS[topic]
        neighbour = TOPIC_NAMES[(i % len(TOPIC_NAMES) + 1) % len(TOPIC_NAMES)]
        n_words, _ = TOPICS[neighbour]

        # This note's "fact": 4 terms drawn from a pool small enough that each
        # one is shared with other notes. A retriever must combine them.
        signature = rng.sample(SIGNATURE_POOL, 4)

        length = rng.choice([60, 120, 200, 360])       # 6x spread
        body = []
        for _ in range(length):
            r = rng.random()
            if r < 0.16:
                body.append(rng.choice(signature))     # the fact, repeated
            elif r < 0.38:
                body.append(rng.choice(words))         # its topic
            elif r < 0.50:
                body.append(rng.choice(n_words))       # a neighbour bleeding in
            elif r < 0.72:
                body.append(rng.choice(SHARED_TECH))   # what everyone says
            else:
                body.append(rng.choice(FILLER))

        # The title carries neither the signature nor the topic words: titles
        # are weighted x3, and matching on them would flatter the score.
        slug = f"note-{i:04d}"
        zone = zones[i % len(zones)]
        rel = f"{zone}/{slug}.md"
        (trunk / rel).write_text(
            f"---\nname: {slug}\n"
            f"description: \"{gist}\"\n"
            f"metadata:\n  type: reference\n---\n"
            + " ".join(body) + "\n",
            encoding="utf-8")
        truth[rel] = topic
        notes.append((rel, topic, signature))
    return truth, notes


def build_queries(notes, rng: random.Random, n_queries=200):
    """Each query paraphrases ONE note and is answered by that note alone.

    Two of the note's four signature terms — never all four, so the query is a
    partial recollection, which is what a real one is. Plus two words of its
    topic and one meaningless word, so neither the signature nor the topic is
    sufficient on its own.
    """
    queries = []
    for rel, topic, signature in rng.sample(notes, min(n_queries, len(notes))):
        terms = rng.sample(signature, 2) + rng.sample(TOPICS[topic][0], 2)
        terms.append(rng.choice(FILLER))
        rng.shuffle(terms)
        queries.append((" ".join(terms), rel, topic))
    return queries


def measure(n_notes: int, seed: int = 7):
    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="cbrain-bench-"))
    try:
        trunk = tmp / "trunk"
        trunk.mkdir()
        truth, notes = build_corpus(trunk, n_notes, rng)

        recall = load_recall()
        recall.BRAIN = str(trunk.resolve())            # point it at the fixture

        # Cold: nothing cached, everything read and tokenized from disk.
        t0 = time.perf_counter()
        docs = recall.load_corpus()
        index = recall.BM25(docs)
        build_ms = (time.perf_counter() - t0) * 1000
        assert len(docs) == n_notes, f"corpus chargé : {len(docs)} sur {n_notes}"

        # Warm: what the user actually pays on a prompt when no note changed —
        # which is almost every prompt. The cache must return the SAME corpus.
        t0 = time.perf_counter()
        cached = recall.load_corpus()
        recall.BM25(cached)
        cached_ms = (time.perf_counter() - t0) * 1000
        assert cached == docs, "le cache a renvoyé un corpus différent"

        queries = build_queries(notes, random.Random(seed + 1))
        hits1 = hits3 = hits5 = 0
        rr_total = 0.0
        useless = 0
        injected = 0
        latencies = []

        for q, answer, topic in queries:
            t = time.perf_counter()
            res = index.search(q, 5)
            latencies.append((time.perf_counter() - t) * 1000)

            paths = [d["path"] for _, d in res]
            # Graded against ONE note, not a bucket: the whole point is to find
            # the note that answers, among ~120 siblings that look just like it.
            if paths[:1] == [answer]:
                hits1 += 1
            if answer in paths[:3]:
                hits3 += 1
            if answer in paths[:5]:
                hits5 += 1
            rr_total += next((1 / (i + 1) for i, p in enumerate(paths) if p == answer), 0.0)

            # The audit's real question: of what we INJECT on every prompt, how
            # much is beside the point? A sibling of the right topic is a
            # defensible neighbour; a note from another subject is pure cost.
            for _, d in res[:SHIPPED_TOP_K]:
                if d["path"] != answer and truth.get(d["path"]) != topic:
                    useless += 1
                injected += len(d["name"]) + min(len(d["desc"]), DESC_BUDGET)

        n = len(queries)
        shipped_slots = n * SHIPPED_TOP_K
        latencies.sort()
        return {
            "notes": n_notes,
            "queries": n,
            "p_at_1": hits1 / n,
            "p_at_3": hits3 / n,
            "p_at_5": hits5 / n,
            "mrr": rr_total / n,
            "useless_at_3": useless / shipped_slots,
            "index_build_ms": round(build_ms, 1),
            "index_cached_ms": round(cached_ms, 1),
            "p50_ms": round(latencies[n // 2], 2),
            "p95_ms": round(latencies[int(n * 0.95)], 2),
            # ~4 characters per token: an estimate, and labelled as one.
            "injected_tokens_per_prompt": round(injected / n / 4, 1),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render(rows):
    print(f"🔎 Benchmark de rappel — corpus synthétique, {len(TOPICS)} thèmes, "
          f"vérité terrain par construction\n")
    head = f"{'fiches':>6} {'P@1':>6} {'P@3':>6} {'P@5':>6} {'MRR':>6} " \
           f"{'hors-sujet':>10} {'p50':>8} {'p95':>8} {'index':>9} {'caché':>8} {'tok ctx':>8}"
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{r['notes']:>6} {r['p_at_1']:>6.2f} {r['p_at_3']:>6.2f} "
              f"{r['p_at_5']:>6.2f} {r['mrr']:>6.2f} {r['useless_at_3']:>10.2f} "
              f"{r['p50_ms']:>7.1f}m {r['p95_ms']:>7.1f}m "
              f"{r['index_build_ms']:>8.0f}m {r['index_cached_ms']:>7.0f}m "
              f"{r['injected_tokens_per_prompt']:>8.0f}")
    print(f"\n  hors-sujet = part des {SHIPPED_TOP_K} fiches injectées à chaque "
          f"prompt qui sont à côté du sujet.")
    print(f"  index      = construction à froid, 1er prompt après un changement.")
    print(f"  caché      = ce que coûte un prompt quand rien n'a changé — presque tous.")
    print(f"  tok ctx    = tokens ajoutés par prompt, estimés (~4 car./token).")


def check(rows):
    """Verrou de CI : jugé sur le PLUS GRAND corpus, là où c'est le plus dur."""
    worst = max(rows, key=lambda r: r["notes"])
    fails = []
    for key, gate in GATES.items():
        maxima = ("useless_at_3", "p50_ms", "index_build_ms")
        got = worst[key]
        bad = got > gate if key in maxima else got < gate
        mark = "❌" if bad else "✅"
        sense = "≤" if key in maxima else "≥"
        print(f"  {mark} {key:<14} {got:>7.2f}   (seuil {sense} {gate})")
        if bad:
            fails.append(key)
    print()
    if fails:
        print(f"❌ le rappel a régressé sur : {', '.join(fails)}")
        return 1
    print(f"✅ le rappel tient ses seuils à {worst['notes']} fiches")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[100, 500, 1000])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    rows = [measure(n) for n in sorted(a.sizes)]
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    render(rows)
    if a.check:
        print()
        return check(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
