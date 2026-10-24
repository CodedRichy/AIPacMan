# arcadeRules.py
# --------------
# Opt-in "arcade mode": the real Pac-Man's rules on top of the Berkeley framework.
# Nothing here runs unless pacman.py is started with --arcade (or install() is
# called explicitly), so the default Berkeley rules and the autograders are
# untouched.  Sources and deviations are listed in docs/ARCADE_MODE.md; every
# number below is from the Pac-Man Dossier (https://pacman.holenet.info/) unless
# a comment says "NOT IN DOSSIER".
#
# How speed fits the framework
# ----------------------------
# One framework "round" (Pac-Man moves, then every ghost) is ARCADE_FRAMES
# arcade frames (default 4, i.e. 1/15 s).  A tile is 8 px and 100 % speed is
# 1.25 px/frame (Dossier: 75.75757625 px/s at 60.606 Hz), so each agent gets a
# *pixel budget* per round: 1.25 * pct/100 * frames.  Agents move continuously
# (fractional tile coordinates, like Berkeley's half-speed scared ghosts) but
# never past a tile centre in one step; unused budget is carried to the next
# round so the average speed is exact.  Decisions (turns) happen only at tile
# centres, which is where Actions.getPossibleActions already allows them.
# Eyes may travel several tiles in a round because their path is scripted.

import math
import random

from game import Actions, Configuration, Directions, Agent, AgentState
from util import manhattanDistance

FPS = 60.606061            # Dossier: 60.606061 Hz refresh
PX = 8.0                   # pixels per tile
PX_PER_FRAME = 1.25        # 100 % speed (Dossier Table A.1: 75.75757625 px/s)
EYES_PCT = 200             # NOT IN DOSSIER (eaten-eye speed is not stated): assumption
EPS = 1e-6

N, S, E, W = Directions.NORTH, Directions.SOUTH, Directions.EAST, Directions.WEST
TIE_ORDER = [N, W, S, E]               # Dossier: up, left, down, right
CLOCKWISE = [N, E, S, W]               # Dossier: frightened tries clockwise until legal
VEC = {N: (0, 1), S: (0, -1), E: (1, 0), W: (-1, 0), Directions.STOP: (0, 0)}
PERSONALITIES = ['blinky', 'pinky', 'inky', 'clyde']

# ----------------------------------------------------------------------------
# Dossier tables
# ----------------------------------------------------------------------------
# level: (pac, pacFright, ghost, ghostFright, tunnel, elroy1Dots, elroy1Pct, elroy2Dots, elroy2Pct)
_LEVEL_ROWS = {
    1: (80, 90, 75, 50, 40, 20, 80, 10, 85),
    2: (90, 95, 85, 55, 45, 30, 90, 15, 95),
    3: (90, 95, 85, 55, 45, 40, 90, 20, 95),
    4: (90, 95, 85, 55, 45, 40, 90, 20, 95),
    5: (100, 100, 95, 60, 50, 40, 100, 20, 105),
    6: (100, 100, 95, 60, 50, 50, 100, 25, 105),
    7: (100, 100, 95, 60, 50, 50, 100, 25, 105),
    8: (100, 100, 95, 60, 50, 50, 100, 25, 105),
    9: (100, 100, 95, 60, 50, 60, 100, 30, 105),
    10: (100, 100, 95, 60, 50, 60, 100, 30, 105),
    11: (100, 100, 95, 60, 50, 60, 100, 30, 105),
    12: (100, 100, 95, 60, 50, 80, 100, 40, 105),
    13: (100, 100, 95, 60, 50, 80, 100, 40, 105),
    14: (100, 100, 95, 60, 50, 80, 100, 40, 105),
    15: (100, 100, 95, 60, 50, 100, 100, 50, 105),
    16: (100, 100, 95, 60, 50, 100, 100, 50, 105),
    17: (100, 100, 95, 60, 50, 100, 100, 50, 105),   # no fright: fright columns unused
    18: (100, 100, 95, 60, 50, 100, 100, 50, 105),
    19: (100, 100, 95, 60, 50, 120, 100, 60, 105),
    20: (100, 100, 95, 60, 50, 120, 100, 60, 105),
}
_LEVEL_21 = (90, 90, 95, 95, 50, 120, 100, 60, 105)   # level 21+: pac 90 %, ghost 95 %, tunnel 50 %
# frightened seconds, levels 1..20 (0 = ghosts do not turn blue); 21+ = 0
_FRIGHT_SECONDS = [6, 5, 4, 3, 2, 5, 2, 2, 1, 5, 2, 1, 1, 3, 1, 1, 0, 1, 0, 0]
INF = float('inf')


