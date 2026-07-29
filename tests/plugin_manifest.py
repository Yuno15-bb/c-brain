#!/usr/bin/env python3
"""
plugin_manifest.py — la moitié « plugin » du paquet ne se vérifie pas à l'œil.

Un hook dont le chemin n'existe plus n'échoue pas bruyamment : Claude Code
signale une erreur de chargement que l'utilisateur fait défiler, et la mémoire
arrête simplement d'enregistrer. C'est le pire mode de panne de ce projet —
silencieux, et invisible jusqu'au jour où l'on cherche une fiche qui n'a jamais
été écrite.

Donc : chaque chemin ${CLAUDE_PLUGIN_ROOT} de hooks.json doit désigner un
fichier réellement présent, les deux manifestes doivent se lire, et la version
du plugin doit coller au dernier tag — parce que Claude Code distribue les
mises à jour sur cette chaîne SEULE, et qu'une version en retard laisse les
utilisateurs sur une vieille copie pendant que chaque note de version affirme
le contraire.

Lancement : python3 tests/plugin_manifest.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARCHE = ROOT / ".claude-plugin" / "marketplace.json"
HOOKS = ROOT / "hooks" / "hooks.json"

PATH_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)")


def echec(msg):
    print(f"❌ {msg}")
    return 1


def _branche():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def dernier_tag():
    """Le plus récent tag de la FAMILLE de cette branche.

    Les tags ne sont pas rangés par branche : `git tag` les rend tous. Comparer
    la version française au dernier tag anglais ferait échouer `fr` en
    permanence, pour une raison qui n'a rien à voir avec un défaut.
    """
    fr = _branche() == "fr"
    motif = r"v\d+\.\d+\.\d+-fr" if fr else r"v\d+\.\d+\.\d+"
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-creatordate"],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for t in out.split():
        if re.fullmatch(motif, t):
            return t
    return None


def main():
    erreurs = 0

    for f in (PLUGIN, MARCHE, HOOKS):
        if not f.exists():
            erreurs += echec(f"absent : {f.relative_to(ROOT)}")
            continue
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            erreurs += echec(f"{f.relative_to(ROOT)} n'est pas du JSON valide : {e}")
    if erreurs:
        return 1

    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    marche = json.loads(MARCHE.read_text(encoding="utf-8"))

    # Chaque script visé par un hook doit exister.
    for rel in sorted(set(PATH_RE.findall(HOOKS.read_text(encoding="utf-8")))):
        rel = rel.rstrip('\\"')
        if not (ROOT / rel).exists():
            erreurs += echec(f"hooks.json désigne un fichier qui n'existe pas : {rel}")

    # Chaque skill doit déclarer une description. Claude Code décide d'invoquer
    # un skill à partir de cette seule ligne : sans elle le skill se charge,
    # n'apparaît nulle part d'utile, et ne se déclenche jamais — sans erreur,
    # le même no-op silencieux que ce projet rencontre sans arrêt.
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    for sk in skills:
        tete = sk.read_text(encoding="utf-8")[:800]
        fm = re.match(r"^---\n(.*?)\n---", tete, re.S)
        desc = re.search(r"^description:\s*(\S.*)$", fm.group(1), re.M) if fm else None
        if not desc:
            erreurs += echec(f"{sk.relative_to(ROOT)} n'a pas de description — il ne se déclencherait jamais")
        elif len(desc.group(1)) < 40:
            erreurs += echec(f"{sk.relative_to(ROOT)} a une description trop maigre pour router : "
                             f"{desc.group(1)!r}")

    noms = [p.get("name") for p in marche.get("plugins", [])]
    if plugin.get("name") not in noms:
        erreurs += echec(f"marketplace.json ne liste pas le plugin {plugin.get('name')!r} "
                         f"(il liste {noms})")

    # Le verrou de version. publish.sh écrit ce champ depuis le tag ; si les deux
    # se séparent, les utilisateurs cessent de recevoir les mises à jour sans une
    # seule erreur. EN RETARD = panne ; EN AVANCE = normal — publish.sh met le
    # manifeste à jour et le committe juste AVANT de créer le tag, donc entre ces
    # deux instants le fichier a légitimement une version d'avance.
    tag = dernier_tag()
    if tag:
        def parts(v):
            return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        if parts(plugin.get("version", "0")) < parts(tag):
            erreurs += echec(f"la version de plugin.json est {plugin.get('version')!r}, EN RETARD "
                             f"sur le dernier tag {tag}. La mise à jour ne serait jamais proposée.")

    if erreurs:
        return 1
    print(f"✅ manifestes de plugin cohérents — c-brain {plugin.get('version')}, "
          f"{len(set(PATH_RE.findall(HOOKS.read_text(encoding='utf-8'))))} script(s) de hook, "
          f"{len(skills)} skill(s) capables de se déclencher")
    return 0


if __name__ == "__main__":
    sys.exit(main())
