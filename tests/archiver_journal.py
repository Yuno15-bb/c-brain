#!/usr/bin/env python3
"""Banc de `tools/archiver-journal.py` — et de chacune de ses assertions, séparément.

    python3 tests/archiver_journal.py              # les contrôles doivent être VERTS
    python3 tests/archiver_journal.py --sabotage   # chacun doit rougir, un par un

POURQUOI CE FICHIER EXISTE (2026-08-14, cf. lessons/une-assertion-tautologique-ne-peut-
pas-rougir.md) : la version précédente de l'outil affichait une garantie « zéro octet
perdu » dont la moitié était vraie par construction. J'avais saboté UN contrôle, il avait
rougi, et j'en avais conclu que le banc entier tenait. C'était faux : un banc à N
assertions demande N sabotages.

Donc la règle du fichier : **CHAQUE assertion a son sabotage nommé**, et `--sabotage`
échoue si l'assertion visée reste verte — comme il échoue si la mutation n'a même pas
été trouvée dans le source (un sabotage qui ne s'applique pas ne prouve rien non plus).

Deux étages :
  · FIXTURES — hermétiques, elles rejouent les incidents réels. Elles tournent toujours.
  · TRONC    — le contrat sur les vraies fiches, avec les verdicts demandés par l'auteur.
               Sautées si la fiche a bougé de place ; jamais écrites (passe à blanc).
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTIL = os.path.join(RACINE, "tools", "archiver-journal.py")

# ── Les fixtures : un incident réel chacune ──────────────────────────────────────

FM = "---\nname: {n}\ndescription: fixture de test\nmetadata:\n  type: project\n---\n\nTête de fiche.\n\n"

# Incident : « ✅ BUILD … FAIT + TESTÉ » dont le CORPS porte des actions ouvertes.
# Trois BUILD de la même famille — c'est ce qui rend l'assertion capable de rougir :
# le garde-fou 2 n'épargne que le plus récent (07-10), donc si le garde-fou 3 tombe,
# le BUILD du 06-19 part au froid avec ses deux actions l'auteur.
BUILD = FM.format(n="fixture-build") + """## ✅ BUILD 0→1→2a FAIT + TESTÉ (2026-06-19) — branche `feat/x` (PAS encore poussée)
Projet posé, 16 tests verts.
- **2 ACTIONS DYLAN avant que ça tourne** : (i) lancer la migration ; (ii) poser la clé.
- **RESTE** : sortie #2 agenda, puis capture Gmail.

## ✅ BUILD ② intermédiaire (2026-06-20) — rien d'ouvert
Étape technique refermée le jour même, plus rien à en tirer.

## ✅ BUILD ③ (2026-07-10) — la chaîne tourne en prod
Dernier état connu.
"""

# Incident : le filtre lexical bloquait sur de la PROSE. Les trois formulations ci-dessous
# ont réellement gelé l'outil sur le tronc (« ne remontent pas encore », « ce qui reste »).
PROSE = FM.format(n="fixture-prose") + """## ⭐ MàJ 2026-06-26 — la carte refaite
Les photos ne remontent pas encore côté serveur ; ce qui reste de l'ancienne carte a été
supprimé, et il n'y a rien à faire de plus (backlog vidé, todo soldé).

## ⭐ MàJ 2026-07-01 — suite
Dernier état.
"""

# Incident : l'archive ÉCRASÉE au 2e passage. Le 2e passage n'a de sens que si la fiche a
# gagné une entrée entre-temps — sinon il n'y a rien de neuf à ranger et le bug dort.
DEUX = FM.format(n="fixture-deux") + """## ⭐ MàJ 2026-06-01 — v1
premier
## ⭐ MàJ 2026-06-02 — v2
deuxième
## ⭐ MàJ 2026-06-03 — v3
troisième
"""
DEUX_SUITE = "## ⭐ MàJ 2026-06-04 — v4\nquatrième\n"


def charger(source=None):
    """Importe l'outil depuis `source` (par défaut le vrai), après avoir posé BRAIN_HOME."""
    spec = importlib.util.spec_from_file_location("aj_%d" % charger.n, source or OUTIL)
    charger.n += 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


charger.n = 0


def bac(fichiers):
    """Crée un faux tronc jetable. JAMAIS le vrai : BRAIN_HOME est posé avant l'import."""
    d = tempfile.mkdtemp(prefix="bac-archiver-")
    os.makedirs(os.path.join(d, "projects", "t"))
    for nom, contenu in fichiers.items():
        open(os.path.join(d, "projects", "t", nom), "w", encoding="utf-8").write(contenu)
    os.environ["BRAIN_HOME"] = d
    return d