def levelRow(level):
    return _LEVEL_ROWS.get(level, _LEVEL_21 if level > 20 else _LEVEL_ROWS[1])


def frightSeconds(level):
    return _FRIGHT_SECONDS[level - 1] if 1 <= level <= 20 else 0


def scheduleSeconds(level):
    """Scatter/chase durations in seconds: S, C, S, C, S, C, S, C (last is endless)."""
    if level == 1:
        return [7, 20, 7, 20, 5, 20, 5, INF]
    if level <= 4:
        return [7, 20, 7, 20, 5, 1033, 1.0 / 60, INF]
    return [5, 20, 5, 20, 5, 1037, 1.0 / 60, INF]


def personalDotLimit(pers, level):
    """Dossier: Pinky 0; Inky 30 on level 1 then 0; Clyde 60 / 50 / then 0."""
    if pers == 2:
        return 30 if level == 1 else 0
    if pers == 3:
        return 60 if level == 1 else (50 if level == 2 else 0)
    return 0


def forcedExitFrames(level):
    return (3.0 if level >= 5 else 4.0) * FPS      # Dossier: 4 s, 3 s from level 5


# ----------------------------------------------------------------------------
# Configuration singleton and ghost house
# ----------------------------------------------------------------------------
class Config:
    def __init__(self):
        self.installed = False
        self.level = 1
        self.frames = 4          # arcade frames per framework round
        self.overflowBug = True  # Pinky/Inky up-direction overflow bug
        self.house = None
        self.foodTotal = 0
        self.dist = {}           # goal -> BFS distance dict
        self.mod = None
        self.saved = []


CFG = Config()


class House:
    """The ghost pen: interior row, door cells above it, and the exit tile."""

    def __init__(self, y, x0, x1, doorXs):
        self.y, self.x0, self.x1 = y, x0, x1
        self.doorXs = tuple(doorXs)
        self.doorX = min(doorXs)                 # left side of the door (Dossier: eyes return above it)
        self.doorY = y + 1
        self.center = (self.doorX, y)            # where eyes are revived
        self.exitTile = (self.doorX, y + 2)      # tile above the left side of the door
        self.blocked = frozenset([(x, y) for x in range(x0, x1 + 1)] +
                                 [(x, self.doorY) for x in self.doorXs])


def findHouse(layout):
    """Detect a pen: a short walled row holding the ghost starts, closed below, with a door gap above.
    Returns None for layouts without one (most Berkeley layouts); ghosts then start active."""
    walls = layout.walls
    starts = [pos for isPac, pos in layout.agentPositions if not isPac]
    if not starts:
        return None
    ys = set(int(p[1]) for p in starts)
    if len(ys) != 1:
        return None
    y = ys.pop()
    xs = [int(p[0]) for p in starts]
    x0 = x1 = xs[0]
    while x0 - 1 >= 0 and not walls[x0 - 1][y]:
        x0 -= 1
    while x1 + 1 < walls.width and not walls[x1 + 1][y]:
        x1 += 1
    if x1 - x0 + 1 > 12 or not (x0 <= min(xs) and max(xs) <= x1):
        return None
    if y - 1 < 0 or y + 2 >= walls.height:
        return None
    if any(not walls[x][y - 1] for x in range(x0, x1 + 1)):
        return None
    doors = [x for x in range(x0, x1 + 1) if not walls[x][y + 1]]
    if not doors or len(doors) > 3 or doors != list(range(doors[0], doors[0] + len(doors))):
        return None
    if any(walls[x][y + 2] for x in doors):
        return None
    return House(y, x0, x1, doors)


def tileOf(pos):
    return (int(pos[0] + 0.5), int(pos[1] + 0.5))


def _isCenter(pos):
    return abs(pos[0] - round(pos[0])) < EPS and abs(pos[1] - round(pos[1])) < EPS


def _distMap(walls, goal):
    cached = CFG.dist.get(goal)
    if cached is not None:
        return cached
    d = {goal: 0}
    q = [goal]
    for t in q:
        for v in VEC.values():
            n = (t[0] + v[0], t[1] + v[1])
            if n in d or not (0 <= n[0] < walls.width and 0 <= n[1] < walls.height) or walls[n[0]][n[1]]:
                continue
            d[n] = d[t] + 1
            q.append(n)
    CFG.dist[goal] = d
    return d


# ----------------------------------------------------------------------------
# Per-agent / global arcade state (stored on AgentState.arcade, copied with it)
# ----------------------------------------------------------------------------
def _newGlobal(level, nGhosts):
    sched = scheduleSeconds(level)
    return dict(level=level, frames=0.0, phase=0, phaseLeft=sched[0] * FPS, frightLeft=0.0,
                combo=0, dots=0, idle=0.0, stall=0.0, carry=0.0, cnt=(0, 0, 0, 0),
                modeEpoch=0, events=(), foodTotal=CFG.foodTotal)


