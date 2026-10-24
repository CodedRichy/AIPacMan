from game import Agent, Directions, Actions
from util import manhattanDistance

_coordinator_instance = None

_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
_FAR = 10 ** 6

# Pincer tuning (measured on mediumClassic vs GreedyAgent, 200 games each):
# radius 4 with "nearest block tile" beat radius 8 / 14 / "furthest" by 70-200 points.
PINCER_RADIUS = 4


# =============================================================================
# Shared helpers (also used by enhancedGhostAgents.py)
# =============================================================================

class MazeDistances:
    """
    Lazily cached BFS distance maps for one maze layout.

    distFrom(src) returns {tile: steps} for every tile reachable from src.
    Each source is searched once per layout, so after warm-up a decision only
    does O(1) dictionary lookups instead of a fresh BFS per ghost per tick.
    """
    _byWalls = {}      # wall signature -> MazeDistances
    _last = None       # fast path: most recently used instance

    def __init__(self, walls):
        self.walls = walls
        self.width = walls.width
        self.height = walls.height
        self.maps = {}

    @classmethod
    def get(cls, walls):
        last = cls._last
        # The engine deep-copies the layout every move, so compare by value; list
        # equality runs in C and costs a couple of microseconds.
        if last is not None and (last.walls is walls or last.walls.data == walls.data):
            return last
        key = (walls.width, walls.height, tuple(tuple(col) for col in walls.data))
        md = cls._byWalls.get(key)
        if md is None:
            md = MazeDistances(walls)
            if len(cls._byWalls) > 8:
                cls._byWalls.clear()
            cls._byWalls[key] = md
        cls._last = md
        return md

    def distFrom(self, src):
        m = self.maps.get(src)
        if m is not None:
            return m
        walls, width, height = self.walls, self.width, self.height
        m = {src: 0}
        frontier = [src]
        d = 0
        while frontier:
            d += 1
            nxt = []
            for (x, y) in frontier:
                for dx, dy in _DIRS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and not walls[nx][ny] and (nx, ny) not in m:
                        m[(nx, ny)] = d
                        nxt.append((nx, ny))
            frontier = nxt
        self.maps[src] = m
        return m


def tileOf(pos):
    """Nearest integer tile (scared ghosts can sit on half-tiles)."""
    return (int(round(pos[0])), int(round(pos[1])))


def ghostMoves(state, index):
    """Legal non-STOP moves of ghost `index` as [(action, destinationTile)]."""
    pos = state.getGhostPosition(index)
    moves = []
    for a in state.getLegalActions(index):
        if a == Directions.STOP:
            continue
        dx, dy = Actions.directionToVector(a)
        moves.append((a, tileOf((pos[0] + dx, pos[1] + dy))))
    return moves


def reachTime(moves, target, md):
    """Steps this ghost needs to reach `target` (respects the no-reverse rule)."""
    dt = md.distFrom(target)
    return 1 + min(dt.get(t, _FAR) for a, t in moves)


def pickAction(moves, target, md, blocked=None, slack=0):
    """
    Move that minimises maze distance to `target`.
    If the best destination is in `blocked` (tile reserved by a higher-priority
    ghost) an alternative at most `slack` steps worse is taken instead.
    """
    dt = md.distFrom(target)
    scored = sorted((dt.get(t, _FAR), i) for i, (a, t) in enumerate(moves))
    best = scored[0][0]
    for d, i in scored:
        if d > best + slack:
            break
        if not blocked or moves[i][1] not in blocked:
            return moves[i][0]
    return moves[scored[0][1]][0]


def fleeAction(moves, pacTile, ghostTile, md, slow=True):
    """
    Scared behaviour. Pick the tile within reach that is farthest from Pac-Man
    among those we can get to well before he can (a scared ghost moves at half
    speed, so its travel time counts double), then step toward it. One-step
    "maximise distance" runs straight into dead ends; this does not.
    """
    dp = md.distFrom(pacTile)
    walls = md.walls
    cost = 2 if slow else 1
    best, bestKey = None, None
    for t, d in md.distFrom(ghostTile).items():
        if d > 12:
            continue
        margin = dp.get(t, 0) - cost * d
        exits = sum(1 for dx, dy in _DIRS if not walls[t[0] + dx][t[1] + dy])
        key = (margin >= 2, dp.get(t, 0) if margin >= 2 else margin, exits)
        if bestKey is None or key > bestKey:
            best, bestKey = t, key
    if best is None or best == ghostTile:
        return max(moves, key=lambda m: dp.get(m[1], 0))[0]
    safe = [m for m in moves if dp.get(m[1], 0) > 1] or moves   # never step next to Pac-Man
    return pickAction(safe, best, md)


