#!/usr/bin/env python3
"""brain_anticipate — proactif (Volet 2 · Horizon 4) : le cerveau devance le besoin.

Au lieu d'attendre qu'on l'interroge, il scanne les fiches pour les POINTS DE REPRISE
(« REPRENDRE ICI », « PROCHAIN », « point de reprise »…) et surface, par récence, là où
tu en étais et quelle était la prochaine étape — au démarrage de session (hook SessionStart)
ou via `brain next`.

Le cerveau qui tend la fiche AVANT qu'on la cherche. Sort toujours 0.
"""
import os, re, sys, glob

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
SKIP_PARTS = (".git", "node_modules", "capsule", "sessions/archive", "corpus", "audits")
# marqueurs forts (vrais points de reprise) puis faibles (todo génériques)
STRONG = re.compile(r"(REPRENDRE ICI|POINT DE REPRISE|À REPRENDRE|REPRENDRE"
                    r"|PROCHAINE ÉTAPE|RESTE À FAIRE)", re.I)
# ⚠️ « À FAIRE » NU ATTRAPE DU FRANÇAIS ORDINAIRE. Le motif était `À FAIRE\b` : il matchait
# « un simple repomix suffit-il À FAIRE auditer un produit », et `audit-pack-outillage` — une
# fiche qui dit « TRANCHÉ, plus rien à faire » — portait le badge ↻ pour cette phrase-là.
# En français « à faire » est un verbe courant ; il ne vaut comme marqueur de tâche que s'il
# est PRÉSENTÉ comme tel : en tête de ligne, en titre, en puce, ou suivi de deux-points.
# (« RESTE À FAIRE » reste attrapé par STRONG, qui passe en premier.)
WEAK = re.compile(r"(PROCHAIN[E]?\b|TODO\b|NEXT\b"
                  r"|À FAIRE\s*[:：]"
                  r"|^[ \t]*(?:[#>\-*•]+[ \t]*)*À FAIRE\b)", re.I | re.M)
# Combien de reprises on met en avant. UN SEUL chiffre pour tout le système : le message de
# démarrage de session le lit, et le badge ↻ de la planète aussi (`graph_export.py`) — sinon la
# carte allume des points que le Brain ne propose pas, et l'inverse.
TOP_REPRISES = 4


def _ligne_de(text, m):
    """La ligne entière qui porte le marqueur."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    return text[start: end if end != -1 else len(text)]


NIE = re.compile(r"(n'est plus|n’est plus|ne sont plus|plus un\b|plus de\b|aucun\b|"
                 # « plus rien à faire » : le marqueur trouvé est « à faire », donc le « à » est
                 # DANS le match et la fenêtre d'avant se termine par « rien » tout court —
                 # `rien à` ne pouvait jamais y correspondre. Trouvé le 2026-08-14 sur
                 # `audit-pack-outillage`, qui portait le badge ↻ en disant « TRANCHÉ — plus
                 # rien à faire ». Un motif de négation doit être écrit contre le marqueur
                 # qu'il annule, pas contre la phrase telle qu'on l'imagine.
                 r"rien à\b|rien\b|pas de\b|jamais de\b)", re.I)


def _annule(text, m):
    """Deux façons dont un marqueur n'en est pas un — les deux constatées le 2026-08-13,
    le jour même où deux décisions ont été consignées proprement :

    1. BARRÉ (`~~À reprendre~~`) : c'est une pierre tombale, pas une tâche. La fiche
       motion/GSAP, marquée abandonnée le matin, ressortait en tête des reprises le soir.
    2. NIÉ (« ce n'est plus un reste à faire ») : écrire qu'une chose est close la faisait
       détecter comme ouverte. La fiche des pins, fermée par décision de l'auteur, se
       proposait comme prochaine tâche — en citant la phrase qui disait le contraire.

    Une fiche BIEN rédigée est celle qui souffrait le plus : c'est ce qui rend ce filtre
    non négociable.
    """
    ligne = _ligne_de(text, m)
    if "~~" in ligne:
        return True
    avant = ligne[: m.start() - (text.rfind("\n", 0, m.start()) + 1)]
    # Les 4 derniers MOTS, pas les 40 derniers caractères : une négation porte sur ce qui
    # la suit immédiatement. Fenêtre trop large, « Réglé le lot A ; RESTE À FAIRE : le lot B »
    # serait annulé à tort ; trop étroite, le marqueur faible « à faire » de la même phrase
    # que le marqueur fort déjà annulé repasse dessous — c'est ce qui a fait échouer la
    # première écriture de ce filtre.
    return bool(NIE.search(" ".join(avant.split()[-4:])))


def best_marker(text):
    """Privilégie un marqueur FORT ; à défaut un faible. Prend la DERNIÈRE occurrence
    (les points de reprise sont en général en fin de fiche), en sautant les marqueurs
    barrés."""
    for motif in (STRONG, WEAK):
        hits = [m for m in motif.finditer(text) if not _annule(text, m)]
        if hits:
            return hits[-1]
    return None


def snippet(text, m):
    """~160 caractères autour du marqueur, sur une ligne."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    if end == -1:
        end = len(text)
    line = text[start:end].strip()
    return re.sub(r"\s+", " ", line)[:180]


def collect():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # skip par SEGMENT de dossier (pas substring : sinon une fiche projet « capsule-… »
        # serait sautée à tort, ratant son point de reprise). cf. [[scan-skip-par-segment-pas-substring]]
        # ETAT-DES-PROJETS.md est un TABLEAU DE BORD généré, pas une fiche de travail :
        # il contient « ce qu'il faut reprendre », donc il se détectait lui-même et
        # squattait la première place des reprises (2026-08-13). Même statut que MEMORY.md.
        if rel in ("MEMORY.md", os.path.join("projects", "ETAT-DES-PROJETS.md")) \
                or any(part in rel.split(os.sep) for part in SKIP_PARTS):
            continue
        zone = rel.split(os.sep)[0]
        if zone not in ("projects",):     # les reprises vivent dans les fiches projet
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        m = best_marker(txt)
        if m:
            name = re.search(r"^name:\s*(.+)$", txt, re.M)
            out.append({"path": rel, "mtime": os.path.getmtime(p),
                        "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
                        "reprise": snippet(txt, m)})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def main():
    items = collect()[:TOP_REPRISES]
    mode_hook = "--hook" in sys.argv
    if not items:
        # En HOOK, ne rien dire : un tronc vide ne doit pas ajouter une ligne à
        # chaque prompt. En COMMANDE, le dire — `brain next` est une commande
        # d'affichage, et une commande d'affichage qui n'imprime rien ne se
        # distingue pas d'une commande cassée. C'est exactement ce silence que
        # le §8 du selftest sort en rouge sur un tronc neuf, où n'avoir aucun
        # point de reprise est l'état NORMAL.
        if not mode_hook:
            print("🧭 Aucun point de reprise en attente.")
        return
    if mode_hook:
        print("<brain-reprises> Points de reprise en attente (tes fiches projet, "
              "du plus récent au plus ancien) — propose de continuer si pertinent :")
    else:
        print("🧭 Reprises en attente :\n")
    for it in items:
        if mode_hook:
            print(f"- {it['name']} ({it['path']}) : {it['reprise']}")
        else:
            print(f"  • {it['name']}  ({it['path']})")
            print(f"      ↳ {it['reprise']}")
    if mode_hook:
        print("</brain-reprises>")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