def _newGhost(i, mode):
    return dict(mode=mode, carry=0.0, rev=False, force=None, frightened=False, rx=False,
                pers=(i - 1) % 4)


def arcadeOf(state):
    """Global arcade dict (lives on Pac-Man's AgentState)."""
    return state.data.agentStates[0].arcade


def globalMode(state):
    A = arcadeOf(state)
    if A['frightLeft'] > 0:
        return 'frightened'
    return 'scatter' if A['phase'] % 2 == 0 else 'chase'


def ghostMode(state, i):
    """'house' | 'exit' | 'active' | 'eyes' for one ghost."""
    return state.data.agentStates[i].arcade['mode']


def ghostStatus(state, i):
    """'house' | 'exit' | 'active' | 'eyes' | 'frightened' (what a renderer should draw)."""
    g = state.data.agentStates[i].arcade
    return 'frightened' if g['frightened'] and g['mode'] != 'eyes' else g['mode']


def dotsLeft(state):
    return state.getNumFood()


def elroyLevel(state):
    """0, 1 or 2 for Blinky (Dossier Table A.1); disabled on mazes with fewer than 150 dots."""
    A = arcadeOf(state)
    if A['foodTotal'] < 150:
        return 0
    row = levelRow(A['level'])
    left = dotsLeft(state)
    return 2 if left <= row[7] else (1 if left <= row[5] else 0)


def snapshot(state):
    """Plain-data view of the arcade state for dashboards and telemetry."""
    A = arcadeOf(state)
    return dict(level=A['level'], mode=globalMode(state), phase=A['phase'],
                phaseLeftSec=None if A['phaseLeft'] == INF else round(max(A['phaseLeft'], 0) / FPS, 2),
                frightLeftSec=round(A['frightLeft'] / FPS, 2), combo=A['combo'], dots=A['dots'],
                elroy=elroyLevel(state),
                ghostModes=[ghostStatus(state, i) for i in range(1, state.getNumAgents())],
                events=[list(e) for e in A['events']])


# ----------------------------------------------------------------------------
# Speed
# ----------------------------------------------------------------------------
def _isTunnel(walls, tile):
    """Side-tunnel stand-in: a 1-wide horizontal corridor within 6 columns of a border.
    (The Berkeley mazes have no wrap-around, so this is only the slow zone.)"""
    x, y = tile
    if not (x <= 5 or x >= walls.width - 6):
        return False
    return walls[x][y + 1] and walls[x][y - 1]


def _pct(state, i):
    A = arcadeOf(state)
    row = levelRow(A['level'])
    if i == 0:
        return row[1] if A['frightLeft'] > 0 else row[0]
    g = state.data.agentStates[i].arcade
    if g['mode'] == 'eyes':
        return EYES_PCT
    if _isTunnel(state.data.layout.walls, tileOf(state.data.agentStates[i].configuration.pos)):
        return row[4]
    if g['mode'] == 'house' or g['mode'] == 'exit':
        return row[2]                 # NOT IN DOSSIER: pen speed assumed equal to normal ghost speed
    if g['frightened']:
        return row[3]
    if g['pers'] == 0 and i == 1:
        lvl = elroyLevel(state)
        if lvl == 2:
            return row[8]
        if lvl == 1:
            return row[6]
    return row[2]


def pxPerRound(pct, frames=None):
    return PX_PER_FRAME * pct / 100.0 * (CFG.frames if frames is None else frames)


# ----------------------------------------------------------------------------
# Movement
# ----------------------------------------------------------------------------
def _toCenterPx(coord, sign):
    if sign > 0:
        d = math.ceil(coord - EPS) - coord
    else:
        d = coord - math.floor(coord + EPS)
    return (d if d > EPS else 1.0) * PX


def _scriptDir(state, i):
    """Direction a scripted ghost (eyes or exiting the pen) takes from its current tile centre, or None if done."""
    g = state.data.agentStates[i].arcade
    h = CFG.house
    t = tileOf(state.data.agentStates[i].configuration.pos)
    walls = state.data.layout.walls
    if g['mode'] == 'exit':
        if h is None:
            return None
        if t[1] == h.y and t[0] != h.doorX:
            return E if h.doorX > t[0] else W
        if t[0] == h.doorX and t[1] < h.exitTile[1]:
            return N
        return None
    goal = h.center if h is not None else tileOf(state.data.agentStates[i].start.pos)
    if t == goal:
        return None
    d = _distMap(walls, goal)
    best, bd = None, None
    for dr in TIE_ORDER:
        v = VEC[dr]
        n = (t[0] + v[0], t[1] + v[1])
        if n in d and (bd is None or d[n] < bd):
            best, bd = dr, d[n]
    return best


