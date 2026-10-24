# voronoiGhostAgents.py
# ---------------------
# Phase 7 ghost candidates:
#   VoronoiGhostTeam            (A) territory control + exit blocking + optimal assignment
#   VoronoiExpectimaxGhostTeam  (B) A + depth-2 joint-move search when Pac-Man is close
#   MazeDistanceChaseTeam       (C) every ghost steps along the maze-shortest path to Pac-Man
#
# All teams: legal actions only, never STOP, one plan per tick shared through a
# class-level coordinator (ghost index 1 plans, the others read the cached plan).

import itertools
import math
from collections import deque

from game import Agent, Directions, Actions

_DIRS = [Directions.NORTH, Directions.SOUTH, Directions.EAST, Directions.WEST]
_BIG = 999


# ---------------------------------------------------------------------------
# Maze distance table (all pairs BFS), cached per layout
# ---------------------------------------------------------------------------

class MazeTable(object):
    _cache = {}

    def __init__(self, walls):
        self.width, self.height = walls.width, walls.height
        self.cells = [(x, y) for x in range(self.width) for y in range(self.height)
                      if not walls[x][y]]
        cellset = set(self.cells)
        self.adj = {}
        for (x, y) in self.cells:
            self.adj[(x, y)] = [(x + dx, y + dy) for dx, dy in
                                ((0, 1), (0, -1), (1, 0), (-1, 0))
                                if (x + dx, y + dy) in cellset]
        self.D = {}
        for s in self.cells:
            d = {s: 0}
            q = deque([s])
            while q:
                c = q.popleft()
                for n in self.adj[c]:
                    if n not in d:
                        d[n] = d[c] + 1
                        q.append(n)
            self.D[s] = d

    def dist(self, a, b):
        return self.D[a].get(b, _BIG)

    @classmethod
    def get(cls, walls):
        key = (walls.width, walls.height, hash(tuple(tuple(col) for col in walls.data)))
        t = cls._cache.get(key)
        if t is None:
            t = MazeTable(walls)
            cls._cache[key] = t
        return t, key


def _cell(pos):
    return (int(math.floor(pos[0] + 0.5)), int(math.floor(pos[1] + 0.5)))


def _next_cells(state, idx, table):
    """[(action, cell_after_move)] for legal non-STOP actions of ghost idx."""
    gs = state.getGhostState(idx)
    speed = 0.5 if gs.scaredTimer > 0 else 1.0
    pos = gs.getPosition()
    out = []
    for a in state.getLegalActions(idx):
        if a == Directions.STOP:
            continue
        dx, dy = Actions.directionToVector(a, speed)
        c = _cell((pos[0] + dx, pos[1] + dy))
        if c in table.D:
            out.append((a, c))
    return out


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------

class _TeamBase(Agent):
    """Plans for every ghost when ghost index 1 is asked; others read the plan."""
    _plan = {}
    _memory = {}
    _lastFood = 10 ** 9
    _lastKey = None
    # timing instrumentation (read by bakeoff)
    plan_calls = 0
    plan_time = 0.0

    def __init__(self, index):
        self.index = index

    @classmethod
    def _reset(cls):
        cls._plan = {}
        cls._memory = {}

    def getAction(self, state):
        cls = type(self)
        table, key = MazeTable.get(state.getWalls())
        nf = state.getNumFood()
        if key != cls._lastKey or nf > cls._lastFood:
            cls._reset()
        cls._lastKey, cls._lastFood = key, nf
        legal = [a for a in state.getLegalActions(self.index) if a != Directions.STOP]
        if not legal:
            return Directions.STOP
        if self.index == 1 or self.index not in cls._plan:
            cls._plan = self.makePlan(state, table)
        a = cls._plan.get(self.index)
        if a not in legal:
            a = self.fallback(state, table, legal)
        return a

    def fallback(self, state, table, legal):
        pac = _cell(state.getPacmanPosition())
        opts = _next_cells(state, self.index, table)
        if not opts:
            return legal[0]
        return min(opts, key=lambda ac: table.dist(ac[1], pac))[0]

    def makePlan(self, state, table):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# C: maze-distance chase
# ---------------------------------------------------------------------------

