# enhancedGhostAgents.py
# ----------------------
# Phase 3 completion : Tasks 4, 5, 6 (Trajectory, Pincer, Path Reservation)
# Phase 4 completion : Tasks 1, 2, 3, 4 (Shared Perception, State Machine, Dynamic Strategy, Scared Coord)
# Written by: [Your Name]
#
# This file does NOT modify any of Renu's code.
# It imports her classes and extends them via subclassing.
#
# To use these agents, run from inside the multiagent/ folder:
#   python pacman.py -p GreedyAgent -g EnhancedCoordinatedGhostTeam -l mediumClassic
#   python pacman.py -p KeyboardAgent -g EnhancedCoordinatedGhostTeam -l mediumClassic -n 1

import coordinatedGhostAgents as _base   # Renu's file — only imported, never edited
from game import Agent, Directions, Actions
from util import manhattanDistance, Queue


# =============================================================================
# SECTION 1 — EnhancedGhostCoordinator
# Subclasses Renu's GhostCoordinator and adds Tasks 4, 5, and 6 logic.
# =============================================================================

class EnhancedGhostCoordinator(_base.GhostCoordinator):
    """
    Extends GhostCoordinator with three improvements:

    Task 4 — Better trajectory prediction:
        Renu's version blindly picks validMoves[0] for 4 steps (not real prediction).
        We override predictPacmanPosition() to track actual velocity from
        Pac-Man's movement history and project it forward through the maze.

    Task 5 — Pincer/containment strategy:
        Renu's interceptor used the weak prediction as its target.
        We add computePincerTargets() which finds a tile *ahead* of Pac-Man
        in the corridor they are currently running through — so the chaser
        chases from behind while the interceptor cuts off the front. Real pincer.

    Task 6 — Path priority & collision avoidance:
        Renu's ghosts ignore each other entirely during pathfinding.
        We add a reservedTiles table: each ghost, after computing its move,
        registers the tile it's about to step on. Lower-priority ghosts check
        this table and pick an alternate tile if theirs is taken.
    """

    DEFAULT_FEATURES = {'macro': True, 'tactical': True, 'flee': True, 'sticky': True}

    def __init__(self, gameState=None):
        # Call Renu's __init__ so roles and assignedTargets are set up
        super().__init__(gameState)

        # --- Phase 3 Task 4 state ---
        # We need to remember where Pac-Man was on the PREVIOUS tick
        # so we can compute (new position - old position) = velocity vector
        self.lastPacmanPos  = None
        self.pacmanVelocity = (0, 0)   # (dx, dy), e.g. (1,0) = moving East

        # --- Phase 3 Task 6 state ---
        # Maps ghost_index -> the tile that ghost is about to move into.
        # Reset each new game tick (detected via stateHash below).
        self.reservedTiles  = {}
        # We use a hash of (pacman_pos, ghost_positions) to detect new ticks.
        # When the hash changes = a new game tick has started = safe to clear reservations.
        self._lastStateHash = None

        # -----------------------------------------------------------------------
        # Phase 4 Task 1 — Shared Perception Model
        # -----------------------------------------------------------------------
        # "Shared perception" means every ghost sees the same global picture of
        # the board — not just its own immediate surroundings.
        #
        # The coordinator is already shared (class-level singleton), so all ghosts
        # already read the same GameState. What was MISSING was MEMORY across ticks:
        #   - Where has Pac-Man been recently? (movement history)
        #   - Was a power pellet just eaten? (capsule delta)
        #   - Are ghosts currently scared?
        #
        # We store that memory here so every ghost can consult it every tick
        # through the coordinator — true shared perception.

        # Ring buffer: last N positions of Pac-Man (oldest → newest)
        self.pacmanHistory   = []          # list of (x,y) tuples, max length below
        self.HISTORY_LEN     = 6           # how many ticks of history to keep

        # Capsule count from the previous tick — lets us detect the exact tick
        # a power pellet was eaten (current count < previous count).
        self.lastCapsuleCount = None

        # True if ghosts are currently in scared (fleeing) mode.
        # Updated every tick in _updatePerception().
        self.ghostsAreScared  = False

        # -----------------------------------------------------------------------
        # Phase 4 Task 2 — Tactical State Machine
        # -----------------------------------------------------------------------
        # The tactical state of the ghost team. Transitions dynamically between:
        #   - 'COORDINATED_HUNT' : Default offensive containment / pincer hunt
        #   - 'DEFEND_CAPSULE'   : Pac-Man is dangerously close to a power pellet
        #   - 'TRAP_AMBUSH'      : Pac-Man is confined to a corridor / pocket
        #   - 'SCATTER'          : Scared mode (active power pellet)
        self.currentTacticalState = 'COORDINATED_HUNT'
        self.threatenedCapsule    = None

        # -----------------------------------------------------------------------
        # Phase 4 Task 3 — Dynamic Strategy Switching
        # -----------------------------------------------------------------------
        # Macro-level strategy based on game progression (food/capsules remaining):
        #   - 'EARLY_SPREAD'    : Food > 50% — spread out to cover wide areas
        #   - 'MID_PRESSURE'    : Food 20-50% — guard high-density food clusters
        #   - 'ENDGAME_COLLAPSE': Food < 20% or <= 5 dots — all-out aggressive collapse
        self.initialFoodCount     = None
        self.currentStrategy      = 'EARLY_SPREAD'

        # Phase 4 feature switches (ablation/benchmarks flip DEFAULT_FEATURES)
        self.features = dict(self.DEFAULT_FEATURES)
        self._resetPhase4State()
        self.initialFoodCount = None

    # =========================================================================
    # TASK 4 — Velocity-based Trajectory Prediction
    # =========================================================================

    def predictPacmanPosition(self, gameState, steps=5):
        """
        Override of Renu's dummy predictPacmanPosition().

        HOW IT WORKS:
        -------------
        1. We compare Pac-Man's current position to their position on the
           LAST tick. The difference is the velocity: (dx, dy).
           Example: was at (5,3), now at (6,3) → velocity = (1,0) = East.

        2. We project that velocity forward tile by tile for `steps` tiles.
           "Pac-Man will keep going East until they hit a wall."

        3. When they'd hit a wall (can't continue straight), we look for
           the best non-reversing open tile (they won't suddenly go backwards).
           This mimics how a real player navigates a maze.

        4. We return the final projected tile as the interception target.

        WHY THIS IS BETTER:
        -------------------
        Renu's version: picks validMoves[0] (alphabetically first legal move)
        and steps 4 times in that direction regardless of walls or actual movement.
        That's not prediction — it's just picking a semi-random nearby tile.

        Our version: actually looks at which direction Pac-Man is moving and
        follows that trajectory through the maze geometry.
        """
        pacmanPos = gameState.getPacmanPosition()
        walls     = gameState.getWalls()

        # Step 1: Update velocity from movement history
        # If Pac-Man moved since last tick, the delta is their velocity.
        # On the very first tick, lastPacmanPos is None, so velocity stays (0,0).
        if self.lastPacmanPos is not None and self.lastPacmanPos != pacmanPos:
            self.pacmanVelocity = (
                pacmanPos[0] - self.lastPacmanPos[0],
                pacmanPos[1] - self.lastPacmanPos[1]
            )
        # Always update lastPacmanPos so next tick has fresh data
        self.lastPacmanPos = pacmanPos

        vx, vy    = self.pacmanVelocity
        current   = pacmanPos

        width  = walls.width
        height = walls.height

        for _ in range(steps):
            # Try to continue straight in the current velocity direction
            nx, ny = int(current[0] + vx), int(current[1] + vy)

            # Bounds + wall check before indexing into walls grid
            in_bounds = (0 <= nx < width and 0 <= ny < height)
            if (vx != 0 or vy != 0) and in_bounds and not walls[nx][ny]:
                # Path is clear → keep going straight
                current = (nx, ny)
                continue

            # Hit a wall (or boundary, or no velocity known yet).
            # Look for open corridors in any direction EXCEPT straight back
            # (Pac-Man almost never reverses direction mid-corridor).
            candidates = []
            for ddx, ddy in [(1,0), (-1,0), (0,1), (0,-1)]:
                if ddx == -vx and ddy == -vy:
                    continue     # skip the reverse direction
                nnx, nny = int(current[0] + ddx), int(current[1] + ddy)
                if (0 <= nnx < width and 0 <= nny < height) and not walls[nnx][nny]:
                    candidates.append(((ddx, ddy), (nnx, nny)))

            if candidates:
                # Take the first non-reversing open direction and update velocity
                (vx, vy), current = candidates[0]
            else:
                # Dead end — allow reversal as last resort
                reversed_out = False
                for ddx, ddy in [(1,0), (-1,0), (0,1), (0,-1)]:
                    nnx, nny = int(current[0] + ddx), int(current[1] + ddy)
                    if not walls[nnx][nny]:
                        vx, vy  = ddx, ddy
                        current = (nnx, nny)
                        reversed_out = True
                        break
                if not reversed_out:
                    break   # totally trapped, stop projecting

        return current

    # =========================================================================
    # TASK 5 — Pincer / Containment Strategy
    # =========================================================================

    def computePincerTargets(self, gameState):
        """
        Computes two target tiles that bracket Pac-Man from both ends of
        their current corridor — creating a true pincer movement.

        HOW IT WORKS:
        -------------
        Imagine Pac-Man is running East in a hallway:

            Ghost A (chaser) → comes from behind (West side)
            Ghost B (interceptor) → runs ahead to cut off the East end

        - "ahead_target": a tile several steps forward in Pac-Man's velocity
          direction, along the same corridor. The interceptor goes here to
          block the escape route.

        - "behind_target": Pac-Man's actual current position. The chaser
          goes here and follows them. (This is already what Renu's chaser does.)

        Together they form a squeeze. Pac-Man runs into the interceptor
        while the chaser closes from behind.

        FALLBACK:
        ---------
        If Pac-Man's velocity is unknown (first tick, or they stopped),
        we find the most open adjacent tile and use that as the ahead target.
        """
        pacmanPos = gameState.getPacmanPosition()
        walls     = gameState.getWalls()
        vx, vy    = self.pacmanVelocity

        # Project forward along velocity to find the "ahead" position
        if vx != 0 or vy != 0:
            x, y   = pacmanPos
            width  = walls.width
            height = walls.height
            for _ in range(5):            # look up to 5 tiles ahead
                nx, ny = int(x + vx), int(y + vy)
                if not (0 <= nx < width and 0 <= ny < height) or walls[nx][ny]:
                    break                 # out of bounds or hit a wall, stop here
                x, y = nx, ny
            ahead_target = (x, y)
        else:
            # No known velocity — find the most open tile adjacent to Pac-Man
            ahead_target = self._mostOpenAdjacentTile(pacmanPos, walls)

        behind_target = pacmanPos   # chaser covers this side already

        return ahead_target, behind_target

    def _mostOpenAdjacentTile(self, pos, walls):
        """
        Helper for Task 5 fallback.
        Returns the adjacent tile that has the most open exits (least wall-blocked).
        "Most open" = best tile for the interceptor to get ahead to.
        """
        x, y = pos
        best_tile  = pos
        best_exits = -1

        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
            nx, ny = int(x + dx), int(y + dy)
            if walls[nx][ny]:
                continue
            # Count how many exits this candidate tile has
            exits = sum(
                1 for ddx, ddy in [(1,0), (-1,0), (0,1), (0,-1)]
                if not walls[int(nx+ddx)][int(ny+ddy)]
            )
            if exits > best_exits:
                best_exits = exits
                best_tile  = (nx, ny)

        return best_tile

    # =========================================================================
    # PHASE 4 TASK 1 — Shared Perception Model
    # =========================================================================

    def _resetPhase4State(self):
        """Forget everything learned in a previous game (the coordinator is a
        class-level singleton that outlives a game when -n > 1)."""
        self.pacmanHistory = []
        self.lastCapsuleCount = None
        self.ghostsAreScared = False
        self.currentTacticalState = 'COORDINATED_HUNT'
        self.threatenedCapsule = None
        self.initialFoodCount = None
        self.currentStrategy = 'EARLY_SPREAD'
        self.scaredTimers = {}
        self._p4Tick = 0
        self._tickKey = None
        self._lastFoodSeen = None
        self._stateSince = 0
        self._roleSince = 0
        self._baseRoles = {}
        self._pacDistCache = (None, None)

    def _updatePerception(self, gameState):
        """
        Shared perception, refreshed once per game tick (see assignRoles).
        Tracks Pac-Man's recent positions, the capsule count, and the
        PER-GHOST scared timers (a ghost eaten by Pac-Man respawns unscared,
        so a single team-wide flag is wrong). Cheap: O(#ghosts).
        """
        pacmanPos = gameState.getPacmanPosition()
        self.pacmanHistory.append(pacmanPos)
        if len(self.pacmanHistory) > self.HISTORY_LEN:
            self.pacmanHistory.pop(0)
        self.lastCapsuleCount = len(gameState.getCapsules())
        self.scaredTimers = {i + 1: int(gs.scaredTimer)
                             for i, gs in enumerate(gameState.getGhostStates())}
        self.ghostsAreScared = any(t > 0 for t in self.scaredTimers.values())
        self._evaluateMacroStrategy(gameState)
        self._evaluateTacticalState(gameState)

    # =========================================================================
    # PHASE 4 TASK 3 — Dynamic Strategy Switching
    # =========================================================================

    def _evaluateMacroStrategy(self, gameState):
        """
        Macro strategy from food progression. It only BIASES the sweeper's
        target (see assignRoles); chaser/interceptor/blocker always pursue.
        EARLY_SPREAD > 50% food; MID_PRESSURE 20-50%; ENDGAME_COLLAPSE below.
        Thresholds have a small hysteresis band so it cannot flap on one dot.
        """
        currentFood = gameState.getNumFood()
        if self.initialFoodCount is None or self.initialFoodCount == 0:
            self.initialFoodCount = max(currentFood, 1)
        ratio = currentFood / float(self.initialFoodCount)
        cur = self.currentStrategy
        # Strategy only ever advances (food never increases within a game).
        if cur == 'EARLY_SPREAD' and ratio <= 0.50:
            cur = 'MID_PRESSURE'
        if cur == 'MID_PRESSURE' and (ratio <= 0.20 or currentFood <= 5):
            cur = 'ENDGAME_COLLAPSE'
        self.currentStrategy = cur
        return cur

    def _findDenseFoodCluster(self, gameState):
        """Food dot closest to the centroid of all remaining food."""
        foodList = gameState.getFood().asList()
        if not foodList:
            return gameState.getPacmanPosition()
        n = float(len(foodList))
        avgX = sum(f[0] for f in foodList) / n
        avgY = sum(f[1] for f in foodList) / n
        return min(foodList, key=lambda f: (f[0] - avgX) ** 2 + (f[1] - avgY) ** 2)

    # =========================================================================
    # PHASE 4 TASK 2 — Tactical State Machine
    # =========================================================================

    CACHE_TICK = 1           # compute once per tick (0 = every ghost call)
    MIN_STATE_DWELL = 5      # ticks a tactical state is held before switching
    MIN_ROLE_DWELL = 6       # ticks a role assignment is held before re-ranking
    ROLE_SWITCH_MARGIN = 3   # new chaser must be this much closer to justify a swap
    FLEE_MIN_TIMER = 5       # scared ghost flees only while timer exceeds this

    def _evaluateTacticalState(self, gameState):
        """
        SCATTER         some ghost is still scared long enough to flee
        DEFEND_CAPSULE  Pac-Man within 4 of a capsule (released beyond 6)
        TRAP_AMBUSH     Pac-Man in a dead end
        COORDINATED_HUNT default
        A state is held for MIN_STATE_DWELL ticks before it may change.
        """
        pacmanPos = gameState.getPacmanPosition()
        cur = self.currentTacticalState
        threatened = None
        if self.features.get('tactical', True):
            reach = 6 if cur == 'DEFEND_CAPSULE' else 4
            for cap in gameState.getCapsules():
                if manhattanDistance(pacmanPos, cap) <= reach:
                    threatened = cap
                    break

        if any(t > self.FLEE_MIN_TIMER for t in self.scaredTimers.values()) \
                and self.features.get('flee', True):
            desired = 'SCATTER'
        elif threatened is not None:
            desired = 'DEFEND_CAPSULE'
        elif self.features.get('tactical', True) and \
                self._isPacmanTrappedOrCorridor(gameState, pacmanPos):
            desired = 'TRAP_AMBUSH'
        else:
            desired = 'COORDINATED_HUNT'

        if desired != cur and self._p4Tick - self._stateSince >= self.MIN_STATE_DWELL:
            self.currentTacticalState = desired
            self._stateSince = self._p4Tick
        # DEFEND_CAPSULE bookkeeping follows the (possibly held) state
        self.threatenedCapsule = threatened if self.currentTacticalState == 'DEFEND_CAPSULE' else None
        return self.currentTacticalState

    def _isPacmanTrappedOrCorridor(self, gameState, pacmanPos):
        """True when Pac-Man stands in a dead end (a single open exit)."""
        walls = gameState.getWalls()
        x, y = pacmanPos
        openExits = 0
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < walls.width and 0 <= ny < walls.height and not walls[nx][ny]:
                openExits += 1
        return openExits <= 1

    # =========================================================================
    # PHASE 4 TASK 4 — Scared Ghost Coordination
    # =========================================================================

    def _bfsDistances(self, walls, start):
        dist = {start: 0}
        q = Queue()
        q.push(start)
        while not q.isEmpty():
            cx, cy = q.pop()
            d = dist[(cx, cy)] + 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (cx + dx, cy + dy)
                if nxt not in dist and 0 <= nxt[0] < walls.width and \
                        0 <= nxt[1] < walls.height and not walls[nxt[0]][nxt[1]]:
                    dist[nxt] = d
                    q.push(nxt)
        return dist

    def getFleeTarget(self, gameState, ghostIndex):
        """
        Flee target for a scared ghost: the tile that maximises the maze
        distance from Pac-Man while staying cheap for the ghost to reach
        (score = distPacman - 0.5 * distGhost). Pac-Man's distance map is
        cached per tick; one extra BFS per fleeing ghost.
        """
        walls = gameState.getWalls()
        pacmanPos = gameState.getPacmanPosition()
        if self._pacDistCache[0] != (pacmanPos, self._p4Tick):
            self._pacDistCache = ((pacmanPos, self._p4Tick),
                                  self._bfsDistances(walls, pacmanPos))
        dP = self._pacDistCache[1]
        ghostPos = tuple(int(v) for v in gameState.getGhostPosition(ghostIndex))
        dG = self._bfsDistances(walls, ghostPos)
        best, bestScore = None, None
        for tile, g in dG.items():
            if g == 0 or tile not in dP:
                continue
            score = dP[tile] - 0.5 * g
            if bestScore is None or score > bestScore:
                best, bestScore = tile, score
        return best if best is not None else pacmanPos

    # =========================================================================
    # Read-only dashboard export is defined after assignRoles (getTelemetry).
    # assignRoles — integrates Phase 3 & 4 Coordination, State Machine & Strategy
    # =========================================================================

    def assignRoles(self, gameState):
        """
        Override of Renu's assignRoles(). Every ghost calls this each tick,
        so the Phase 4 work is done once per tick (keyed on score+Pac-Man
        position; score drops by 1 per Pac-Man move) and cached for the
        other ghosts. A rise in food count marks a new game and resets state.

        Order: reservation reset (Phase 3) -> perception/state machine ->
        base roles/targets -> sticky role mapping -> tactical overrides
        (flee / capsule guard / pincer) -> macro bias on the sweeper.
        """
        # --- Phase 3 Task 6: detect new tick and reset reservations ---
        stateHash = (
            gameState.getPacmanPosition(),
            tuple(gameState.getGhostPositions())
        )
        if stateHash != self._lastStateHash:
            self.reservedTiles  = {}
            self._lastStateHash = stateHash

        # --- Phase 4: once-per-tick gate + new-game detection ---
        food = gameState.getNumFood()
        if self._lastFoodSeen is not None and food > self._lastFoodSeen:
            self._resetPhase4State()
        self._lastFoodSeen = food
        tickKey = (gameState.getScore(), gameState.getPacmanPosition(), food)
        if self.CACHE_TICK and tickKey == self._tickKey and self.roles:
            return
        self._tickKey = tickKey
        self._p4Tick += 1

        self._updatePerception(gameState)

        # --- base roles/targets; harvest the per-role target table ---
        super().assignRoles(gameState)
        order = ['chaser', 'interceptor', 'blocker', 'sweeper']
        roleTarget = {r: self.assignedTargets[g] for g, r in self.roles.items()}
        pacmanPos = gameState.getPacmanPosition()
        ghostIdxs = sorted(self.roles.keys())

        # --- who flees (scared with enough timer left) ---
        fleeing = []
        if self.features.get('flee', True):
            fleeing = [g for g in ghostIdxs if self.scaredTimers.get(g, 0) > self.FLEE_MIN_TIMER]
        active = [g for g in ghostIdxs if g not in fleeing]

        # --- sticky role mapping over the active ghosts ---
        def dist(g):
            return manhattanDistance(gameState.getGhostPosition(g), pacmanPos)
        avail = order[:len(active)]
        fresh = {g: r for g, r in zip(sorted(active, key=dist), avail)}
        prev = self._baseRoles
        valid = (self.features.get('sticky', True) and
                 len(prev) == len(active) and set(prev) == set(active) and
                 sorted(prev.values()) == sorted(avail))
        if valid and fresh != prev:
            prevChaser = [g for g, r in prev.items() if r == 'chaser']
            freshChaser = [g for g, r in fresh.items() if r == 'chaser']
            keep = True
            if prevChaser and freshChaser:
                better = dist(prevChaser[0]) - dist(freshChaser[0]) >= self.ROLE_SWITCH_MARGIN
                keep = not (better and self._p4Tick - self._roleSince >= self.MIN_ROLE_DWELL)
            final = prev if keep else fresh
        else:
            final = fresh if not valid else prev
        if final != prev:
            self._roleSince = self._p4Tick
        self._baseRoles = dict(final)

        self.roles = dict(final)
        self.assignedTargets = {g: roleTarget[r] for g, r in final.items()}

        # --- Scared ghosts flee (Phase 4 Task 4) ---
        for g in fleeing:
            self.roles[g] = 'scared'
            self.assignedTargets[g] = self.getFleeTarget(gameState, g)
        if not active:
            return

        # --- DEFEND_CAPSULE: nearest non-chaser guards the pellet ---
        if self.currentTacticalState == 'DEFEND_CAPSULE' and self.threatenedCapsule:
            candidates = [g for g in active if self.roles[g] != 'chaser']
            if candidates:
                guard = min(candidates, key=lambda g: manhattanDistance(
                    gameState.getGhostPosition(g), self.threatenedCapsule))
                self.roles[guard] = 'capsule_guard'
                self.assignedTargets[guard] = self.threatenedCapsule

        # --- Pincer: interceptor cuts off ahead of Pac-Man (Phase 3) ---
        ahead_target, _ = self.computePincerTargets(gameState)
        for g, role in list(self.roles.items()):
            if role == 'interceptor':
                self.assignedTargets[g] = ahead_target

        # --- Macro bias: only the sweeper's target, never the pursuers ---
        if self.features.get('macro', True):
            for g, role in self.roles.items():
                if role != 'sweeper':
                    continue
                foodList = gameState.getFood().asList()
                if self.currentStrategy == 'MID_PRESSURE':
                    dense = self._findDenseFoodCluster(gameState)
                    if manhattanDistance(dense, pacmanPos) <= 10:
                        self.assignedTargets[g] = dense
                elif self.currentStrategy == 'ENDGAME_COLLAPSE' and foodList:
                    self.assignedTargets[g] = min(
                        foodList, key=lambda f: manhattanDistance(f, pacmanPos))

    def getTelemetry(self):
        """Read-only, JSON-serialisable snapshot for the dashboard."""
        return {
            'tacticalState': self.currentTacticalState,
            'macroStrategy': self.currentStrategy,
            'roles': {int(g): str(r) for g, r in self.roles.items()},
            'targets': {int(g): [int(t[0]), int(t[1])] for g, t in self.assignedTargets.items()},
            'scaredTimers': {int(g): int(t) for g, t in self.scaredTimers.items()},
        }

    # =========================================================================
    # TASK 6 — Path Priority & Collision Avoidance (Reservation Table)
    # =========================================================================

    def reserveTile(self, ghostIndex, tile):
        """
        Called by a ghost after it has chosen its next move.
        Records: "ghost #ghostIndex is about to step onto `tile`."

        Lower-priority ghosts will check this before finalising their own move.
        """
        self.reservedTiles[ghostIndex] = tile

    def isTileReservedByHigherPriority(self, ghostIndex, tile):
        """
        Returns True if a HIGHER-priority ghost has already reserved `tile`
        this tick, meaning our ghost should pick a different tile.

        PRIORITY ORDER (lower number = higher priority = moves first):
            chaser      → 1
            interceptor → 2
            blocker     → 3
            sweeper     → 4

        WHY THIS ORDER:
        ---------------
        The chaser is always closest to Pac-Man and most critical to keep
        on the right path. The sweeper is the least critical (it's covering
        distant food tiles), so it yields to everyone else.
        """
        my_priority = self._rolePriority(ghostIndex)

        for other_idx, other_tile in self.reservedTiles.items():
            if other_idx == ghostIndex:
                continue
            other_priority = self._rolePriority(other_idx)
            if other_priority < my_priority and other_tile == tile:
                return True   # a more important ghost is going here → yield

        return False

    def _rolePriority(self, ghostIndex):
        """Maps ghost index → priority number (1 = highest, 4 = lowest)."""
        role         = self.roles.get(ghostIndex, 'sweeper')
        priority_map = {'chaser': 1, 'interceptor': 2, 'blocker': 3, 'sweeper': 4}
        return priority_map.get(role, 4)