def _arrive(state, i):
    """Tile-centre bookkeeping for scripted modes; returns True if the ghost should keep scripted movement."""
    s = state.data.agentStates[i]
    g = s.arcade
    h = CFG.house
    if g['mode'] == 'eyes':
        goal = h.center if h is not None else tileOf(s.start.pos)
        if tileOf(s.configuration.pos) == goal:
            g['frightened'] = False
            s.scaredTimer = 0
            if h is not None:
                g['mode'] = 'exit'                       # revived: leave at once (Dossier)
                g['rx'] = False
            else:
                g['mode'] = 'active'
        return g['mode'] in ('eyes', 'exit')
    if g['mode'] == 'exit':
        if _scriptDir(state, i) is None:
            g['mode'] = 'active'
            g['force'] = E if g['rx'] else W             # Dossier: exits left unless a mode change occurred inside
            g['rx'] = False
            return False
        return True
    return False


def _move(state, i, action, budget):
    """Move agent i along `action` using up to `budget` px. Returns leftover budget."""
    s = state.data.agentStates[i]
    scripted = i != 0 and s.arcade['mode'] in ('eyes', 'exit')
    conf = s.configuration
    guard = 0
    while action != Directions.STOP and budget > EPS and guard < 64:
        guard += 1
        dx, dy = VEC[action]
        x, y = conf.pos
        dist = _toCenterPx(x if dx else y, dx + dy)
        m = min(budget, dist)
        arrived = m >= dist - EPS
        if arrived:
            m = dist
            nx, ny = round(x + dx * m / PX), round(y + dy * m / PX)
            conf = Configuration((float(nx), float(ny)), action)
        else:
            conf = conf.generateSuccessor((dx * m / PX, dy * m / PX))
        budget -= m
        s.configuration = conf
        if not arrived:
            return 0.0
        if scripted:
            keep = _arrive(state, i)
            scripted = i != 0 and s.arcade['mode'] in ('eyes', 'exit')
            if keep and budget > EPS:
                action = _scriptDir(state, i)
                if action is None:
                    return 0.0
                continue
        return budget
    return budget if action != Directions.STOP else 0.0


# ----------------------------------------------------------------------------
# Rules (monkey-patched in by install())
# ----------------------------------------------------------------------------
def _blocked(tile):
    h = CFG.house
    return h is not None and tile in h.blocked


def pacLegalActions(state):
    conf = state.getPacmanState().configuration
    walls = state.data.layout.walls
    acts = Actions.getPossibleActions(conf, walls)
    if _isCenter(conf.pos):
        t = tileOf(conf.pos)
        acts = [a for a in acts if a == Directions.STOP or not _blocked((t[0] + VEC[a][0], t[1] + VEC[a][1]))]
    else:                                   # the arcade lets Pac-Man reverse between tiles
        rev = Actions.reverseDirection(conf.direction)
        acts = [conf.direction, rev] if rev != conf.direction else acts
    return acts


def ghostLegalActions(state, i):
    s = state.getGhostState(i)
    g = s.arcade
    conf = s.configuration
    walls = state.data.layout.walls
    if not _isCenter(conf.pos):
        return [conf.direction]
    mode = g['mode']
    if mode == 'house':
        return [Directions.STOP]
    if mode in ('eyes', 'exit'):
        d = _scriptDir(state, i)
        return [d] if d is not None else [Directions.STOP]
    t = tileOf(conf.pos)
    possible = [a for a in Actions.getPossibleActions(conf, walls) if a != Directions.STOP
                and not _blocked((t[0] + VEC[a][0], t[1] + VEC[a][1]))]
    reverse = Actions.reverseDirection(conf.direction)
    if g['rev'] and reverse in possible:
        return [reverse]
    if g['force'] in possible and g['force'] is not None:
        return [g['force']]
    if reverse in possible and len(possible) > 1:
        possible.remove(reverse)
    return possible or [Directions.STOP]


def pacApply(state, action):
    legal = pacLegalActions(state)
    if action not in legal:
        raise Exception("Illegal action " + str(action))
    s = state.data.agentStates[0]
    A = s.arcade
    A['events'] = ()                                # events describe one round only
    F = CFG.frames
    used = min(A['stall'], F)                       # Dossier: a dot costs 1 frame, an energizer 3
    A['stall'] -= used
    budget = A['carry'] + pxPerRound(_pct(state, 0), F - used)
    A['carry'] = _move(state, 0, action, budget)
    if action == Directions.STOP:
        A['carry'] = 0.0
    nxt = s.configuration.getPosition()
    near = tileOf(nxt)
    if manhattanDistance(near, nxt) <= 0.5:
        CFG.mod.PacmanRules.consume(near, state)
    _clock(state)