def froid(mod, chemin):
    """Rend (titres restés, titres partis au froid) sans rien écrire."""
    brut = open(chemin, encoding="utf-8").read()
    fm, corps = mod.frontmatter(brut)
    _, secs = mod.sections(corps)
    cour, hist, _ = mod.classer(secs)
    return [t for t, _ in cour], [t for t, _ in hist]


def sections_de(txt, mod):
    _, corps = mod.frontmatter(txt)
    _, secs = mod.sections(corps)
    return [b.strip() for _, b in secs]


# ══ LES ASSERTIONS ═══════════════════════════════════════════════════════════════
# Chacune est une fonction autonome : le mode --sabotage les rejoue une par une contre
# un outil muté. Une assertion qui n'a pas su rougir est signalée comme décorative.

def a1_vieux_instantanes_partent(charge):
    """Les 3 vieux POINT DE REPRISE de la fiche bento partent au froid (tronc réel)."""
    f = os.path.join(RACINE, "projects", "<projet>", "<une-fiche-a-plusieurs-points-de-reprise>.md")
    if not os.path.exists(f):
        raise unittest.SkipTest("fiche déplacée")
    _, hist = froid(charge(), f)
    for jour in ("2026-07-02", "2026-07-01", "2026-06-30"):
        assert any("POINT DE REPRISE" in t and jour in t for t in hist), \
            f"le POINT DE REPRISE du {jour} devrait partir au froid — restés : {hist}"


def a2_dernier_instantane_reste(charge):
    """Le POINT DE REPRISE le plus récent (2026-07-03) reste au chaud (tronc réel)."""
    f = os.path.join(RACINE, "projects", "<projet>", "<une-fiche-a-plusieurs-points-de-reprise>.md")
    if not os.path.exists(f):
        raise unittest.SkipTest("fiche déplacée")
    cour, hist = froid(charge(), f)
    assert any("POINT DE REPRISE" in t and "2026-07-03" in t for t in cour), \
        "le dernier point de reprise doit rester : c'est « où on en est »"
    assert not any("2026-07-03" in t and "POINT DE REPRISE" in t for t in hist)


def a3_build_avec_actions_reste_tronc(charge):
    """La section BUILD 0→1→2a de la fiche visée reste (tronc réel).

    ⚠️ Cette assertion est FAIBLE et c'est assumé : dans cette fiche le BUILD est le seul
    de sa famille, donc le garde-fou 2 le protège déjà. Elle reste verte même sans
    garde-fou 3 — elle vérifie le contrat, pas le mécanisme. C'est a3bis qui teste le
    mécanisme. Les garder séparées évite de croire qu'un contrat vert prouve un mécanisme
    vivant.
    """
    f = os.path.join(RACINE, "projects", "<projet>", "<une-fiche-a-sections-datees>.md")
    if not os.path.exists(f):
        raise unittest.SkipTest("fiche déplacée")
    cour, hist = froid(charge(), f)
    assert any("BUILD 0→1→2a" in t for t in cour), "BUILD 0→1→2a doit rester"
    assert not any("BUILD 0→1→2a" in t for t in hist)


def a3bis_action_ouverte_sauve_une_entree_perimee(charge):
    """Fixture : de deux BUILD également périmés, seul celui à action ouverte reste."""
    d = bac({"f.md": BUILD})
    cour, hist = froid(charge(), os.path.join(d, "projects", "t", "f.md"))
    assert any("2026-06-19" in t for t in cour), \
        "le BUILD 06-19 porte « 2 ACTIONS DYLAN » et « RESTE » : il doit rester"
    assert any("2026-06-20" in t for t in hist), \
        "le BUILD 06-20, même famille et même époque mais sans action ouverte, doit partir"


def a4_action_ouverte_reelle_sauve_une_session(charge):
    """c-brain : « Session 2026-07-27 (soir) » reste grâce à `**Reste ouvert…**`."""
    f = os.path.join(RACINE, "projects", "claude-brain", "c-brain-installable-package.md")
    if not os.path.exists(f):
        raise unittest.SkipTest("fiche déplacée")
    cour, hist = froid(charge(), f)
    assert any("Session 2026-07-27 (soir)" in t for t in cour), \
        "elle porte une action ouverte structurelle, elle doit rester"
    assert not any("Session 2026-07-27 (soir)" in t for t in hist)


