"""Unit tests for arcade mode (plain asserts).

    cd multiagent && python3 tests_arcade.py        (pytest also works)

Each test installs the arcade rules on a fresh game and uninstalls afterwards, so the
Berkeley defaults are never left patched (test_default_rules_untouched checks that).
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import arcadeRules as ar                      # noqa: E402
import layout as layoutmod                    # noqa: E402
import pacman                                 # noqa: E402
from game import Agent, Configuration, Directions   # noqa: E402

N, S, E, W = Directions.NORTH, Directions.SOUTH, Directions.EAST, Directions.WEST


class Null:
    def initialize(self, d, isBlue=False): pass
    def update(self, d): pass
    def finish(self): pass
    def pause(self): pass
    def draw(self, s): pass
    def updateDistributions(self, d): pass
    def checkNullDisplay(self): return True


class Idle(Agent):
    def getAction(self, state):
        return Directions.STOP


def newgame(level=1, name='originalClassic', frames=4):
    ar.install(pacman, level, frames)
    lay = layoutmod.getLayout(name)
    ghosts = [ar.ArcadeGhostTeam(i + 1) for i in range(lay.getNumGhosts())]
    game = pacman.ClassicGameRules(30).newGame(lay, Idle(), ghosts, Null(), quiet=True)
    return game.state


def place(state, i, tile, direction=Directions.STOP):
    state.data.agentStates[i].configuration = Configuration((float(tile[0]), float(tile[1])), direction)


def teardown():
    ar.uninstall()


def run(fn):
    try:
        fn()
    finally:
        teardown()


# ---------------------------------------------------------------- tables
def test_dossier_tables():
    assert ar.levelRow(1)[:5] == (80, 90, 75, 50, 40)
    assert ar.levelRow(2)[2] == 85 and ar.levelRow(5)[2] == 95 and ar.levelRow(21)[0] == 90
    assert [ar.frightSeconds(l) for l in range(1, 21)] == [6, 5, 4, 3, 2, 5, 2, 2, 1, 5, 2, 1, 1, 3, 1, 1, 0, 1, 0, 0]
    assert ar.frightSeconds(25) == 0
    assert ar.scheduleSeconds(1)[:7] == [7, 20, 7, 20, 5, 20, 5]
    assert ar.scheduleSeconds(3)[5] == 1033 and ar.scheduleSeconds(7)[0] == 5
    assert ar.pxPerRound(80, 1) == 1.0           # 80 % = exactly one pixel per frame
    assert ar.personalDotLimit(2, 1) == 30 and ar.personalDotLimit(3, 2) == 50 and ar.personalDotLimit(3, 3) == 0


# ---------------------------------------------------------------- targeting
def test_targeting_formulas():
    pac = (10, 10)
    assert ar.blinkyTarget(pac) == (10, 10)
    assert ar.pinkyTarget(pac, E) == (14, 10)
    assert ar.pinkyTarget(pac, S) == (10, 6)
    assert ar.pinkyTarget(pac, N) == (6, 14)                 # overflow bug: 4 up AND 4 left
    assert ar.pinkyTarget(pac, N, bug=False) == (10, 14)
    # Inky: pivot 2 ahead of Pac-Man, vector from Blinky doubled
    assert ar.inkyTarget(pac, E, (8, 10)) == (16, 10)         # pivot (12,10); 2*pivot - blinky
    assert ar.inkyTarget(pac, W, (10, 4)) == (6, 16)          # pivot (8,10)
    assert ar.inkyTarget(pac, N, (10, 4)) == (6, 20)          # bug pivot (8,12)
    assert ar.inkyTarget(pac, N, (10, 4), bug=False) == (10, 20)
    # Clyde: >= 8 tiles targets Pac-Man, else his corner
    corner = (0, -2)
    assert ar.clydeTarget((10, 18), pac, corner) == pac       # exactly 8 away
    assert ar.clydeTarget((10, 17), pac, corner) == corner    # 7 away
    assert ar.clydeTarget((16, 16), pac, corner) == pac       # sqrt(72) > 8
    # tie order up, left, down, right
    assert ar.chooseExit([E, S, W, N], (5, 5), (5, 5)) == N   # all neighbours equidistant -> up first
    assert ar.chooseExit([E, S], (5, 5), (5, 5)) == S
    assert ar.chooseExit([N, E], (5, 5), (9, 5)) == E


def test_personality_agents_use_formulas():
    state = newgame()
    place(state, 0, (6, 1), N)
    state.data.agentStates[0].configuration = Configuration((6.0, 1.0), N)
    assert ar.ArcadePinky(2).chaseTarget(state) == ar.pinkyTarget((6, 1), N)
    assert ar.ArcadeBlinky(1).chaseTarget(state) == (6, 1)
    blinky = ar.tileOf(state.getGhostPosition(1))
    assert ar.ArcadeInky(3).chaseTarget(state) == ar.inkyTarget((6, 1), N, blinky)
    # scatter: every ghost heads for its own corner
    assert ar.globalMode(state) == 'scatter'
    lay = state.data.layout
    assert ar.ArcadePinky(2).target(state) == ar.scatterCorner(1, lay.width, lay.height)


# ---------------------------------------------------------------- pen and eyes
def test_house_detected_and_blinky_outside():
    state = newgame()
    h = ar.CFG.house
    assert h is not None and h.center == (13, 13) and h.exitTile == (13, 15)
    modes = [ar.ghostMode(state, i) for i in range(1, 5)]
    assert modes[0] == 'active' and modes[2:] == ['house', 'house'] and modes[1] == 'exit'   # Pinky limit 0 -> leaves at once
    assert state.getGhostPosition(1) == (13.0, 15.0)


def _eat(state, i):
    ghost = state.data.agentStates[i]
    place(state, 0, ar.tileOf(ghost.configuration.pos))
    state.data._eaten = [False] * state.getNumAgents()
    pacman.GhostRules.checkDeath(state, 0)


def test_eyes_return_and_respawn_with_cooldown():
    state = newgame()
    # let Blinky be frightened and eaten in a far corridor
    place(state, 1, (1, 5), E)
    ar._frighten(state)
    assert state.data.agentStates[1].arcade['frightened'] and state.data.agentStates[1].scaredTimer > 0
    before = state.data.scoreChange
    _eat(state, 1)
    assert state.data.scoreChange - before == 200
    assert ar.ghostMode(state, 1) == 'eyes' and state.data.agentStates[1].scaredTimer == 0
    # eyes are harmless: Pac-Man standing on them does not die
    pacman.GhostRules.checkDeath(state, 0)
    assert not state.data._lose
    # walk the eyes home through legal actions only
    place(state, 0, (1, 1))
    rounds, seen_exit_tile, modes = 0, False, []
    while rounds < 400:
        legal = state.getLegalActions(1)
        assert legal, 'ghost must always have a legal action'
        state = state.generateSuccessor(1, legal[0])
        m = ar.ghostMode(state, 1)
        modes.append(m)
        rounds += 1
        if m == 'active':
            break
    assert modes[0] == 'eyes' and 'exit' in modes and modes[-1] == 'active', modes
    assert rounds > 10, 'eaten ghost must take time to return (no instant respawn): %d rounds' % rounds
    # revived at the exit tile above the left side of the door, then heads left
    assert state.getGhostPosition(1) == (13.0, 15.0)
    assert state.getLegalActions(1) == [W]


def test_eyes_speed_and_door_closed_to_hunters():
    state = newgame()
    h = ar.CFG.house
    # active ghosts and Pac-Man may not enter the door cells
    place(state, 2, h.exitTile, N)
    state.data.agentStates[2].arcade['mode'] = 'active'
    state.data.agentStates[2].arcade['force'] = None
    assert S not in state.getLegalActions(2)
    place(state, 0, h.exitTile)
    assert S not in state.getLegalActions(0)
    assert ar._pct(state, 1) == ar.levelRow(1)[2]
    state.data.agentStates[1].arcade['mode'] = 'eyes'
    assert ar._pct(state, 1) == ar.EYES_PCT


# ---------------------------------------------------------------- clock
def test_scatter_chase_timer_pauses_during_fright():
    state = newgame()
    a = ar.arcadeOf(state)
    start = a['phaseLeft']
    place(state, 0, (1, 1))
    s1 = state.generateSuccessor(0, Directions.STOP)
    a1 = ar.arcadeOf(s1)
    assert abs((start - a1['phaseLeft']) - ar.CFG.frames) < 1e-9          # ticks while not frightened
    ar._frighten(s1)
    left = a1['phaseLeft']
    s2 = s1.generateSuccessor(0, Directions.STOP)
    assert ar.arcadeOf(s2)['phaseLeft'] == left, 'schedule must pause while frightened'
    assert ar.arcadeOf(s2)['frightLeft'] == ar.frightSeconds(1) * ar.FPS - ar.CFG.frames
    # fright runs out -> schedule resumes
    ar.arcadeOf(s2)['frightLeft'] = 1.0
    s3 = s2.generateSuccessor(0, Directions.STOP)
    assert ar.arcadeOf(s3)['frightLeft'] == 0 and not any(
        s3.data.agentStates[i].arcade['frightened'] for i in range(1, 5))
    s4 = s3.generateSuccessor(0, Directions.STOP)
    assert ar.arcadeOf(s4)['phaseLeft'] < left


def test_mode_switch_reverses_ghosts_and_flips_phase():
    state = newgame()
    a = ar.arcadeOf(state)
    a['phaseLeft'] = 1.0                     # scatter ends this round
    place(state, 0, (1, 1))
    s1 = state.generateSuccessor(0, Directions.STOP)
    assert ar.globalMode(s1) == 'chase'
    assert ar.arcadeOf(s1)['phaseLeft'] > 19 * ar.FPS
    assert s1.data.agentStates[1].arcade['rev']
    assert ('mode', 'chase') in ar.arcadeOf(s1)['events']
    # the reversal is the ghost's only legal move at its next tile centre
    place(s1, 1, (13, 15), W)
    assert s1.getLegalActions(1) == [E]


def test_frightened_start_reverses_and_scores_reset():
    state = newgame()
    place(state, 1, (6, 5), N)
    ar._frighten(state)
    assert state.data.agentStates[1].arcade['rev']
    assert state.getLegalActions(1) == [S]
    assert ar.globalMode(state) == 'frightened'


# ---------------------------------------------------------------- scoring
def test_score_escalation_200_400_800_1600_and_reset():
    state = newgame()
    for i in range(1, 5):
        state.data.agentStates[i].arcade['mode'] = 'active'
    ar._frighten(state)
    gains = []
    for i in range(1, 5):
        place(state, i, (1, 1))
        state.data.scoreChange = 0
        _eat(state, i)
        gains.append(state.data.scoreChange)
    assert gains == [200, 400, 800, 1600], gains
    ar._frighten(state)                                  # next energizer: back to 200
    for i in range(1, 5):
        state.data.agentStates[i].arcade['mode'] = 'active'
    ar._frighten(state)
    for i in (2, 3, 4):
        place(state, i, (1, 5 + i))                       # keep the others out of Pac-Man's tile
    place(state, 1, (1, 1))
    state.data.scoreChange = 0
    _eat(state, 1)
    assert state.data.scoreChange == 200


def test_dot_energizer_scores_and_pacman_stalls():
    state = newgame()
    a = ar.arcadeOf(state)
    dots0 = state.getNumFood()
    x, y = next((x, y) for x in range(state.data.layout.width) for y in range(state.data.layout.height)
                if state.data.food[x][y])
    state.data.scoreChange = 0
    ar._consume((x, y), state)
    assert state.data.scoreChange == 10 and a['stall'] == 1 and state.getNumFood() == dots0 - 1
    cap = state.getCapsules()[0]
    state.data.scoreChange = 0
    ar._consume(cap, state)
    assert state.data.scoreChange == 50 and a['stall'] == 4
    # stall frames eat into movement: 4 pending frames = one whole 4-frame round standing still
    place(state, 0, (1, 1), E)
    state.data.food = state.data.food.copy()
    for x in range(1, 6):
        state.data.food[x][1] = False
    s2 = state.generateSuccessor(0, E)
    assert s2.getPacmanPosition() == (1.0, 1.0) and ar.arcadeOf(s2)['stall'] == 0
    s3 = s2.generateSuccessor(0, E)
    assert abs((s3.getPacmanPosition()[0] - 1.0) * ar.PX - 4.5) < 1e-9     # then 90 % (frightened Pac-Man, the energizer is active): 4.5 px


def test_pacman_speed_is_80_percent_on_level_1():
    state = newgame()
    place(state, 0, (1, 1), E)
    state.data.food = state.data.food.copy()
    for x in range(1, 13):
        state.data.food[x][1] = False                # no dots on the row: nothing to slow him down
    s = state
    for _ in range(20):
        s = s.generateSuccessor(0, E)
    # 20 rounds * 4 frames * 1.25 px * 80 % = 80 px = exactly 10 tiles
    assert abs(s.getPacmanPosition()[0] - 11.0) < 1e-9, s.getPacmanPosition()


# ---------------------------------------------------------------- framework contract
def test_ghosts_always_return_legal_actions():
    random.seed(1)
    state = newgame()
    state.data.agentStates[0].arcade['stall'] = 0
    agents = [ar.ArcadeGhostTeam(i + 1) for i in range(4)]
    for _ in range(600):
        if state.isWin() or state.isLose():
            break
        legal = state.getLegalActions(0)
        state = state.generateSuccessor(0, legal[0] if len(legal) == 1 else random.choice(legal))
        for i in range(1, 5):
            if state.isWin() or state.isLose():
                break
            legal = state.getLegalActions(i)
            act = agents[i - 1].getAction(state)
            assert act in legal, (i, act, legal)
            state = state.generateSuccessor(i, act)


def test_default_rules_untouched():
    ar.uninstall()
    assert pacman.GhostRules.getLegalActions.__module__ == 'pacman'
    assert pacman.TIME_PENALTY == 1
    assert not hasattr(pacman.GameState, 'arcade')
    lay = layoutmod.getLayout('mediumClassic')
    from ghostAgents import RandomGhost
    game = pacman.ClassicGameRules(30).newGame(lay, Idle(), [RandomGhost(1), RandomGhost(2)], Null(), quiet=True)
    assert not hasattr(game.state.data.agentStates[0], 'arcade')


def test_no_house_layout_still_plays():
    state = newgame(name='capsuleClassic')
    modes = [ar.ghostMode(state, i) for i in range(1, state.getNumAgents())]
    assert all(m in ('active', 'exit', 'house') for m in modes)
    s = state
    for _ in range(40):
        if s.isLose() or s.isWin():
            break
        s = s.generateSuccessor(0, Directions.STOP)
        for i in range(1, s.getNumAgents()):
            if s.isLose():
                break
            s = s.generateSuccessor(i, ar.ArcadeGhostTeam(i).getAction(s))


def _wrap(fn):
    def wrapped():
        run(fn)
    wrapped.__name__ = fn.__name__
    return wrapped


names = sorted(n for n in list(globals()) if n.startswith('test_'))
for _n in names:                       # every test gets a clean uninstall, also under pytest
    globals()[_n] = _wrap(globals()[_n])

if __name__ == '__main__':
    for n in names:
        globals()[n]()
        print('ok  ', n)
    print('%d arcade tests passed' % len(names))