def _consume(position, state):
    x, y = position
    A = arcadeOf(state)
    if state.data.food[x][y]:
        state.data.scoreChange += 10
        state.data.food = state.data.food.copy()
        state.data.food[x][y] = False
        state.data._foodEaten = position
        A['dots'] += 1
        A['stall'] += 1
        A['idle'] = 0.0
        _onDot(state)
        if state.getNumFood() == 0 and not state.data._lose:
            state.data._win = True               # Dossier scores no bonus for clearing the maze
    if position in state.getCapsules():
        state.data.capsules.remove(position)
        state.data._capsuleEaten = position
        state.data.scoreChange += 50
        A['stall'] += 3
        _frighten(state)


def _frighten(state):
    A = arcadeOf(state)
    secs = frightSeconds(A['level'])
    A['combo'] = 0                                   # next ghost is worth 200 again
    ev = list(A['events'])
    for i in range(1, state.getNumAgents()):
        s = state.data.agentStates[i]
        g = s.arcade
        if g['mode'] == 'eyes':
            continue
        if g['mode'] == 'active':
            g['rev'] = True                          # Dossier: all ghosts reverse when frightened starts
        if secs > 0:
            g['frightened'] = True
    if secs > 0:
        A['frightLeft'] = secs * FPS
        ev.append(('fright', secs))
    else:
        ev.append(('fright', 0))
    A['events'] = tuple(ev)
    _syncScared(state)


def _syncScared(state):
    A = arcadeOf(state)
    t = int(math.ceil(A['frightLeft'] / CFG.frames)) if A['frightLeft'] > 0 else 0
    for i in range(1, state.getNumAgents()):
        s = state.data.agentStates[i]
        s.scaredTimer = t if s.arcade['frightened'] else 0


def _clock(state):
    """Advance the arcade clock by one round: scatter/chase timer (paused while frightened), fright timer, pen timer."""
    A = arcadeOf(state)
    F = CFG.frames
    A['frames'] += F
    A['idle'] += F
    ev = list(A['events'])
    if A['frightLeft'] > 0:
        A['frightLeft'] -= F
        if A['frightLeft'] <= 0:
            A['frightLeft'] = 0.0
            for i in range(1, state.getNumAgents()):
                state.data.agentStates[i].arcade['frightened'] = False
            ev.append(('fright_end', 0))
    else:
        sched = scheduleSeconds(A['level'])
        A['phaseLeft'] -= F
        while A['phaseLeft'] <= 0 and A['phase'] < len(sched) - 1:
            A['phase'] += 1
            A['phaseLeft'] += sched[A['phase']] * FPS
            A['modeEpoch'] += 1
            ev.append(('mode', 'scatter' if A['phase'] % 2 == 0 else 'chase'))
            for i in range(1, state.getNumAgents()):
                g = state.data.agentStates[i].arcade
                if g['mode'] == 'active':
                    g['rev'] = True                  # Dossier: forced reversal on scatter<->chase
                elif g['mode'] == 'house':
                    g['rx'] = True                   # Dossier: exits right if a mode change happened inside
    A['events'] = tuple(ev)
    if A['idle'] >= forcedExitFrames(A['level']):
        order = _houseOrder(state)
        if order:
            _release(state, order[0])
            A['idle'] = 0.0
    _syncScared(state)


def _houseOrder(state):
    ids = [i for i in range(1, state.getNumAgents()) if state.data.agentStates[i].arcade['mode'] == 'house']
    return sorted(ids, key=lambda i: (state.data.agentStates[i].arcade['pers'], i))


def _release(state, i):
    g = state.data.agentStates[i].arcade
    g['mode'] = 'exit'


def _onDot(state):
    """Personal dot counters (Dossier): only the preferred waiting ghost counts."""
    A = arcadeOf(state)
    order = _houseOrder(state)
    if order:
        p = state.data.agentStates[order[0]].arcade['pers']
        c = list(A['cnt'])
        c[p] += 1
        A['cnt'] = tuple(c)
    _releaseByCounters(state)


def _releaseByCounters(state):
    A = arcadeOf(state)
    while True:
        order = _houseOrder(state)
        if not order:
            return
        p = state.data.agentStates[order[0]].arcade['pers']
        if A['cnt'][p] >= personalDotLimit(p, A['level']):
            _release(state, order[0])
        else:
            return


