"""Integration tests for the ghost teams (unittest; also runs under pytest).

    python3 -m unittest discover -s tests -v
    python3 tests/test_integration.py

Each (team, layout) game runs in-process through benchmarks.run_benchmark.play_game,
which resets the teams' singleton coordinators and wraps every ghost so that
illegal actions and ghost freezes are recorded.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from benchmarks import run_benchmark as rb          # noqa: E402
from layout_check import check_layout_file, LAYOUT_DIR  # noqa: E402

TEAMS = ['CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam',
         'DirectionalGhost', 'RandomGhost']
LAYOUTS = ['mediumClassic', 'smallClassic', 'originalClassic', 'trappedClassic',
           'demo_corridor_trap', 'demo_pincer_arena', 'demo_capsule_corner',
           'demo_open_field', 'demo_long_loop', 'demo_dead_end_comb']
DEMOS = [l for l in LAYOUTS if l.startswith('demo_')]

MAX_MOVES = 300        # Pac-Man move cap per game (keeps the suite fast)
STALL_TICKS = 30       # ghosts may not stay frozen this long while Pac-Man keeps moving
SEEDS = (1, 2)


class GhostTeamIntegration(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)

    def _play(self, team, layout, seed, pacman='GreedyAgent'):
        return rb.play_game({'pacman': pacman, 'layout': layout, 'ghost': team,
                             'seed': seed, 'max_moves': MAX_MOVES})

    def test_every_team_on_every_layout(self):
        for team in TEAMS:
            for layout in LAYOUTS:
                for seed in SEEDS:
                    with self.subTest(team=team, layout=layout, seed=seed):
                        r = self._play(team, layout, seed)
                        self.assertIsNone(r['error'], r['error'])
                        self.assertEqual(r['illegal_actions'], 0,
                                         'ghost returned an illegal action')
                        self.assertGreater(r['ghost_decisions'], 0)
                        self.assertLess(r['max_frozen_ticks'], STALL_TICKS,
                                        'ghost team frozen for %d ticks while Pac-Man moved'
                                        % r['max_frozen_ticks'])

    def test_game_ends_or_hits_cap_not_hang(self):
        # Every game must either terminate or be stopped by the move cap, never hang.
        for team in TEAMS:
            with self.subTest(team=team):
                r = self._play(team, 'mediumClassic', 7)
                self.assertTrue(r['win'] or r['lose'] or r['capped'])

    def test_search_pacman_vs_coordinated_teams(self):
        for team in ('CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam'):
            for pac in ('ExpectimaxAgent:2', 'AlphaBetaAgent:2'):
                with self.subTest(team=team, pacman=pac):
                    r = self._play(team, 'smallClassic', 3, pacman=pac)
                    self.assertIsNone(r['error'], r['error'])
                    self.assertEqual(r['illegal_actions'], 0)

    def test_singleton_reset_gives_reproducible_games(self):
        # Same seed, same team -> identical outcome (guards coordinator state leaking across games).
        for team in ('CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam'):
            with self.subTest(team=team):
                a = self._play(team, 'mediumClassic', 11)
                b = self._play(team, 'mediumClassic', 11)
                self.assertEqual((a['score'], a['moves']), (b['score'], b['moves']))

    def test_demo_layouts_valid(self):
        for name in DEMOS + ['demo_corridor_trap']:
            with self.subTest(layout=name):
                self.assertEqual(
                    check_layout_file(os.path.join(LAYOUT_DIR, name + '.lay')), [])


class StallDetectorTests(unittest.TestCase):
    """The freeze detector itself must fire on a frozen ghost config."""

    class _G:
        scaredTimer = 0

    class _S:
        def __init__(self, pac, ghosts):
            self.pac, self.ghosts = pac, ghosts

        def getPacmanPosition(self):
            return self.pac

        def getGhostPositions(self):
            return self.ghosts

        def getGhostStates(self):
            return [StallDetectorTests._G() for _ in self.ghosts]

    class _A:
        def getAction(self, state):
            return 'Stop'

    def test_detects_frozen_ghosts(self):
        probe = rb.Probe(max_moves=1000)
        agent = rb._wrap_pacman(self._A(), probe)
        for i in range(50):
            agent.getAction(self._S((i % 5, 1), ((9, 9), (3, 3))))   # Pac-Man moves, ghosts frozen
        self.assertGreaterEqual(probe.frozen_ticks, 40)

    def test_no_false_positive_when_ghosts_move(self):
        probe = rb.Probe(max_moves=1000)
        agent = rb._wrap_pacman(self._A(), probe)
        for i in range(50):
            agent.getAction(self._S((i % 5, 1), ((i, 9), (3, 3))))
        self.assertEqual(probe.frozen_ticks, 0)


class GhostConfigTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, 'multiagent'))
        import ghostConfig
        self.gc = ghostConfig

    def test_roundtrip_and_env(self):
        import tempfile
        cfg = self.gc.GhostConfig()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'c.json')
            cfg.save(p)
            self.assertEqual(self.gc.GhostConfig.load(p), cfg)
            c2 = self.gc.load_config(p, environ={'GHOST_PREDICTION_HORIZON': '9',
                                                  'GHOST_USE_RESERVATION': 'off'})
        self.assertEqual(c2.prediction_horizon, 9)
        self.assertFalse(c2.use_reservation)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            self.gc.GhostConfig.from_dict({'nope': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