def pincerTarget(moves, pacTile, chaserTile, md, radius=PINCER_RADIUS, nearest=True):
    """
    Block tile on the far side of Pac-Man from the chaser: a tile t whose
    shortest path from the chaser runs *through* Pac-Man's tile (so Pac-Man is
    squeezed between the two ghosts), within `radius` of Pac-Man, that this
    ghost can reach no later than Pac-Man. Of those, the nearest (or furthest,
    nearest=False) one. If none is reachable in time, take the tile that
    minimises (our arrival time - Pac-Man's arrival time). Falls back to
    Pac-Man's own tile.
    """
    dp = md.distFrom(pacTile)
    dc = md.distFrom(chaserTile)
    base = dc.get(pacTile, _FAR)
    best, bestKey = None, None
    for t, d in dp.items():
        if d < 1 or d > radius:
            continue
        if dc.get(t, _FAR) != base + d:          # not on the far side of Pac-Man
            continue
        slack = d - reachTime(moves, t, md)      # >= 0 means we beat Pac-Man there
        key = (slack >= 0, (-d if nearest else d) if slack >= 0 else slack)
        if bestKey is None or key > bestKey:
            best, bestKey = t, key
    return best if best is not None else pacTile


def approachTarget(moves, pacTile, chaserTile, md):
    """
    Tile next to Pac-Man on a different side than the one the chaser will
    arrive through, so extra ghosts do not stack behind the chaser.
    """
    walls = md.walls
    nbrs = [(pacTile[0] + dx, pacTile[1] + dy) for dx, dy in _DIRS
            if not walls[pacTile[0] + dx][pacTile[1] + dy]]
    if len(nbrs) <= 1:
        return pacTile
    dc = md.distFrom(chaserTile)
    entry = min(nbrs, key=lambda n: dc.get(n, _FAR))
    best, bestD = pacTile, _FAR
    for n in nbrs:
        if n == entry:
            continue
        d = reachTime(moves, n, md)
        if d < bestD:
            best, bestD = n, d
    return best if bestD > 1 else pacTile


# =============================================================================
# Base coordinator
# =============================================================================

class GhostCoordinator:
    def __init__(self, gameState=None):
        self.gameState = gameState
        self.roles = {}
        self.assignedTargets = {}
        self.lastPacmanPos = None
        self.pacmanVelocity = (0, 0)
        self._chokeWalls = None
        self._chokeCands = []
        self._chokeMemo = {}

    def rankGhosts(self, gameState):
        """Ghost indices ordered by maze distance to Pac-Man (closest first)."""
        md = MazeDistances.get(gameState.getWalls())
        dp = md.distFrom(tileOf(gameState.getPacmanPosition()))
        ranked = [(dp.get(tileOf(pos), _FAR), i + 1)
                  for i, pos in enumerate(gameState.getGhostPositions())]
        ranked.sort()
        return [i for d, i in ranked]

    def assignRoles(self, gameState):
        pacmanPos = gameState.getPacmanPosition()
        self.roles = {}
        self.assignedTargets = {}
        order = self.rankGhosts(gameState)
        numGhosts = len(order)
        if numGhosts == 0:
            return
        if numGhosts >= 1:
            ghostIdx = order[0]
            self.roles[ghostIdx] = 'chaser'
            self.assignedTargets[ghostIdx] = pacmanPos
        if numGhosts >= 2:
            ghostIdx = order[1]
            self.roles[ghostIdx] = 'interceptor'
            self.assignedTargets[ghostIdx] = self.predictPacmanPosition(gameState)
        if numGhosts >= 3:
            ghostIdx = order[2]
            self.roles[ghostIdx] = 'blocker'
            chokePoint = self.findChokePoint(gameState)
            self.assignedTargets[ghostIdx] = chokePoint if chokePoint else pacmanPos
        if numGhosts >= 4:
            ghostIdx = order[3]
            self.roles[ghostIdx] = 'sweeper'
            sweepTarget = self.findSweepTarget(gameState)
            self.assignedTargets[ghostIdx] = sweepTarget if sweepTarget else pacmanPos

    def _updateVelocity(self, gameState):
        """Track Pac-Man's heading from his last observed move."""
        pacmanPos = gameState.getPacmanPosition()
        last = self.lastPacmanPos
        if last is not None and last != pacmanPos:
            dx, dy = pacmanPos[0] - last[0], pacmanPos[1] - last[1]
            if abs(dx) + abs(dy) == 1:
                self.pacmanVelocity = (int(dx), int(dy))
            else:
                self.pacmanVelocity = (0, 0)   # teleport / new game
        self.lastPacmanPos = pacmanPos

    def projectPath(self, gameState, steps=5):
        """
        Tiles Pac-Man is expected to visit next: keep going straight, at a wall
        take the open turn (never reversing unless in a dead end).
        """
        walls = gameState.getWalls()
        width, height = walls.width, walls.height
        current = gameState.getPacmanPosition()
        vx, vy = self.pacmanVelocity
        path = []
        for _ in range(steps):
            nx, ny = int(current[0] + vx), int(current[1] + vy)
            if (vx or vy) and 0 <= nx < width and 0 <= ny < height and not walls[nx][ny]:
                current = (nx, ny)
                path.append(current)
                continue
            options = []
            for ddx, ddy in _DIRS:
                tx, ty = int(current[0] + ddx), int(current[1] + ddy)
                if 0 <= tx < width and 0 <= ty < height and not walls[tx][ty]:
                    options.append((ddx, ddy))
            forward = [o for o in options if o != (-vx, -vy)]
            pool = forward if forward else options
            if not pool:
                break
            vx, vy = pool[0]
            current = (int(current[0] + vx), int(current[1] + vy))
            path.append(current)
        return path

    def predictPacmanPosition(self, gameState, steps=4):
        self._updateVelocity(gameState)
        path = self.projectPath(gameState, steps)
        return path[-1] if path else gameState.getPacmanPosition()

    def findChokePoint(self, gameState):
        """Tile with <=2 exits closest to Pac-Man (candidate list cached per maze)."""
        walls = gameState.getWalls()
        md = MazeDistances.get(walls)     # same object for equal mazes (engine copies walls every move)
        if self._chokeWalls is not md:
            cands = []
            for x in range(1, walls.width - 1):
                for y in range(1, walls.height - 1):
                    if walls[x][y]:
                        continue
                    exits = sum(1 for dx, dy in _DIRS if not walls[x + dx][y + dy])
                    if exits <= 2:
                        cands.append(((x, y), exits))
            self._chokeWalls, self._chokeCands, self._chokeMemo = md, cands, {}
        pacmanPos = gameState.getPacmanPosition()
        if pacmanPos in self._chokeMemo:          # pure function of (maze, Pac-Man tile)
            return self._chokeMemo[pacmanPos]
        bestChoke, bestScore = None, -1
        for pos, exits in self._chokeCands:
            if pos == pacmanPos:
                continue
            score = (3 - exits) * 10 / (manhattanDistance(pacmanPos, pos) + 1)
            if score > bestScore:
                bestScore, bestChoke = score, pos
        self._chokeMemo[pacmanPos] = bestChoke
        return bestChoke

    def findSweepTarget(self, gameState):
        food = gameState.getFood().asList()
        pacmanPos = gameState.getPacmanPosition()
        if not food:
            return pacmanPos
        px, py = pacmanPos
        return max(food, key=lambda f: abs(f[0] - px) + abs(f[1] - py))