def ghostApply(state, action, i):
    legal = ghostLegalActions(state, i)
    if action not in legal:
        raise Exception("Illegal ghost action " + str(action))
    s = state.data.agentStates[i]
    g = s.arcade
    if action != Directions.STOP and g['mode'] == 'active':
        if g['rev']:
            g['rev'] = False
        g['force'] = None
    if g['mode'] == 'house' or action == Directions.STOP:
        g['carry'] = 0.0
        return
    budget = g['carry'] + pxPerRound(_pct(state, i))
    g['carry'] = _move(state, i, action, budget)


def ghostDecrement(s):
    # Scared time is driven by the arcade clock (see _syncScared), not by a per-move counter.
    pass


def ghostCheckDeath(state, index):
    pac = state.getPacmanPosition()
    ids = range(1, len(state.data.agentStates)) if index == 0 else [index]
    for i in ids:
        s = state.data.agentStates[i]
        if s.arcade['mode'] in ('house', 'eyes'):
            continue
        if CFG.mod.GhostRules.canKill(pac, s.configuration.getPosition()):
            CFG.mod.GhostRules.collide(state, s, i)


def ghostCollide(state, ghostState, index):
    g = ghostState.arcade
    A = arcadeOf(state)
    if g['frightened']:
        state.data.scoreChange += 200 * (2 ** min(A['combo'], 3))   # 200, 400, 800, 1600
        A['events'] = A['events'] + (('eaten', index, 200 * (2 ** min(A['combo'], 3))),)
        A['combo'] += 1
        g['mode'] = 'eyes'
        g['frightened'] = False
        g['carry'] = 0.0
        g['rev'] = False
        g['force'] = None
        ghostState.scaredTimer = 0
        state.data._eaten[index] = True
    else:
        if not state.data._win:
            state.data._lose = True                  # Dossier gives no score penalty for dying


# ----------------------------------------------------------------------------
# Install / uninstall
# ----------------------------------------------------------------------------
def _initGame(game, lay):
    state = game.state
    CFG.house = findHouse(lay)
    CFG.dist = {}
    CFG.foodTotal = state.getNumFood()
    n = state.getNumAgents() - 1
    pac = state.data.agentStates[0]
    pac.arcade = _newGlobal(CFG.level, n)
    h = CFG.house
    for i in range(1, n + 1):
        s = state.data.agentStates[i]
        s.arcade = _newGhost(i, 'house' if h is not None else 'active')
        if h is not None and i == 1:                # Blinky starts outside, above the door, heading left
            s.arcade['mode'] = 'active'
            start = Configuration((float(h.exitTile[0]), float(h.exitTile[1])), W)
            s.start = start
            s.configuration = start
    _releaseByCounters(state)
    game.rules.initialState = state.deepCopy()


def install(mod, level=1, frames=4, overflowBug=True):
    """Switch `mod` (the pacman module) to arcade rules. Idempotent per process; undo with uninstall()."""
    import game as gamemod
    if CFG.installed:
        uninstall()
    CFG.level, CFG.frames, CFG.overflowBug, CFG.mod = int(level), int(frames), overflowBug, mod
    CFG.saved = []

    def patch(obj, name, new):
        CFG.saved.append((obj, name, obj.__dict__[name]))
        setattr(obj, name, new)

    patch(mod, 'TIME_PENALTY', 0)                   # Dossier has no per-move penalty
    patch(mod.PacmanRules, 'getLegalActions', staticmethod(pacLegalActions))
    patch(mod.PacmanRules, 'applyAction', staticmethod(pacApply))
    patch(mod.PacmanRules, 'consume', staticmethod(_consume))
    patch(mod.GhostRules, 'getLegalActions', staticmethod(ghostLegalActions))
    patch(mod.GhostRules, 'applyAction', staticmethod(ghostApply))
    patch(mod.GhostRules, 'decrementTimer', staticmethod(ghostDecrement))
    patch(mod.GhostRules, 'checkDeath', staticmethod(ghostCheckDeath))
    patch(mod.GhostRules, 'collide', staticmethod(ghostCollide))

    origCopy = gamemod.AgentState.__dict__['copy']

    def copy(self):
        c = origCopy(self)
        a = getattr(self, 'arcade', None)
        if a is not None:
            c.arcade = dict(a)
        return c
    patch(gamemod.AgentState, 'copy', copy)

    origNew = mod.ClassicGameRules.__dict__['newGame']

    def newGame(self, layout, pacmanAgent, ghostAgents, display, quiet=False, catchExceptions=False):
        game = origNew(self, layout, pacmanAgent, ghostAgents, display, quiet, catchExceptions)
        _initGame(game, layout)
        return game
    patch(mod.ClassicGameRules, 'newGame', newGame)
    CFG.installed = True


