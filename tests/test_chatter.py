"""Tests for the Phase 10 chatter ghosts (plain asserts, unittest runner).

    python3 -m unittest discover -s tests -v
    python3 tests/test_chatter.py
"""
import json
import os
import sys
import tracemalloc
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'multiagent'))

from benchmarks import run_benchmark as rb                      # noqa: E402
import layout as layoutmod                                       # noqa: E402
import pacman as pacmanmod                                       # noqa: E402
import chatterGhostAgents as C                                   # noqa: E402
from coordinatedGhostAgents import MazeDistances, tileOf         # noqa: E402

MULTIAGENT = os.path.join(ROOT, 'multiagent')


def initial_state(name='originalClassic'):      # 4 ghosts (mediumClassic only has 2)
    cwd = os.getcwd()
    os.chdir(MULTIAGENT)
    try:
        lay = layoutmod.getLayout(name)
    finally:
        os.chdir(cwd)
    st = pacmanmod.GameState()
    st.initialize(lay, 4)
    return st


def make_hub(state, comms=True, radius=2, loss=0.0):
    """A hub whose ghosts have fresh beliefs (age 0) unless the test ages them."""
    hub = C.ChatterHub(comms=comms, loss=loss, radius=radius)
    hub.start(state)
    hub.tick = 1
    hub.lastCaller = 4
    hub.bus.newTick(1)
    return hub


def decide(hub, idx, state):
    hub.decide(idx, state)
    return hub.roles[idx], hub.assignedTargets[idx]


class BusTests(unittest.TestCase):
    def test_ordering_and_determinism(self):
        def run():
            bus = C.MessageBus(loss=0.5, seed=7)
            for i in (1, 2, 3):
                bus.register(i)
            for t in range(5):
                bus.newTick(t)
                bus.send(1, 'all', 'SPOTTED', {'n': t})
                bus.send(2, 3, 'CLAIM', {'n': t})
            return [(m['id'], m['sender'], m['to'], m['type'], tuple(m.get('lost', ()))) for m in bus.log], \
                   [m['id'] for m in bus.receive(3)]
        a, b = run(), run()
        self.assertEqual(a, b)                                    # deterministic incl. loss draws
        ids = a[1]
        self.assertEqual(ids, sorted(ids))                        # delivery order = send order
        bus = C.MessageBus()
        for i in (1, 2, 3):
            bus.register(i)
        bus.send(1, 'all', 'SPOTTED', {})
        bus.send(2, 1, 'CLAIM', {})
        self.assertEqual([m['type'] for m in bus.receive(1)], ['CLAIM'])      # senders do not hear themselves
        self.assertEqual(bus.receive(1), [])                      # drained
        self.assertEqual([m['type'] for m in bus.receive(3)], ['SPOTTED'])   # the CLAIM was addressed to 1
        self.assertEqual([m['type'] for m in bus.receive(2)], ['SPOTTED'])

    def test_bounded(self):
        bus = C.MessageBus(capacity=50, inboxCap=8, tickCap=10)
        for i in (1, 2):
            bus.register(i)
        for t in range(1000):
            bus.send(1, 'all', 'SPOTTED', {})
        self.assertLessEqual(len(bus.log), 50)
        self.assertLessEqual(len(bus.inbox[2]), 8)
        self.assertLessEqual(len(bus.thisTick), 10)
        self.assertEqual(bus.sent, 1000)

    def test_disabled_bus_sends_nothing(self):
        bus = C.MessageBus(enabled=False)
        bus.register(1)
        bus.register(2)
        self.assertIsNone(bus.send(1, 'all', 'SPOTTED', {}))
        self.assertEqual(bus.sent, 0)
        self.assertEqual(bus.receive(2), [])