def a5_la_prose_ne_protege_pas(charge):
    """Fixture : « pas encore », « ce qui reste », « rien à faire » en pleine phrase
    ne sont PAS des actions ouvertes. C'est ce qui bloquait tout l'outil."""
    d = bac({"f.md": PROSE})
    _, hist = froid(charge(), os.path.join(d, "projects", "t", "f.md"))
    assert any("2026-06-26" in t for t in hist), \
        "de la prose contenant les mots-clés ne doit plus geler l'archivage"


def a6_deux_passages_ne_perdent_rien(charge):
    """Fixture : passage → la fiche gagne une entrée → 2e passage. L'archive cumule."""
    d = bac({"f.md": DEUX})
    mod = charge()
    chemin = os.path.join(d, "projects", "t", "f.md")
    assert mod.traiter(chemin, True), "l'outil a refusé d'écrire (une preuve est rouge)"
    open(chemin, "a", encoding="utf-8").write("\n" + DEUX_SUITE)
    assert mod.traiter(chemin, True), "l'outil a refusé d'écrire (une preuve est rouge)"
    archive = open(os.path.join(d, "archive", "f-journal.md"), encoding="utf-8").read()
    for v in ("premier", "deuxième", "troisième"):
        assert v in archive, f"« {v} » a disparu de l'archive au 2e passage"


def a7_rien_ne_disparait(charge):
    """Fixture : après écriture, fiche ∪ archive redonne TOUTES les sections d'origine —
    et quelque chose a bel et bien bougé (sinon l'assertion serait vraie sans rien faire)."""
    d = bac({"f.md": DEUX})
    mod = charge()
    chemin = os.path.join(d, "projects", "t", "f.md")
    avant = sections_de(open(chemin, encoding="utf-8").read(), mod)
    assert mod.traiter(chemin, True), "l'outil a refusé d'écrire (une preuve est rouge)"
    apres = open(chemin, encoding="utf-8").read()
    archive = open(os.path.join(d, "archive", "f-journal.md"), encoding="utf-8").read()
    assert len(sections_de(apres, mod)) < len(avant), \
        "rien n'a quitté la fiche — l'assertion « rien n'est perdu » serait vraie sans travail"
    for s in avant:
        assert s in apres or s in archive, f"section perdue : {s[:60]!r}"


def a8_le_renvoi_ne_sempile_pas(charge):
    """Fixture : deux passages ne laissent qu'UN bloc « ## Historique » dans la fiche."""
    d = bac({"f.md": DEUX})
    mod = charge()
    chemin = os.path.join(d, "projects", "t", "f.md")
    assert mod.traiter(chemin, True), "l'outil a refusé d'écrire (une preuve est rouge)"
    open(chemin, "a", encoding="utf-8").write("\n" + DEUX_SUITE)
    assert mod.traiter(chemin, True), "l'outil a refusé d'écrire (une preuve est rouge)"
    texte = open(chemin, encoding="utf-8").read()
    n = len(re.findall(r'^## Historique$', texte, re.M))
    assert n == 1, f"{n} blocs « ## Historique » empilés dans la fiche"


ASSERTIONS = [
    ("a1", a1_vieux_instantanes_partent),
    ("a2", a2_dernier_instantane_reste),
    ("a3", a3_build_avec_actions_reste_tronc),
    ("a3bis", a3bis_action_ouverte_sauve_une_entree_perimee),
    ("a4", a4_action_ouverte_reelle_sauve_une_session),
    ("a5", a5_la_prose_ne_protege_pas),
    ("a6", a6_deux_passages_ne_perdent_rien),
    ("a7", a7_rien_ne_disparait),
    ("a8", a8_le_renvoi_ne_sempile_pas),
]