def uninstall():
    for obj, name, old in reversed(CFG.saved):
        setattr(obj, name, old)
    CFG.saved = []
    CFG.installed = False


# ----------------------------------------------------------------------------
# Targeting (pure functions: unit-tested)
# ----------------------------------------------------------------------------
def aheadTile(pacTile, pacDir, n, bug=True):
    """n tiles ahead of Pac-Man. Dossier: facing up also shifts n tiles left (overflow bug)."""
    v = VEC.get(pacDir, (0, 0))
    t = (pacTile[0] + v[0] * n, pacTile[1] + v[1] * n)
    if bug and pacDir == N:
        t = (t[0] - n, t[1])
    return t


def blinkyTarget(pacTile):
    return tuple(pacTile)


def pinkyTarget(pacTile, pacDir, bug=True):
    return aheadTile(pacTile, pacDir, 4, bug)


def inkyTarget(pacTile, pacDir, blinkyTile, bug=True):
    """Vector from Blinky to the tile 2 ahead of Pac-Man, doubled."""
    p = aheadTile(pacTile, pacDir, 2, bug)
    return (2 * p[0] - blinkyTile[0], 2 * p[1] - blinkyTile[1])


def clydeTarget(clydeTile, pacTile, corner):
    """Dossier: >= 8 tiles (Euclidean) from Pac-Man targets him, closer targets his scatter corner."""
    d2 = (clydeTile[0] - pacTile[0]) ** 2 + (clydeTile[1] - pacTile[1]) ** 2
    return tuple(pacTile) if d2 >= 64 else tuple(corner)


def scatterCorner(pers, width, height):
    """NOT IN DOSSIER (it gives no coordinates): dead-space tiles outside the four maze corners."""
    return [(width - 3, height + 2), (2, height + 2), (width - 1, -2), (0, -2)][pers]


def chooseExit(options, tile, target):
    """Pick the exit whose neighbouring tile is closest (squared Euclidean) to target; ties: up, left, down, right."""
    best, bd = None, None
    for d in TIE_ORDER:
        if d not in options:
            continue
        v = VEC[d]
        n = (tile[0] + v[0], tile[1] + v[1])
        dd = (n[0] - target[0]) ** 2 + (n[1] - target[1]) ** 2
        if bd is None or dd < bd:
            best, bd = d, dd
    return best


def frightenedChoice(options, rng=random):
    """Dossier: pseudo-random start direction, then clockwise until legal."""
    k = rng.randrange(4)
    for j in range(4):
        d = CLOCKWISE[(k + j) % 4]
        if d in options:
            return d
    return options[0]


# ----------------------------------------------------------------------------
# Ghost agents
# ----------------------------------------------------------------------------
class ArcadeDirector:
    """Shared, read-only-ish telemetry for the four ghosts (same attribute names the dashboard reads
    from the coordinated teams: roles, assignedTargets, currentTacticalState, getTelemetry())."""

    def __init__(self):
        self.roles = {}
        self.assignedTargets = {}
        self.modes = {}
        self.currentTacticalState = None
        self.currentStrategy = None
        self.reservedTiles = {}
        self.events = ()
        self.info = {}

    def observe(self, state):
        self.info = snapshot(state)
        self.currentTacticalState = self.info['mode'].upper()
        self.events = tuple(tuple(e) for e in self.info['events'])

    def report(self, index, role, target, mode):
        # scatter/chase is a team-wide state (currentTacticalState); per ghost only the exceptions are modes
        self.roles[index] = role
        self.modes[index] = 'active' if mode in ('scatter', 'chase') else mode
        if target is None:
            self.assignedTargets.pop(index, None)
        else:
            self.assignedTargets[index] = (int(target[0]), int(target[1]))

    def getTelemetry(self):
        return dict(tacticalState=self.currentTacticalState, macroStrategy=None,
                    modes=dict(self.modes), events=[list(e) for e in self.events], **{
                        k: self.info.get(k) for k in ('level', 'phaseLeftSec', 'frightLeftSec', 'combo', 'elroy')})