# =============================================================================
# SECTION 2 — EnhancedCoordinatedGhostTeam
# The actual ghost agent class. Uses EnhancedGhostCoordinator for all 3 tasks.
# This is the class you pass to -g on the command line.
# =============================================================================

class EnhancedCoordinatedGhostTeam(Agent):
    """
    Drop-in replacement for Renu's CoordinatedGhostTeam.

    Uses EnhancedGhostCoordinator which adds Tasks 4, 5, and 6.
    We do NOT inherit from CoordinatedGhostTeam — that would pull in
    Renu's global _coordinator_instance and cause conflicts.
    Instead we maintain our own class-level coordinator here.

    HOW getAction() WORKS each tick:
    ---------------------------------
    1. Coordinator assigns roles + targets (with pincer injection for interceptor).
    2. Ghost gets its target tile from the coordinator.
    3. BFS finds the shortest path from ghost's position to that target.
    4. Task 6 check: if the first step of that path is reserved by a
       higher-priority ghost, pick the next-best step instead.
    5. Register our chosen tile so lower-priority ghosts can avoid it.
    6. Return the move.
    """

    # Shared coordinator across all ghost instances in the same game.
    # Class-level (not instance-level) so all 4 ghost objects see the same one.
    _coordinator = None

    def __init__(self, index):
        self.index = index
        # First ghost to be created initialises the shared coordinator
        if EnhancedCoordinatedGhostTeam._coordinator is None:
            EnhancedCoordinatedGhostTeam._coordinator = EnhancedGhostCoordinator()

    def getAction(self, state):
        coord = EnhancedCoordinatedGhostTeam._coordinator

        # --- Step 1: Coordinator assigns roles and targets ---
        # This internally runs Renu's role logic + our pincer override (Task 5)
        # and clears reservations if a new tick is detected (Task 6 setup).
        coord.assignRoles(state)

        # --- Step 2: Get MY assigned target tile ---
        myTarget     = coord.assignedTargets.get(self.index, state.getPacmanPosition())
        legalActions = state.getLegalActions(self.index)
        ghostPos     = state.getGhostPosition(self.index)
        walls        = state.getWalls()

        if not legalActions or (len(legalActions) == 1 and legalActions[0] == Directions.STOP):
            return Directions.STOP

        # --- Step 3: BFS — find the first action toward our target ---
        bestAction = self._bfsFirstAction(
            ghostPos, myTarget, legalActions, walls, walls.width, walls.height
        )

        # --- Step 4 (Task 6): Collision avoidance ---
        # What tile would we land on if we take bestAction?
        nextTile = self._resultTile(ghostPos, bestAction)

        # Is that tile already claimed by a higher-priority ghost?
        if coord.isTileReservedByHigherPriority(self.index, nextTile):
            # Yes — find the next-best action that avoids the reserved tile
            bestAction = self._avoidAndMove(
                ghostPos, myTarget, legalActions, walls, blockedTile=nextTile
            )
            nextTile = self._resultTile(ghostPos, bestAction)

        # --- Step 5 (Task 6): Register our tile so lower-priority ghosts see it ---
        coord.reserveTile(self.index, nextTile)

        return bestAction

    # -------------------------------------------------------------------------
    # BFS path-finding (same algorithm Renu used, extracted as a clean method)
    # -------------------------------------------------------------------------

    def _bfsFirstAction(self, start, target, legalActions, walls, width, height):
        """
        Finds the first action to take to reach `target` from `start`
        using Breadth-First Search (shortest path in an unweighted grid).

        WHAT BFS DOES HERE:
        --------------------
        - We add every legal first step into a queue, paired with the action
          that produced it.
        - We expand tiles layer by layer (BFS = level order = shortest path).
        - The moment we find `target` in the queue, we return the first action
          that was taken to start that path.
        - If BFS never reaches target (disconnected maze section), we fall
          back to the action that minimises Manhattan distance to target.
        """
        if start == target:
            # Already at target — just move toward Pac-Man (greedy fallback)
            return self._manhattanBestAction(start, target, legalActions)

        visited = {start}
        queue   = Queue()

        # Seed the queue with all legal first steps
        for action in legalActions:
            if action == Directions.STOP:
                continue
            dx, dy  = Actions.directionToVector(action)
            nextPos = (int(start[0]+dx), int(start[1]+dy))
            if 0 <= nextPos[0] < width and 0 <= nextPos[1] < height and not walls[nextPos[0]][nextPos[1]]:
                if nextPos == target:
                    return action        # target is one step away → done immediately
                if nextPos not in visited:
                    visited.add(nextPos)
                    queue.push((nextPos, action))   # (position, first_action_that_led_here)

        # Expand the frontier until we hit target
        while not queue.isEmpty():
            currentPos, firstAction = queue.pop()
            for action in [Directions.NORTH, Directions.SOUTH, Directions.EAST, Directions.WEST]:
                dx, dy  = Actions.directionToVector(action)
                nextPos = (int(currentPos[0]+dx), int(currentPos[1]+dy))
                if 0 <= nextPos[0] < width and 0 <= nextPos[1] < height:
                    if walls[nextPos[0]][nextPos[1]] or nextPos in visited:
                        continue
                    if nextPos == target:
                        return firstAction   # found it — return the very first step
                    visited.add(nextPos)
                    queue.push((nextPos, firstAction))

        # BFS couldn't reach target (shouldn't happen in a connected maze)
        # Fall back to Manhattan-minimising greedy step
        return self._manhattanBestAction(start, target, legalActions)

    def _manhattanBestAction(self, pos, target, legalActions):
        """
        Greedy fallback: pick whichever legal action gets us closest to
        `target` by Manhattan distance in one step.
        """
        bestAction = Directions.STOP
        bestDist   = float('inf')
        for action in legalActions:
            if action == Directions.STOP:
                continue
            dx, dy  = Actions.directionToVector(action)
            nextPos = (int(pos[0]+dx), int(pos[1]+dy))
            dist    = manhattanDistance(nextPos, target)
            if dist < bestDist:
                bestDist   = dist
                bestAction = action
        return bestAction

    # -------------------------------------------------------------------------
    # Task 6 helpers
    # -------------------------------------------------------------------------

    def _resultTile(self, pos, action):
        """
        Returns the tile we'd land on after taking `action` from `pos`.
        If action is STOP, we stay on pos.
        """
        if action == Directions.STOP:
            return pos
        dx, dy = Actions.directionToVector(action)
        return (int(pos[0]+dx), int(pos[1]+dy))

    def _avoidAndMove(self, pos, target, legalActions, walls, blockedTile):
        """
        Task 6: Called when our first-choice tile is reserved by a higher-
        priority ghost. Picks the next-best legal action that avoids `blockedTile`.

        HOW IT WORKS:
        -------------
        Iterate over all legal actions, skip any that lead to `blockedTile`,
        and among the remaining ones pick whichever is closest to our target
        (Manhattan distance). This is a greedy one-step decision — good enough
        to break deadlocks without expensive re-planning.

        FALLBACK:
        ---------
        If every possible move leads to the blocked tile (very rare — would
        need a 1-tile dead-end where the only exit is blocked), we allow the
        blocked tile anyway rather than returning STOP indefinitely.
        """
        bestAction = None
        bestDist   = float('inf')

        for action in legalActions:
            if action == Directions.STOP:
                continue
            nextTile = self._resultTile(pos, action)
            if nextTile == blockedTile:
                continue        # skip the reserved tile
            dist = manhattanDistance(nextTile, target)
            if dist < bestDist:
                bestDist   = dist
                bestAction = action

        # If no clear alternative exists, allow the blocked tile (last resort)
        if bestAction is None:
            for action in legalActions:
                if action != Directions.STOP:
                    return action

        return bestAction if bestAction else legalActions[0]
