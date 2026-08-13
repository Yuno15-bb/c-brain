#!/usr/bin/env python3
"""Invariants du C Brain — relations qui doivent rester vraies, pas cas particuliers.

Chaque test énonce une RELATION entre deux moitiés du système qui, lues séparément,
semblent justes. Lancer : python3 tests/invariants_brain.py   (rc != 0 si un invariant casse)

Nés de l'audit du 2026-07-10 : le capteur du challenger comptait `len(coherence.json)`
alors que le fichier peut contenir des entrées NON actionnables (notes d'arbitrage
laissées par un agent). Résultat : un agent sonnet réveillé toutes les 12 h pour rien,
qui préemptait l'architecte — et un check_coherence mort en KeyError sur la même entrée.
"""
import json, os, sys, unittest

# BRAIN_HOME rend la suite HERMÉTIQUE (Phase 1 du RFC Brain V3, 2026-08-03).
# Sans elle, SensorNeverStuck écrit dans le VRAI state/coherence.json et le
# restaure ensuite depuis une copie mémoire : un crash entre les deux laisse
# l'état de production écrasé par une valeur de test. Le défaut par défaut reste
# la racine du dépôt, donc `python3 tests/invariants_brain.py` ne change pas.
# Deux racines DISTINCTES, et c'est volontaire :
#  · CODE  — d'où viennent les hooks à importer. Suit le fichier, car le moteur
#    peut vivre ailleurs que le tronc (installation par symlinks).
#  · BRAIN — le tronc de l'utilisateur, d'où viennent les DONNÉES (state/).
#    Toujours dérivé de $HOME : écrire dans le moteur casserait l'installation
#    et serait écrasé à la première mise à jour.
CODE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BRAIN = os.path.expanduser("~/.c-brain/trunk")
sys.path.insert(0, os.path.join(CODE, "hooks"))

MALFORMED = [{"note": "✓ arbitré, faux positif", "note2": "✓ idem"}]
REAL_PAIR = [{"a": "x", "b": "y", "sim": 0.9, "ts": 0, "status": "fort recouvrement"}]


class SensorNeverStuck(unittest.TestCase):
    """INVARIANT : un agent n'est réveillé que s'il a du travail ACTIONNABLE.

    Un capteur qui compte des lignes plutôt que des unités de travail ne redescend
    jamais → l'agent se rallume à chaque cooldown, indéfiniment, sans rien faire.
    """

    def _has_work(self, coherence_content):
        import brain_upkeep
        path = os.path.join(BRAIN, "state", "coherence.json")
        backup = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        try:
            json.dump(coherence_content, open(path, "w", encoding="utf-8"))
            return brain_upkeep.sensor_signal()["challenger"][0]
        finally:
            if backup is not None:
                open(path, "w", encoding="utf-8").write(backup)

    def test_entrees_non_actionnables_ne_reveillent_pas_le_challenger(self):
        self.assertFalse(self._has_work(MALFORMED),
                         "challenger réveillé sur une entrée sans paire (a,b) à arbitrer")

    def test_vraie_paire_reveille_bien_le_challenger(self):
        self.assertTrue(self._has_work(REAL_PAIR),
                        "challenger endormi alors qu'une vraie paire attend un arbitrage")

    def test_capteur_vide_ne_reveille_personne(self):
        self.assertFalse(self._has_work([]))


class CheckCoherenceTolerantAuxVieillesEntrees(unittest.TestCase):
    """INVARIANT : le détecteur survit à tout contenu déjà présent dans son propre état.

    check_coherence RELIT coherence.json puis y réécrit. S'il suppose un schéma que
    les entrées existantes ne respectent pas, il meurt — silencieusement, car il est
    lancé détaché — et plus AUCUN recouvrement n'est jamais détecté.
    """

    def test_pas_de_keyerror_sur_entree_legacy(self):
        import check_coherence
        for flags in (MALFORMED, REAL_PAIR, [], MALFORMED + REAL_PAIR):
            with self.subTest(flags=flags):
                try:
                    pairs = check_coherence.existing_pairs(flags)
                except Exception as e:  # noqa: BLE001
                    self.fail(f"check_coherence casse sur {flags}: {e!r}")
                self.assertIsInstance(pairs, set)