class MazeDistanceChaseTeam(_TeamBase):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9

    def makePlan(self, state, table):
        pac = _cell(state.getPacmanPosition())
        plan = {}
        taken = []
        for i in range(1, state.getNumAgents()):
            opts = _next_cells(state, i, table)
            if not opts:
                continue
            gs = state.getGhostState(i)
            scared = gs.scaredTimer > 3

            def cost(ac, i=i, scared=scared):
                d = table.dist(ac[1], pac)
                base = -d if scared else d
                spread = 0.6 * sum(1 for c in taken if c == ac[1])
                # deterministic per-ghost tie break so ghosts fan out
                tb = 0.01 * ((_DIRS.index(ac[0]) + i) % 4)
                return base + spread + tb
            a, c = min(opts, key=cost)
            plan[i] = a
            taken.append(c)
        return plan


# ---------------------------------------------------------------------------
# A: Voronoi territory control
# ---------------------------------------------------------------------------

class VoronoiGhostTeam(_TeamBase):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9

    HUNT_TIMER = 3         # scared ghosts resume hunting at/below this timer
    STICK = 0.35           # stickiness weight (maze distance from previous target)
    CHASER = False         # nearest hunter always chases Pac-Man directly
    CAP_R = 10             # capsules Pac-Man can reach within this many steps are guarded
    CAP_BONUS = 0.0        # assignment bonus for guarding a threatened capsule
    STRICT = True          # ghost must arrive strictly before Pac-Man

    # -- territory / targets ------------------------------------------------
    def territory(self, table, pac, hunters_cells):
        Dp = table.D[pac]
        owned = {}
        for c in table.cells:
            dp = Dp.get(c, _BIG)
            dg = min((table.D[g].get(c, _BIG) for g in hunters_cells), default=_BIG)
            owned[c] = (dg < dp) if self.STRICT else (dg <= dp)
        return owned

    def chooseTargets(self, table, pac, owned, k, capsules=()):
        """Frontier tiles of ghost territory, one per Pac-Man exit first."""
        Dp = table.D[pac]
        frontier = [c for c in table.cells if owned[c] and
                    any((not owned[n]) for n in table.adj[c])]
        frontier = [c for c in frontier if c != pac]
        exits = table.adj[pac]
        groups = {}
        for t in frontier:
            dp = Dp.get(t, _BIG)
            # exit n lies on a shortest path pac -> t
            for n in exits:
                if table.D[n].get(t, _BIG) == dp - 1:
                    groups.setdefault(n, []).append(t)
        cands = []
        for n, ts in groups.items():
            ts.sort(key=lambda t: Dp.get(t, _BIG))
            cands.append(ts[0])
        # extras: next-nearest frontier tiles (spread), then Pac-Man itself
        rest = sorted(frontier, key=lambda t: Dp.get(t, _BIG))
        for t in rest:
            if len(cands) >= k + 3:
                break
            if t not in cands and all(table.dist(t, c) >= 2 for c in cands):
                cands.append(t)
        if pac not in cands:
            cands.append(pac)
        for c in capsules:
            if self.CAP_BONUS > 0 and Dp.get(c, _BIG) <= self.CAP_R and c not in cands:
                cands.append(c)
        return cands

    def assign(self, table, ghosts, cands, capsules=()):
        """Brute-force optimal assignment with stickiness; ghosts: [(idx, cell)]."""
        mem = type(self)._memory
        k = len(ghosts)
        n = len(cands)
        cost = []
        for (i, g) in ghosts:
            prev = mem.get(i)
            row = []
            for t in cands:
                c = table.dist(g, t)
                if prev is not None:
                    c += self.STICK * min(table.dist(prev, t), 8)
                if t in capsules:
                    c -= self.CAP_BONUS
                row.append(c)
            cost.append(row)
        best, bestperm = None, None
        if n >= k:
            for perm in itertools.permutations(range(n), k):
                s = sum(cost[r][perm[r]] for r in range(k))
                if best is None or s < best:
                    best, bestperm = s, perm
        else:
            for r in range(k):
                pass
            bestperm = tuple(min(range(n), key=lambda j: cost[r][j]) for r in range(k))
        return {ghosts[r][0]: cands[bestperm[r]] for r in range(k)}

    # -- planning -------------------------------------------------------------
    def huntTargets(self, state, table):
        pac = _cell(state.getPacmanPosition())
        n = state.getNumAgents()
        hunters, scared = [], []
        for i in range(1, n):
            gs = state.getGhostState(i)
            c = _cell(gs.getPosition())
            if gs.scaredTimer > self.HUNT_TIMER:
                scared.append((i, c))
            else:
                hunters.append((i, c))
        targets = {}
        if hunters:
            owned = self.territory(table, pac, [c for _, c in hunters])
            caps = tuple(_cell(c) for c in state.getCapsules())
            cands = self.chooseTargets(table, pac, owned, len(hunters), caps)
            if self.CHASER and len(hunters) > 1:
                near = min(hunters, key=lambda h: table.dist(h[1], pac))
                rest = [h for h in hunters if h is not near]
                targets = self.assign(table, rest, cands, caps)
                targets[near[0]] = pac
            else:
                targets = self.assign(table, hunters, cands, caps)
            for i, t in targets.items():
                type(self)._memory[i] = t
        return pac, hunters, scared, targets

    def stepToward(self, state, table, i, target, pac):
        opts = _next_cells(state, i, table)
        if not opts:
            return None
        g = _cell(state.getGhostPosition(i))
        if target == g:
            target = pac
        return min(opts, key=lambda ac: (table.dist(ac[1], target),
                                         table.dist(ac[1], pac)))

    def flee(self, state, table, i, pac):
        opts = _next_cells(state, i, table)
        if not opts:
            return None
        return max(opts, key=lambda ac: (table.dist(ac[1], pac), len(table.adj[ac[1]])))

    def makePlan(self, state, table):
        pac, hunters, scared, targets = self.huntTargets(state, table)
        plan = {}
        for i, _ in hunters:
            r = self.stepToward(state, table, i, targets[i], pac)
            if r:
                plan[i] = r[0]
        for i, _ in scared:
            r = self.flee(state, table, i, pac)
            if r:
                plan[i] = r[0]
        return plan