# ══ LES SABOTAGES ════════════════════════════════════════════════════════════════
# (nom, texte à trouver dans le source, remplacement, assertions qui DOIVENT rougir)
# Une entrée dont le texte n'est pas trouvé fait échouer le mode : un sabotage qui ne
# s'applique pas laisse le banc « tout vert » et ne prouve strictement rien.
SABOTAGES = [
    ("garde-fou 4 débranché (l'instantané périmé redevient protégé)",
     'FAMILLES_INSTANTANE = {"reprise"}',
     'FAMILLES_INSTANTANE = {"reprise", "_neutralise"}\nFAMILLES_INSTANTANE = set()',
     ["a1"]),

    ("garde-fou 2 débranché (plus rien n'épargne la journée la plus récente)",
     "epargnees |= {i for dt, i in f if dt == recent}",
     "epargnees |= set()",
     ["a2"]),  # a4 n'en dépend pas : sa Session n'est pas la plus récente de sa famille

    ("garde-fou 3 débranché (l'action ouverte ne protège plus rien)",
     "if ouverte and fam not in FAMILLES_INSTANTANE and i not in epargnees}",
     "if False and fam not in FAMILLES_INSTANTANE and i not in epargnees}",
     ["a3bis"]),

    ("le mot RESTE retiré du vocabulaire d'action ouverte",
     "MOTS_OUVERTS = (r'RESTE|RESTENT|",
     "MOTS_OUVERTS = (r'",
     ["a4"]),

    ("marqueur redevenu lexical (plus d'ancrage en début de ligne)",
     "    r'^[ \\t]{0,3}(?:[-*+][ \\t]+)?(?:\\[ \\][ \\t]*)?(?:\\*\\*|__)?[ \\t]*'\n"
     "    r'[^\\w\\s]{0,4}[ \\t]*(?:\\*\\*|__)?[ \\t]*(?:' + MOTS_OUVERTS + r')\\b',",
     "    r'(?:' + MOTS_OUVERTS + r')|pas encore',",
     ["a5"]),

    ("archive réécrite au lieu d'être complétée (le bug du 2e passage)",
     'with open(cible, "a", encoding="utf-8") as f:',
     'with open(cible, "w", encoding="utf-8") as f:',
     ["a6"]),

    ("découpe qui rogne un octet par section",
     "out.append((x.group(0), txt[x.start():fin]))",
     "out.append((x.group(0), txt[x.start():fin - 1]))",
     ["a7"]),

    ("renvoi empilé (l'ancien « ## Historique » n'est plus retiré)",
     'if not (t.strip() == "## Historique" and sentinelle in b)]',
     'if True]',
     ["a8"]),
]


def mode_sabotage():
    source = open(OUTIL, encoding="utf-8").read()
    total, echecs = 0, []
    print("SABOTAGE — chaque assertion doit rougir sur SON sabotage, pas sur celui du voisin\n")
    for nom, avant, apres, cibles in SABOTAGES:
        if avant not in source:
            echecs.append(f"⛔ sabotage jamais appliqué (motif introuvable) : {nom}")
            print(f"⛔ {nom}\n     motif introuvable dans le source — sabotage VIDE")
            continue
        d = tempfile.mkdtemp(prefix="sabot-")
        mute = os.path.join(d, "archiver-journal.py")
        open(mute, "w", encoding="utf-8").write(source.replace(avant, apres, 1))
        print(f"▸ {nom}")
        for cle in cibles:
            fn = dict(ASSERTIONS)[cle]
            total += 1
            try:
                fn(lambda: charger(mute))
            except unittest.SkipTest as e:
                print(f"     {cle} : sautée ({e})")
                total -= 1
            except AssertionError as e:
                motif = (str(e).splitlines() or ["(assertion nue)"])[0][:90]
                print(f"     {cle} : ROUGE ✅  — {motif}")
            except Exception as e:  # noqa: BLE001 — un plantage compte comme rouge, mais on le dit
                print(f"     {cle} : ROUGE (exception {type(e).__name__}) ✅")
            else:
                echecs.append(f"⛔ {cle} reste VERTE sous « {nom} » — assertion décorative")
                print(f"     {cle} : VERTE ⛔ — elle ne surveille pas ce qu'elle prétend")
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{total} couples (sabotage → assertion) éprouvés.")
    # L'inventaire de ce qui N'EST PAS éprouvé vaut autant que la liste des ✅ : sans lui,
    # « tout est rouge » se lit comme « tout est couvert ».
    couvertes = {c for _, _, _, cibles in SABOTAGES for c in cibles}
    nues = [c for c, _ in ASSERTIONS if c not in couvertes]
    if nues:
        print(f"⚠️  sans sabotage, donc non éprouvées : {', '.join(nues)} "
              f"— elles décrivent un contrat, elles ne prouvent aucun mécanisme.")
    for e in echecs:
        print(e)
    return 1 if echecs else 0


class Banc(unittest.TestCase):
    pass


def _fabrique(nom, fn):
    def t(self):
        fn(charger)
    t.__doc__ = fn.__doc__
    return t


for _nom, _fn in ASSERTIONS:
    setattr(Banc, "test_" + _nom + "_" + _fn.__name__, _fabrique(_nom, _fn))


if __name__ == "__main__":
    if "--sabotage" in sys.argv:
        sys.exit(mode_sabotage())
    sys.exit(0 if unittest.main(argv=[sys.argv[0], "-v"], exit=False)
             .result.wasSuccessful() else 1)