class DocEtCodeDAccord(unittest.TestCase):
    """INVARIANT : tout agent réveillable en autonome est documenté comme tel.

    Un agent branché dans ORDER tourne avec --dangerously-skip-permissions. Si la doc
    le dit « optionnel, non branché », personne ne sait qu'il peut écrire tout seul.
    """

    def test_tout_agent_de_ORDER_est_annonce_dans_le_readme(self):
        import brain_upkeep
        readme = open(os.path.join(BRAIN, "agents", "readme.md"), encoding="utf-8").read()
        bloc = readme.split("## Seconde couche")[-1]
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, bloc,
                          f"{agent} est réveillé en auto mais absent de la doc de la veille")

    def test_tout_agent_de_ORDER_a_un_modele_et_une_tache(self):
        import brain_upkeep
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, brain_upkeep.MODEL, f"{agent} sans modèle → défaut silencieux")
            self.assertIn(agent, brain_upkeep.TASKS, f"{agent} sans mission → KeyError au réveil")


class ModeleParAgentCoucheUn(unittest.TestCase):
    """INVARIANT : l'étage créatif (distillateur) n'est jamais moins bien doté que l'étage
    mécanique (jardinier). Un échec de distillation perd du savoir DÉFINITIVEMENT ;
    un jardinage raté se rejoue."""

    RANG = {"haiku": 0, "sonnet": 1, "opus": 2}

    def test_distillateur_au_moins_aussi_fort_que_jardinier(self):
        src = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        self.assertIn("MODEL_L1", src, "le modèle est codé en dur, non réglable par agent")
        ns = {}
        for line in src.splitlines():
            if line.strip().startswith("MODEL_L1"):
                exec(line.strip(), {}, ns)  # noqa: S102
        m = ns["MODEL_L1"]
        self.assertGreaterEqual(self.RANG[m["distillateur"]], self.RANG[m["jardinier"]],
                                "le distillateur (irréversible) tourne sous le jardinier (rejouable)")


class CarteComposeeSansPollution(unittest.TestCase):
    """INVARIANT : l'index secondaire allège le démarrage sans devenir du savoir."""

    REL_INDEX = os.path.join("lessons", "INDEX.md")

    def test_memory_garde_sa_marge_de_chargement(self):
        import brain_doctor
        size = os.path.getsize(os.path.join(BRAIN, "MEMORY.md"))
        self.assertLessEqual(size, brain_doctor.MEMORY_WARN_BYTES)

    def test_index_structurel_est_exclu_des_moteurs_de_savoir(self):
        import brain_recall
        import brain_topology
        import brain_utility
        import track_read
        self.assertTrue(brain_recall._skip(self.REL_INDEX))
        self.assertIn(self.REL_INDEX, brain_topology.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, brain_utility.STRUCTURAL_MAPS)
        self.assertIn(self.REL_INDEX, track_read.STRUCTURAL_MAPS)

    def test_catalogues_infra_sont_exclus_du_rappel(self):
        import brain_recall
        for rel in ("agents/jardinier.md", "state/a-valider.md",
                    "capsule-v2/README.md", self.REL_INDEX):
            with self.subTest(rel=rel):
                self.assertTrue(brain_recall._skip(rel))


class SignalDeContexte(unittest.TestCase):
    """INVARIANT : l'alerte de contexte ne dépend pas d'un résultat de rappel."""

    def test_somme_usage_partagee(self):
        import context_usage
        self.assertEqual(context_usage.usage_tokens({
            "input_tokens": 10,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 30,
        }), 60)

    def test_alerte_strictement_au_dessus_de_300k(self):
        import inject_recall
        original = inject_recall.read_context_tokens
        try:
            inject_recall.read_context_tokens = lambda _path: 300_000
            self.assertIsNone(inject_recall.context_notice({"transcript_path": "x"}))
            inject_recall.read_context_tokens = lambda _path: 300_001
            self.assertIn("300k tokens", inject_recall.context_notice({"transcript_path": "x"}))
        finally:
            inject_recall.read_context_tokens = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