# ---------------------------------------------------------------------------
# B: Voronoi + depth-2 joint search near Pac-Man
# ---------------------------------------------------------------------------

class VoronoiExpectimaxGhostTeam(VoronoiGhostTeam):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9

    TRIGGER = 4            # any hunting ghost within this maze distance triggers search
    SEARCH_R = 6           # ghosts within this distance join the search
    MAX_PLY1 = 3           # ghosts enumerated at ply 1
    MAX_PLY2 = 2           # ghosts enumerated at ply 2
    PAC_MODEL = 'mix'      # 'greedy' | 'pessimistic' | 'mix'
    W_MIX = 0.5            # weight on pessimistic in 'mix'
    search_calls = 0

    def makePlan(self, state, table):
        pac, hunters, scared, targets = self.huntTargets(state, table)
        plan = {}
        for i, _ in hunters:
            r = self.stepToward(state, table, i, targets[i], pac)
            if r:
                plan[i] = r[0]
        for i, _ in scared:
            r = self.flee(state, table, i, pac)
            if r:
                plan[i] = r[0]
        if hunters and min(table.dist(c, pac) for _, c in hunters) <= self.TRIGGER:
            VoronoiExpectimaxGhostTeam.search_calls += 1
            try:
                self.search(state, table, pac, hunters, plan)
            except Exception:
                pass  # never let search crash a game; keep Voronoi plan
        return plan

    # -- search ----------------------------------------------------------------
    def search(self, state, table, pac, hunters, plan):
        D = table.D
        adj = table.adj
        foods = state.getFood().asList()
        nfCache = {}

        def nearfood(c):
            v = nfCache.get(c)
            if v is None:
                d = D[c]
                v = min((d.get(f, _BIG) for f in foods), default=0)
                nfCache[c] = v
            return v

        # ghost records: (idx, cell, prevcell)
        recs = {}
        for i, c in hunters:
            gs = state.getGhostState(i)
            dirn = gs.configuration.direction
            if dirn in (Directions.STOP, None):
                prev = None
            else:
                dx, dy = Actions.directionToVector(dirn)
                prev = (c[0] - int(dx), c[1] - int(dy))
            recs[i] = (c, prev)
        order = sorted(recs, key=lambda i: D[recs[i][0]].get(pac, _BIG))
        near = [i for i in order if D[recs[i][0]].get(pac, _BIG) <= self.SEARCH_R]
        if not near:
            return
        ply1 = near[:self.MAX_PLY1]
        # action choices at ply 1 from the real legal action set
        choices1 = {}
        for i in ply1:
            opts = _next_cells(state, i, table)
            if not opts:
                return
            choices1[i] = opts
        others = [i for i in recs if i not in ply1]
        # fixed moves for other hunters at ply 1 = the Voronoi plan move
        fixed1 = {}
        for i in others:
            r = [c for a, c in _next_cells(state, i, table) if a == plan.get(i)]
            fixed1[i] = r[0] if r else recs[i][0]

        def moves(cell, prev):
            ns = adj[cell]
            ms = [n for n in ns if n != prev]
            return ms if ms else ns

        def chase_step(cell, prev, pc):
            ms = moves(cell, prev)
            return min(ms, key=lambda n: D[n].get(pc, _BIG))

        def evaluate(pc, gcells):
            ds = sorted(D[g].get(pc, _BIG) for g in gcells)
            return -(ds[0] + 0.25 * sum(ds[1:]))

        def pac_options(pc, gcells, gprev):
            return adj[pc]

        def value_after_ghosts(pc, g, depth_left, gprev_map):
            """Ghost move result handled by caller; g = dict idx->(cell, prev)."""
            raise NotImplementedError

        # value of a configuration just after ghosts moved: evaluate or recurse.
        def ghost_phase(pc, gstate, ply):
            """gstate: dict idx->(cell,prev). Ghosts to move at ply (1 or 2).
            Returns best (max) value over joint ghost moves."""
            if ply == 1:
                keys = ply1
            else:
                keys = [i for i in order if i in gstate][:self.MAX_PLY2]
            lists = []
            for i in keys:
                c, p = gstate[i]
                lists.append(moves(c, p) if ply == 2 else [cc for _, cc in choices1[i]])
            rest = [i for i in gstate if i not in keys]
            best = -1e9
            for combo in itertools.product(*lists):
                ng = {}
                for i, n in zip(keys, combo):
                    ng[i] = (n, gstate[i][0])
                for i in rest:
                    c, p = gstate[i]
                    if ply == 1:
                        n = fixed1[i]
                    else:
                        n = chase_step(c, p, pc)
                    ng[i] = (n, c)
                cells = [v[0] for v in ng.values()]
                if pc in cells:
                    val = 1000.0 - 10 * ply
                elif ply == 1:
                    val = pac_phase(pc, ng)
                else:
                    val = evaluate(pc, cells)
                if val > best:
                    best = val
                    if ply == 1:
                        ghost_phase.bestmap = {i: ng[i][0] for i in ng}
            return best

        def pac_phase(pc, gstate):
            """Pac-Man replies, then ghosts move again (ply 2)."""
            vals = []
            gcells = {v[0] for v in gstate.values()}
            for n in adj[pc]:
                swap = any(v[0] == pc and v[1] == n for v in gstate.values())
                if n in gcells or swap:
                    vals.append((n, 1000.0 - 5, True))  # Pac-Man walked into a ghost
                else:
                    vals.append((n, ghost_phase(n, gstate, 2), False))
            if not vals:
                return evaluate(pc, [v[0] for v in gstate.values()])
            model = self.PAC_MODEL
            pess = min(v for _, v, _ in vals)
            safe = [(n, v) for n, v, dead in vals if not dead]
            if not safe:
                gre = pess
            else:
                bf = min(nearfood(n) for n, _ in safe)
                top = [v for n, v in safe if nearfood(n) == bf]
                gre = sum(top) / len(top)
            if model == 'pessimistic':
                return pess
            if model == 'greedy':
                return gre
            return self.W_MIX * pess + (1 - self.W_MIX) * gre

        g0 = dict((i, recs[i]) for i in recs)
        ghost_phase.bestmap = None
        ghost_phase(pac, g0, 1)
        bm = ghost_phase.bestmap
        if not bm:
            return
        for i in ply1:
            target = bm[i]
            for a, c in choices1[i]:
                if c == target:
                    plan[i] = a
                    break


# convenience aliases for the PAC_MODEL variants (used by the bake-off)
class VoronoiExpectimaxGreedyTeam(VoronoiExpectimaxGhostTeam):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9
    PAC_MODEL = 'greedy'


class VoronoiExpectimaxPessimisticTeam(VoronoiExpectimaxGhostTeam):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9
    PAC_MODEL = 'pessimistic'


class VoronoiChaserTeam(VoronoiGhostTeam):
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9
    CHASER = True


class VoronoiLooseTeam(VoronoiGhostTeam):
    """Ties go to the ghost (Pac-Man moves first, so an equal-distance tile is a capture)."""
    _plan = {}
    _memory = {}
    _lastKey = None
    _lastFood = 10 ** 9
    STRICT = False
    STICK = 0.1