class ArcadeGhost(Agent):
    """Base arcade ghost: chooses among the framework's legal actions; all arcade timing lives in the rules."""
    PERS = 0

    def __init__(self, index=1):
        self.index = index
        self._plan = None
        self._director = None

    def director(self):
        d = ArcadeGhostTeam._coordinator
        if d is None:
            d = ArcadeGhostTeam._coordinator = ArcadeDirector()
        return d

    # -- personality -----------------------------------------------------
    def chaseTarget(self, state):
        pac = tileOf(state.getPacmanPosition())
        return blinkyTarget(pac)

    def target(self, state):
        """Target tile for the current global mode (scatter corner or chase target)."""
        mode = globalMode(state)
        lay = state.data.layout
        pers = self.PERS
        if mode == 'scatter' and not (pers == 0 and self.index == 1 and elroyLevel(state) > 0):
            return scatterCorner(pers, lay.width, lay.height)
        return self.chaseTarget(state)

    # -- decision ---------------------------------------------------------
    def getAction(self, state):
        legal = state.getLegalActions(self.index)
        d = self.director()
        d.observe(state)
        s = state.getGhostState(self.index)
        g = s.arcade
        tile = tileOf(s.configuration.pos)
        role = PERSONALITIES[self.PERS]
        if g['mode'] == 'eyes':
            h = CFG.house
            d.report(self.index, role, h.center if h else tileOf(s.start.pos), 'eyes')
            return legal[0] if legal else Directions.STOP
        if g['mode'] in ('house', 'exit'):
            d.report(self.index, role, CFG.house.exitTile if CFG.house else None, g['mode'])
            return legal[0] if legal else Directions.STOP
        mode = 'frightened' if g['frightened'] else globalMode(state)
        if len(legal) <= 1:
            self._plan = None
            tgt = None if mode == 'frightened' else self.target(state)
            d.report(self.index, role, tgt, mode)
            return legal[0] if legal else Directions.STOP
        if mode == 'frightened':
            self._plan = None
            d.report(self.index, role, None, mode)
            return frightenedChoice(legal)
        tgt = self.target(state)
        d.report(self.index, role, tgt, mode)
        # Arcade ghosts commit to the turn one tile in advance; use that plan if it still applies.
        if self._plan and self._plan[0] == tile and self._plan[1] in legal and self._plan[2] == mode:
            action = self._plan[1]
        else:
            action = chooseExit(legal, tile, tgt)
        self._planAhead(state, tile, action, tgt, mode)
        return action

    def _planAhead(self, state, tile, action, tgt, mode):
        walls = state.data.layout.walls
        v = VEC[action]
        nxt = (tile[0] + v[0], tile[1] + v[1])
        rev = Actions.reverseDirection(action)
        opts = [a for a in TIE_ORDER if a != rev and not walls[nxt[0] + VEC[a][0]][nxt[1] + VEC[a][1]]
                and not _blocked((nxt[0] + VEC[a][0], nxt[1] + VEC[a][1]))]
        self._plan = (nxt, chooseExit(opts, nxt, tgt), mode) if len(opts) > 1 else None


class ArcadeBlinky(ArcadeGhost):
    """Red: targets Pac-Man's tile; Cruise Elroy speed-up is applied by the rules."""
    PERS = 0


class ArcadePinky(ArcadeGhost):
    """Pink: four tiles ahead of Pac-Man (with the up-direction overflow bug unless disabled)."""
    PERS = 1

    def chaseTarget(self, state):
        return pinkyTarget(tileOf(state.getPacmanPosition()), state.getPacmanState().configuration.direction,
                           CFG.overflowBug)


class ArcadeInky(ArcadeGhost):
    """Cyan: twice the vector from Blinky to the tile two ahead of Pac-Man."""
    PERS = 2

    def chaseTarget(self, state):
        blinky = tileOf(state.getGhostPosition(1)) if state.getNumAgents() > 1 else tileOf(state.getPacmanPosition())
        return inkyTarget(tileOf(state.getPacmanPosition()), state.getPacmanState().configuration.direction,
                          blinky, CFG.overflowBug)


class ArcadeClyde(ArcadeGhost):
    """Orange: chases from 8+ tiles away, retreats to his corner when closer."""
    PERS = 3

    def chaseTarget(self, state):
        lay = state.data.layout
        me = tileOf(state.getGhostPosition(self.index))
        return clydeTarget(me, tileOf(state.getPacmanPosition()), scatterCorner(3, lay.width, lay.height))


_PERS_CLASSES = [ArcadeBlinky, ArcadePinky, ArcadeInky, ArcadeClyde]


class ArcadeGhostTeam(Agent):
    """Use as `--ghost ArcadeGhostTeam`: ghost k gets personality (k-1) mod 4 (1 Blinky, 2 Pinky, 3 Inky, 4 Clyde).
    The class attribute `_coordinator` is the shared ArcadeDirector, so dashboards read it like a coordinator."""
    _coordinator = None

    def __init__(self, index=1):
        self.index = index
        self.agent = _PERS_CLASSES[(index - 1) % 4](index)

    def getAction(self, state):
        return self.agent.getAction(state)
