#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""
recall_cache.py — un index périmé est pire qu'un index lent.

Le corpus de rappel est caché, parce que le reconstruire à chaque prompt coûtait
243 ms sur un tronc de 241 fiches et croissait linéairement. Ce cache achète de
la vitesse et introduit la seule panne que ce projet ne peut pas se permettre :
servir des fiches qui ne disent plus ce qu'elles disaient. Rien n'en serait
visible — le rappel continuerait de répondre, avec assurance, à côté.

Donc chaque façon dont le tronc peut changer doit l'invalider, et chaque façon
dont le cache peut mal tourner doit dégrader en « plus lent », jamais en
« faux » et jamais en « planté » — ceci tourne dans un hook, et un hook qui
lève emporte le rappel de la session avec lui.

Lancement : python3 tests/recall_cache.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = 0


def check(label, condition, detail=""):
    global FAILS
    if condition:
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label}{'  — ' + detail if detail else ''}")
        FAILS += 1


def load_recall(trunk):
    spec = importlib.util.spec_from_file_location(
        "brain_recall", ROOT / "hooks" / "brain_recall.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.BRAIN = str(Path(trunk).resolve())
    return mod


def main():
    tmp = Path(tempfile.mkdtemp(prefix="cbrain-cache-"))
    try:
        trunk = tmp / "trunk"
        (trunk / "lessons").mkdir(parents=True)
        m = load_recall(trunk)
        cache = trunk / "state" / "recall-index.json"

        def note(name, body):
            # L'empreinte lit le mtime à la nanoseconde, mais un test qui écrit
            # deux fois dans le même tic resterait un mensonge sur un système de
            # fichiers à horodatage plus grossier. Une courte pause le tient honnête.
            time.sleep(0.01)
            (trunk / "lessons" / f"{name}.md").write_text(
                f"---\nname: {name}\ndescription: \"d\"\n---\n{body}\n", encoding="utf-8")

        note("alpha", "cache deployment stale artifact")

        first = m.load_corpus()
        check("le fichier de cache est écrit", cache.exists())
        second = m.load_corpus()
        check("un cache valide renvoie un corpus identique", first == second)

        print("▸ chaque façon de changer le tronc doit l'invalider")
        note("alpha", "offline queue outbox retry resync")
        docs = m.load_corpus()
        check("fiche modifiée → nouveaux tokens servis",
              "outbox" in docs[0]["tokens"],
              "le cache a servi le contenu précédent de la fiche")

        note("beta", "token refresh expiry")
        check("fiche ajoutée → indexée", len(m.load_corpus()) == 2)

        (trunk / "lessons" / "beta.md").unlink()
        check("fiche supprimée → retirée", len(m.load_corpus()) == 1)

        # Un renommage garde mtime et taille : seul le chemin change. Si
        # l'empreinte ignorait les chemins, le rappel continuerait de désigner un
        # fichier qui n'existe plus, et la fiche s'ouvrirait sur rien.
        (trunk / "lessons" / "alpha.md").rename(trunk / "lessons" / "renamed.md")
        docs = m.load_corpus()
        check("fiche renommée → nouveau chemin servi",
              docs and docs[0]["path"].endswith("renamed.md"),
              f"sert encore {docs[0]['path'] if docs else 'rien'}")

        print("▸ un cache cassé dégrade en lent, jamais en faux ni en mort")
        cache.write_text("{ not json at all", encoding="utf-8")
        check("cache corrompu → reconstruit", len(m.load_corpus()) == 1)

        # On plante dans le cache une version que le code refuse ET un contenu
        # qui ne peut venir que de lui. Une assertion sur le NOMBRE de fiches
        # passerait dans les deux cas — ce contrôle plus faible a laissé passer
        # une mutation tout en restant vert.
        import json as _json
        stale = _json.loads(cache.read_text(encoding="utf-8"))
        stale["version"] = 0
        stale["docs"] = [{"path": "lessons/ghost.md", "name": "SHOULD-NOT-BE-SERVED",
                          "desc": "", "tokens": ["ghost"]}]
        cache.write_text(_json.dumps(stale), encoding="utf-8")
        served = {d["name"] for d in m.load_corpus()}
        check("version de cache ancienne → jetée, pas servie",
              "SHOULD-NOT-BE-SERVED" not in served,
              "un cache écrit sous d'autres règles de tokenisation a été servi tel quel")

        os.chmod(trunk / "state", 0o500)          # dossier d'état en lecture seule
        try:
            check("cache non inscriptible → le rappel répond quand même",
                  len(m.load_corpus()) == 1)
        finally:
            os.chmod(trunk / "state", 0o700)

        print()
        if FAILS:
            print(f"❌ {FAILS} échec(s) — le cache de rappel peut servir des fiches périmées")
            return 1
        print("✅ le cache s'invalide à chaque changement du tronc, et n'échoue jamais durement")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
