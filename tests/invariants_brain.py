#!/usr/bin/env python3
"""Invariants du Claude Brain — relations qui doivent rester vraies, pas cas particuliers.

Each test states a RELATION between two halves of the system that, read separately,
semblent justes. Lancer : python3 tests/invariants_brain.py   (rc != 0 si un invariant casse)

Born of a real audit: the challenger's sensor counted `len(coherence.json)`
while the file can hold NON-actionable entries (arbitration notes left by an
agent). The result: a sonnet agent woken every 12 h for nothing, which
preempted the architect — and a check_coherence dying on a KeyError over the same entry.
"""
import json, os, sys, unittest

# Deux racines DISTINCTES, et c'est volontaire :
#  · CODE  — where the hooks to import come from. Follows the file, because the engine
#    peut vivre ailleurs que le tronc (installation par symlinks).
#  · BRAIN — the user's trunk, where the DATA comes from (state/).
#    Always derived from $HOME: writing into the engine would break the installation
#    and be wiped on the first update.
CODE = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BRAIN = os.path.expanduser("~/claude-brain")
sys.path.insert(0, os.path.join(CODE, "hooks"))

MALFORMED = [{"note": "✓ arbitrated, false positive", "note2": "✓ same"}]
REAL_PAIR = [{"a": "x", "b": "y", "sim": 0.9, "ts": 0, "status": "fort recouvrement"}]


class SensorNeverStuck(unittest.TestCase):
    """INVARIANT: an agent is woken only when it has ACTIONABLE work.

    A sensor counting lines rather than units of work never comes back down
    → the agent relights on every cooldown, forever, doing nothing.
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
                         "challenger woken on an entry with no (a,b) pair to arbitrate")

    def test_vraie_paire_reveille_bien_le_challenger(self):
        self.assertTrue(self._has_work(REAL_PAIR),
                        "challenger endormi alors qu'une vraie paire attend un arbitrage")

    def test_capteur_vide_ne_reveille_personne(self):
        self.assertFalse(self._has_work([]))


class CheckCoherenceTolerantAuxVieillesEntrees(unittest.TestCase):
    """INVARIANT: the detector survives any content already present in its own state.

    check_coherence RE-READS coherence.json then writes back to it. If it assumes a
    schema the existing entries do not respect, it dies — silently, because it runs
    detached — and NO overlap is ever detected again.
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
    """INVARIANT: every agent that can wake autonomously is documented as such.

    An agent wired into ORDER runs with --dangerously-skip-permissions. If the docs
    call it "optional, not wired in", nobody knows it can write on its own.
    """

    def test_tout_agent_de_ORDER_est_annonce_dans_le_readme(self):
        import brain_upkeep
        readme = open(os.path.join(BRAIN, "agents", "readme.md"), encoding="utf-8").read()
        bloc = readme.split("## Seconde couche")[-1]
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, bloc,
                          f"{agent} wakes autonomously but is missing from the watch documentation")

    def test_tout_agent_de_ORDER_a_un_modele_et_une_tache(self):
        import brain_upkeep
        for agent in brain_upkeep.ORDER:
            self.assertIn(agent, brain_upkeep.MODEL, f"{agent} has no model → a silent default")
            self.assertIn(agent, brain_upkeep.TASKS, f"{agent} has no mission → KeyError on wake-up")


class ModeleParAgentCoucheUn(unittest.TestCase):
    """INVARIANT: the creative stage (distiller) is never given a weaker model than the
    mechanical one (gardener). A failed distillation loses knowledge PERMANENTLY;
    a failed gardening pass simply replays."""

    RANG = {"haiku": 0, "sonnet": 1, "opus": 2}

    def test_distillateur_au_moins_aussi_fort_que_jardinier(self):
        src = open(os.path.join(BRAIN, "hooks", "auto_maintain.py"), encoding="utf-8").read()
        self.assertIn("MODEL_L1", src, "the model is hardcoded, not configurable per agent")
        ns = {}
        for line in src.splitlines():
            if line.strip().startswith("MODEL_L1"):
                exec(line.strip(), {}, ns)  # noqa: S102
        m = ns["MODEL_L1"]
        self.assertGreaterEqual(self.RANG[m["distiller"]], self.RANG[m["gardener"]],
                                "the distiller (irreversible) runs below the gardener (replayable)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