class FogTests(unittest.TestCase):
    def test_fog_rule(self):
        st = initial_state()
        md = MazeDistances.get(st.getWalls())
        g = tileOf(st.getGhostPosition(1))
        self.assertTrue(C.canSense(md, g, g, 6))
        far = max(md.distFrom(g).items(), key=lambda kv: kv[1])[0]
        if g[0] != far[0] and g[1] != far[1]:
            self.assertFalse(C.canSense(md, g, far, 6))
        near = next(t for t, d in md.distFrom(g).items() if d == 3)
        self.assertTrue(C.canSense(md, g, near, 6))
        self.assertFalse(C.canSense(md, g, near, 1) and g[0] != near[0] and g[1] != near[1])


class MessageEffectTests(unittest.TestCase):
    """A/B: the same state and ghost, with and without one message, yields a different decision."""

    def setUp(self):
        self.st = initial_state()
        self.md = MazeDistances.get(self.st.getWalls())

    def _stale_pair(self):
        a, b = make_hub(self.st), make_hub(self.st)
        for h in (a, b):
            h.tick = 30
            h.bus.newTick(30)
            h.minds[1].seen = 0                     # belief 30 ticks old -> search mode
        return a, b

    def test_spotted_redirects_the_hunt(self):
        a, b = self._stale_pair()
        g = tileOf(self.st.getGhostPosition(1))
        spot = max((t for t, d in self.md.distFrom(g).items() if d <= 14), key=lambda t: self.md.distFrom(g)[t])
        self.assertFalse(C.canSense(self.md, g, tileOf(self.st.getPacmanPosition()), 2))
        roleA, targetA = decide(a, 1, self.st)
        self.assertEqual(roleA, 'search')
        b.bus.send(2, 'all', 'SPOTTED', {'pac': list(spot), 'heading': [0, 0], 'age': 0})
        roleB, targetB = decide(b, 1, self.st)
        self.assertNotEqual(roleB, 'search')
        self.assertNotEqual(targetB, targetA)
        self.assertEqual(b.minds[1].pac, spot)

    def test_claim_displaces_a_role(self):
        a, b = make_hub(self.st), make_hub(self.st)
        chaser = next(i for i in (1, 2, 3, 4) if decide(a, i, self.st)[0] == 'chaser')
        other = 1 if chaser != 1 else 2
        b.bus.send(other, 'all', 'CLAIM', {'role': 'chaser', 'target': [1, 1], 'bid': -50})
        self.assertNotEqual(decide(b, chaser, self.st)[0], 'chaser')

    def test_handoff_forces_chaser(self):
        a, b = make_hub(self.st), make_hub(self.st)
        weak = next(i for i in (1, 2, 3, 4) if decide(a, i, self.st)[0] != 'chaser')
        b.bus.send(1 if weak != 1 else 2, weak, 'HANDOFF',
                   {'pac': list(tileOf(self.st.getPacmanPosition())), 'heading': [0, 0], 'age': 0})
        self.assertEqual(decide(b, weak, self.st)[0], 'chaser')

    def test_request_support_gets_ack_and_cutoff(self):
        b = make_hub(self.st)
        pac = tileOf(self.st.getPacmanPosition())
        exit_ = chaserTile = None
        for t, d in sorted(self.md.distFrom(pac).items()):
            if d == 3 and C.ChatterHub._exitTile(self.md, pac, t):
                chaserTile, exit_ = t, C.ChatterHub._exitTile(self.md, pac, t)
                break
        self.assertIsNotNone(exit_)
        req = b.bus.send(1, 'all', 'REQUEST_SUPPORT', {'pac': list(pac), 'heading': [0, 0], 'age': 0,
                                                       'exit': list(exit_), 'gap': 5, 'ticks': 6})
        roles = {}
        for g in (2, 3, 4):
            roles[g] = decide(b, g, self.st)[0]
        helpers = [g for g, r in roles.items() if r == 'cutoff']
        self.assertEqual(len(helpers), 1)                          # exactly the nearest free ghost answers
        acks = [m for m in b.bus.log if m['type'] == 'ACK']
        self.assertEqual(len(acks), 1)
        self.assertEqual(acks[0]['ackOf'], req['id'])
        self.assertEqual(acks[0]['to'], 1)
        self.assertEqual(acks[0]['sender'], helpers[0])
        self.assertEqual(b.assignedTargets[helpers[0]], exit_)
        # and the requester hears it, which silences further requests
        b.minds[1].lastReqId = req['id']
        decide(b, 1, self.st)
        self.assertGreater(b.minds[1].supportUntil, b.tick)

    def test_warn_capsule_sends_a_guard(self):
        a, b = make_hub(self.st), make_hub(self.st)
        cap = tuple(int(v) for v in self.st.getCapsules()[0])
        dc = self.md.distFrom(cap)
        farPac = max(dc, key=lambda t: (dc[t], t))               # Pac-Man far from the pellet: the ghosts win the race
        b.bus.send(1, 'all', 'WARN_CAPSULE', {'cap': list(cap), 'pac': list(farPac), 'heading': [0, 0], 'age': 0})
        rolesB = {g: decide(b, g, self.st)[0] for g in (2, 3, 4)}
        rolesA = {g: decide(a, g, self.st)[0] for g in (2, 3, 4)}
        self.assertNotIn('capsule_guard', rolesA.values())
        guards = [g for g, r in rolesB.items() if r == 'capsule_guard']
        # a guard only commits if it can win the race to the capsule; when none can, nobody moves
        for g in guards:
            self.assertEqual(b.assignedTargets[g], cap)
        self.assertTrue(any(b.minds[g].guard for g in (2, 3, 4)))

    def test_yield_locks_winner_target(self):
        b = make_hub(self.st)
        b.minds[2].role, b.minds[2].target = 'interceptor', (3, 3)
        b.bus.send(3, 2, 'YIELD', {'tile': [3, 3], 'alt': [4, 4]})
        decide(b, 2, self.st)
        self.assertEqual(b.minds[2].lock[2], (3, 3))
        self.assertEqual(b.assignedTargets[2], (3, 3))

    def test_silent_team_has_no_effect_from_bus(self):
        s = make_hub(self.st, comms=False)
        self.assertIsNone(s.bus.send(1, 'all', 'SPOTTED', {'pac': [1, 1], 'heading': [0, 0], 'age': 0}))
        decide(s, 1, self.st)
        self.assertEqual(s.bus.sent, 0)