def ghostTarget(state, index, roles, md, moves, chaserTile=None):
    """
    Decide what ghost `index` is doing this tick. Returns (action, target):
    action is set only for scared ghosts (they flee); otherwise target is the
    tile to path toward.

    chaser            -> Pac-Man
    interceptor       -> nearest tile on the far side of Pac-Man (pincer)
    blocker           -> same, wider radius, furthest tile (cuts off retreat)
    sweeper / other   -> approach from the side the chaser is not using
    """
    pacTile = tileOf(state.getPacmanPosition())
    if state.getGhostState(index).scaredTimer > 0:
        return fleeAction(moves, pacTile, tileOf(state.getGhostPosition(index)), md), None
    role = roles.get(index, 'chaser')
    if chaserTile is None:
        chasers = [i for i, r in roles.items() if r == 'chaser' and i != index]
        chaserTile = tileOf(state.getGhostPosition(chasers[0])) if chasers else None
    if role == 'chaser' or chaserTile is None:
        return None, pacTile
    if role == 'interceptor':
        return None, pincerTarget(moves, pacTile, chaserTile, md)
    if role == 'blocker':
        return None, pincerTarget(moves, pacTile, chaserTile, md, radius=8, nearest=False)
    return None, approachTarget(moves, pacTile, chaserTile, md)


def chooseGhostAction(state, index, roles, reserved=None):
    """Shared per-ghost decision: flee when scared, else path to ghostTarget()."""
    moves = ghostMoves(state, index)
    if not moves:
        return Directions.STOP
    if len(moves) == 1:
        return moves[0][0]
    md = MazeDistances.get(state.getWalls())
    action, target = ghostTarget(state, index, roles, md, moves)
    if action is not None:
        return action
    return pickAction(moves, target, md, blocked=reserved)


class CoordinatedGhostTeam(Agent):
    def __init__(self, index):
        self.index = index
        global _coordinator_instance
        if _coordinator_instance is None:
            _coordinator_instance = GhostCoordinator(None)

    def getAction(self, state):
        coord = _coordinator_instance
        order = coord.rankGhosts(state)
        roles = {}
        for rank, idx in enumerate(order):
            roles[idx] = ('chaser', 'interceptor', 'blocker', 'sweeper')[min(rank, 3)]
        coord.roles = roles
        return chooseGhostAction(state, self.index, roles)