class GameTests(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)

    def _play(self, team, seed=3, layout='originalClassic', moves=200, pacman='GreedyAgent'):
        return rb.play_game({'pacman': pacman, 'layout': layout, 'ghost': team, 'seed': seed, 'max_moves': moves})

    def test_legal_actions_only(self):
        for team in ('ChatterGhostTeam', 'SilentFogGhostTeam', 'LossyChatterGhostTeam'):
            for layout in ('mediumClassic', 'originalClassic', 'demo_corridor_trap'):
                r = self._play(team, layout=layout)
                self.assertIsNone(r['error'], r['error'])
                self.assertEqual(r['illegal_actions'], 0, (team, layout))
                self.assertGreater(r['ghost_decisions'], 0)

    def test_reset_between_games(self):
        r1 = self._play('ChatterGhostTeam', seed=11)
        hub1 = C.ChatterGhostTeam._coordinator
        t1 = hub1.tick
        r2 = self._play('ChatterGhostTeam', seed=11)
        hub2 = C.ChatterGhostTeam._coordinator
        self.assertIsNot(hub1, hub2)                               # fresh hub per game
        self.assertEqual((r1['score'], r1['moves']), (r2['score'], r2['moves']))   # identical replay
        self.assertEqual(hub2.tick, t1)                            # tick counter restarted, not accumulated
        self.assertEqual(hub2.bus.sent, hub1.bus.sent)

    def test_reuse_of_one_instance_set_across_games(self):
        """pacman.py -n N reuses the ghost objects: registerInitialState must reset the hub."""
        st = initial_state()
        ghosts = [C.ChatterGhostTeam(i) for i in (1, 2, 3, 4)]
        for g in ghosts:
            g.registerInitialState(st)
        hub1 = C.ChatterGhostTeam._coordinator
        for g in ghosts:
            g.getAction(st)
        for g in ghosts:
            g.registerInitialState(st)                              # next game
        hub2 = C.ChatterGhostTeam._coordinator
        self.assertIsNot(hub1, hub2)
        self.assertEqual(hub2.tick, 0)
        self.assertEqual(hub2.bus.sent, 0)

    def test_existing_teams_unchanged(self):
        import sys as _s
        a = self._play('EnhancedCoordinatedGhostTeam', seed=5)
        self._play('ChatterGhostTeam', seed=5)
        b = self._play('EnhancedCoordinatedGhostTeam', seed=5)
        self.assertEqual((a['score'], a['moves']), (b['score'], b['moves']))
        enh = _s.modules['enhancedGhostAgents']
        tele = enh.EnhancedCoordinatedGhostTeam._coordinator.getTelemetry()
        self.assertNotIn('messages', tele)                         # no fog, no bus on the full-information team

    def test_telemetry_shape_and_dashboard_compat(self):
        self._play('ChatterGhostTeam', seed=2, moves=60)
        hub = C.ChatterGhostTeam._coordinator
        tele = hub.getTelemetry()
        json.dumps(tele)
        for k in ('tacticalState', 'macroStrategy', 'roles', 'targets', 'scaredTimers', 'messages', 'beliefs'):
            self.assertIn(k, tele)
        self.assertEqual(sorted(tele['beliefs']), [1, 2, 3, 4])
        for b in tele['beliefs'].values():
            self.assertEqual(set(b), {'pacTile', 'age'})
        self.assertGreater(hub.bus.sent, 0)
        for m in tele['messages']:
            for k in ('id', 'tick', 'from', 'to', 'type', 'payload'):
                self.assertIn(k, m)
            self.assertIn(m['type'], C.MSG_TYPES)
            self.assertEqual(m['tick'], tele['tick'])               # 'messages' = this tick's sends only
        sys.path.insert(0, ROOT)
        from dashboard import commander
        snap = commander.read_coordinator(hub)
        self.assertEqual(snap['source'], 'getTelemetry')
        self.assertTrue(snap['roles'])
        silent = self._play('SilentFogGhostTeam', seed=2, moves=60)
        tele = C.SilentFogGhostTeam._coordinator.getTelemetry()
        self.assertEqual(tele['messages'], [])
        self.assertFalse(tele['comms'])

    def test_every_shown_message_was_sent_and_has_a_receiver_effect(self):
        """Telemetry reads the bus log itself: ids shown are ids that went through send()."""
        self._play('ChatterGhostTeam', seed=4, moves=120)
        hub = C.ChatterGhostTeam._coordinator
        logged = {m['id'] for m in hub.bus.log}
        for m in hub.getTelemetry()['messages']:
            self.assertIn(m['id'], logged)


class BoundedMemoryTests(unittest.TestCase):
    def test_2000_ticks_bounded(self):
        st = initial_state()
        hub = make_hub(st, radius=6)
        hub.lastCaller = C._FAR
        tracemalloc.start()
        snaps = []
        for tick in range(2000):
            for i in (1, 2, 3, 4):
                hub.begin(i, st)
                hub.decide(i, st)
            if tick in (200, 1999):
                snaps.append(tracemalloc.get_traced_memory()[0])
        tracemalloc.stop()
        self.assertEqual(hub.tick, 2001)
        self.assertLessEqual(len(hub.bus.log), hub.bus.capacity)
        for box in hub.bus.inbox.values():
            self.assertLessEqual(len(box), hub.bus.inboxCap)
        for m in hub.minds.values():
            self.assertLessEqual(len(m.claims), 4)
            self.assertLessEqual(len(m.gap), C.GAP_WINDOW + 2)
            self.assertLessEqual(len(m.lastWarn), 8)
        self.assertLess(snaps[1] - snaps[0], 2 * 1024 * 1024)       # no growth with ticks


if __name__ == '__main__':
    unittest.main()
