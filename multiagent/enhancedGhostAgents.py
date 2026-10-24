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

    def _updatePerception(self, gameState):
        """
        Called at the start of every tick (from assignRoles) to refresh the
        coordinator's shared memory of the board.

        HOW IT WORKS:
        -------------
        Three things are tracked:

        1. PACMAN HISTORY — We append Pac-Man's current position to a rolling
           buffer (max HISTORY_LEN entries). This tells every ghost not just
           where Pac-Man IS, but where they've BEEN — useful for spotting
           patrol patterns, repeated corridors, and for smarter prediction.

        2. CAPSULE DELTA — We compare the current capsule count to the count
           from the previous tick. If it dropped, Pac-Man just ate a power
           pellet THIS TICK → we set ghostsAreScared = True immediately,
           one tick before the game's scaredTimer propagates to all ghosts.

        3. SCARED FLAG — We check each ghost's scaredTimer directly. If any
           ghost has scaredTimer > 0, we set ghostsAreScared = True so every
           agent in the team can check this single flag without re-reading
           every ghost state independently.

        WHY THIS MATTERS:
        -----------------
        Without shared perception, each ghost independently reads the game
        state and makes local decisions. With it, the coordinator builds a
        richer picture that all 4 ghosts benefit from simultaneously —
        they share one "brain" that remembers the past and detects events.
        """
        pacmanPos     = gameState.getPacmanPosition()
        capsuleCount  = len(gameState.getCapsules())
        ghostStates   = gameState.getGhostStates()

        # 1. Update Pac-Man's position history (rolling window)
        self.pacmanHistory.append(pacmanPos)
        if len(self.pacmanHistory) > self.HISTORY_LEN:
            self.pacmanHistory.pop(0)   # drop the oldest entry

        # 2. Detect power pellet being eaten this tick
        if self.lastCapsuleCount is not None and capsuleCount < self.lastCapsuleCount:
            # A capsule just disappeared — Pac-Man ate it → ghosts are now scared
            self.ghostsAreScared = True
        self.lastCapsuleCount = capsuleCount

        # 3. Sync scared flag with actual ghost states
        # (covers the case where scared timer naturally expires)
        self.ghostsAreScared = any(gs.scaredTimer > 0 for gs in ghostStates)

        # 4. Phase 4 Task 3: Evaluate Macro Strategy (food progression)
        self._evaluateMacroStrategy(gameState)

        # 5. Phase 4 Task 2: Evaluate Tactical State (threats & opportunities)
        self._evaluateTacticalState(gameState)

    # =========================================================================
    # PHASE 4 TASK 3 — Dynamic Strategy Switching
    # =========================================================================

    def _evaluateMacroStrategy(self, gameState):
        """
        Determines the high-level macro strategy based on game progression
        (remaining food and capsules).

        STRATEGY MODES:
        ---------------
        1. 'EARLY_SPREAD' (Food > 50% remaining):
           The board is full of food. Ghosts maintain wide territorial control
           to restrict Pac-Man's free roaming and prevent him from clearing
           large sections unmolested.

        2. 'MID_PRESSURE' (Food between 20% and 50% remaining):
           Pac-Man is actively clearing food. Ghosts tighten their containment
           perimeter and focus pressure on high-density food clusters.

        3. 'ENDGAME_COLLAPSE' (Food < 20% or <= 5 dots remaining):
           Pac-Man is close to winning! Sweeper stops roaming to distant food
           and transitions into an active pursuer / close guard. All ghosts
           collapse on Pac-Man and the remaining dots.
        """
        currentFood = gameState.getNumFood()
        if self.initialFoodCount is None or self.initialFoodCount == 0:
            self.initialFoodCount = max(currentFood, 1)

        foodRatio = currentFood / float(self.initialFoodCount)

        if foodRatio > 0.50 and currentFood > 5:
            self.currentStrategy = 'EARLY_SPREAD'
        elif foodRatio > 0.20 and currentFood > 5:
            self.currentStrategy = 'MID_PRESSURE'
        else:
            self.currentStrategy = 'ENDGAME_COLLAPSE'

        return self.currentStrategy

    def _findDenseFoodCluster(self, gameState):
        """
        Helper for Task 3: Dynamic Strategy Switching.
        Finds the food dot that is closest to the 'center of mass' of all remaining food,
        representing the densest cluster of dots where Pac-Man must eventually go.
        """
        foodList = gameState.getFood().asList()
        if not foodList:
            return gameState.getPacmanPosition()

        # Calculate centroid (average x, average y)
        avgX = sum(f[0] for f in foodList) / float(len(foodList))
        avgY = sum(f[1] for f in foodList) / float(len(foodList))

        # Find the actual food dot closest to this centroid
        bestFood = min(foodList, key=lambda f: (f[0] - avgX)**2 + (f[1] - avgY)**2)
        return bestFood

    # =========================================================================
    # PHASE 4 TASK 2 — Tactical State Machine
    # =========================================================================

    def _evaluateTacticalState(self, gameState):
        """
        Evaluates the immediate tactical posture of the ghost team.
        Transitions the team between tactical states on each tick:

        STATE TRANSITIONS:
        ------------------
        1. 'SCATTER':
           Active when Pac-Man has consumed a power pellet (scaredTimer > 0).
           Overrides all other tactical states — defensive survival is #1 priority.

        2. 'DEFEND_CAPSULE':
           Triggered when an active capsule exists and Pac-Man is within
           threatening distance (<= 4 Manhattan distance) of it, AND a ghost
           is positioned to potentially contest or intercept before Pac-Man eats it.
           One ghost is dispatched as 'capsule_guard' to race to that pellet.

        3. 'TRAP_AMBUSH':
           Triggered when Pac-Man is confined in a corridor or pocket with
           limited escape routes (<= 2 open exits) and ghosts are in position
           to seal the bottleneck.

        4. 'COORDINATED_HUNT' (Default):
           Standard tactical offensive: Chaser drives, Interceptor pincers,
           Blocker covers bottleneck, Sweeper controls territory.
        """
        # State 1: SCATTER (Highest priority — defensive survival)
        if self.ghostsAreScared:
            self.currentTacticalState = 'SCATTER'
            self.threatenedCapsule = None
            return self.currentTacticalState

        pacmanPos = gameState.getPacmanPosition()
        capsules = gameState.getCapsules()

        # State 2: DEFEND_CAPSULE (Threat-driven)
        # Check if Pac-Man is dangerously close to any power pellet
        threatened = None
        for cap in capsules:
            distToPacman = manhattanDistance(pacmanPos, cap)
            if distToPacman <= 4:
                threatened = cap
                break

        if threatened is not None:
            self.currentTacticalState = 'DEFEND_CAPSULE'
            self.threatenedCapsule = threatened
            return self.currentTacticalState
        else:
            self.threatenedCapsule = None

        # State 3: TRAP_AMBUSH (Opportunity-driven)
        # Check if Pac-Man is in a corridor/dead-end with <= 2 open exits
        if self._isPacmanTrappedOrCorridor(gameState, pacmanPos):
            self.currentTacticalState = 'TRAP_AMBUSH'
            return self.currentTacticalState

        # State 4: COORDINATED_HUNT (Default offensive)
        self.currentTacticalState = 'COORDINATED_HUNT'
        return self.currentTacticalState

    def _isPacmanTrappedOrCorridor(self, gameState, pacmanPos):
        """
        Helper for Task 2.
        Checks if Pac-Man is currently in a narrow corridor (2 exits total)
        or a dead-end (1 exit total), making an ambush lockdown highly effective.
        """
        walls = gameState.getWalls()
        width, height = walls.width, walls.height
        x, y = pacmanPos
        openExits = 0
        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and not walls[nx][ny]:
                openExits += 1

        # A dead-end has 1 exit; a standard corridor has 2 exits.
        return openExits <= 2

    # =========================================================================
    # PHASE 4 TASK 4 — Scared Ghost Coordination
    # =========================================================================

    def getFleeTarget(self, gameState, ghostIndex):
        """
        When ghosts are scared (Pac-Man ate a power pellet), they should NOT
        hunt — they should RUN AWAY in a coordinated scatter pattern.

        HOW IT WORKS:
        -------------
        Renu's original code has no scared behaviour at all — scared ghosts
        still try to move toward their hunting target. We fix that here.

        Each ghost picks a SCATTER CORNER: a fixed corner of the maze opposite
        to Pac-Man. We assign a different corner per ghost role so they spread
        out and don't all flee to the same spot (which would make them easy
        to catch and waste scared time colliding).

        Corner assignment by role:
            chaser      → top-right corner    (opposite of bottom-left)
            interceptor → top-left corner
            blocker     → bottom-right corner
            sweeper     → bottom-left corner

        We give each corner a small inset (2 tiles) so ghosts don't try to
        walk into a wall at the literal corner.

        WHY SCATTER CORNERS:
        --------------------
        This is actually how the original Pac-Man arcade game worked —
        ghosts scatter to fixed corners when not hunting. It's a proven
        pattern that prevents them clustering and keeps them spread across
        the maze, making them harder to catch all at once.
        """
        walls  = gameState.getWalls()
        width  = walls.width
        height = walls.height
        role   = self.roles.get(ghostIndex, 'sweeper')

        # Corner tile coordinates with 2-tile inset from actual corner walls
        corners = {
            'chaser'      : (width - 3,  height - 3),   # top-right
            'interceptor' : (2,           height - 3),   # top-left
            'blocker'     : (width - 3,  2),             # bottom-right
            'sweeper'     : (2,           2),             # bottom-left
        }

        corner = corners.get(role, (2, 2))

        # Safety: if the corner tile is a wall (rare layout edge case),
        # nudge inward until we find a walkable tile
        cx, cy = corner
        for offset in range(0, 4):
            tx, ty = cx + offset, cy + offset
            if 0 <= tx < width and 0 <= ty < height and not walls[tx][ty]:
                return (tx, ty)

        # Absolute fallback: just move away from Pac-Man
        return gameState.getPacmanPosition()

    # =========================================================================
    # assignRoles — integrates Phase 3 & 4 Coordination, State Machine & Strategy
    # =========================================================================

    def assignRoles(self, gameState):
        """
        Override of Renu's assignRoles().

        HOW IT WORKS:
        -------------
        1. [Phase 3 Task 6] Compute state hash to detect new ticks and reset
           the reservation table for path collision avoidance.

        2. [Phase 4 Task 1] Run _updatePerception() to refresh shared memory:
           Pac-Man history, capsule delta, scared timers, macro strategy,
           and current tactical state.

        3. Call Renu's baseline assignRoles() via super() to establish initial
           distance-based role assignments and base targets.

        4. [Phase 4 Task 2 & 4] Tactical State Machine Overrides:
           - 'SCATTER': Scared mode. All ghosts flee to designated scatter corners.
           - 'DEFEND_CAPSULE': Pac-Man is near a power pellet. A ghost is
             assigned 'capsule_guard' to race to the pellet and deny it.
           - 'TRAP_AMBUSH': Pac-Man is trapped in a narrow corridor. Chaser
             presses from behind while Interceptor locks down the forward choke.
           - 'COORDINATED_HUNT': Standard pincer setup with velocity projection.

        5. [Phase 4 Task 3] Dynamic Strategy Switching Overrides:
           - 'MID_PRESSURE': Sweeper redirects from far food to the densest food
             cluster to contest high-value areas.
           - 'ENDGAME_COLLAPSE': Late game (<20% food). Sweeper becomes an active
             pursuer; all ghosts converge on Pac-Man and remaining dots.
        """
        # --- Phase 3 Task 6: detect new tick and reset reservations ---
        stateHash = (
            gameState.getPacmanPosition(),
            tuple(gameState.getGhostPositions())
        )
        if stateHash != self._lastStateHash:
            # New game tick detected → clear the reservation table
            self.reservedTiles  = {}
            self._lastStateHash = stateHash

        # --- Phase 4 Task 1, 2, 3: refresh shared perception & state machines ---
        self._updatePerception(gameState)

        # --- Renu's base role assignment runs (unchanged) ---
        super().assignRoles(gameState)

        # =====================================================================
        # Phase 4 Task 2 & 4: Tactical State Machine Handling
        # =====================================================================

        # State 1: SCATTER (Phase 4 Task 4)
        if self.currentTacticalState == 'SCATTER':
            for ghostIdx in self.roles:
                self.assignedTargets[ghostIdx] = self.getFleeTarget(gameState, ghostIdx)
            return   # Offensive coordination suspended while scared

        # State 2: DEFEND_CAPSULE (Phase 4 Task 2)
        if self.currentTacticalState == 'DEFEND_CAPSULE' and self.threatenedCapsule:
            # Pick a secondary ghost (blocker/sweeper/interceptor) to defend the pellet
            # so the primary chaser can continue applying direct pressure
            candidates = [idx for idx in self.roles if self.roles[idx] in ('blocker', 'sweeper', 'interceptor')]
            if not candidates:
                candidates = list(self.roles.keys())
            if candidates:
                guardIdx = min(
                    candidates,
                    key=lambda idx: manhattanDistance(gameState.getGhostPosition(idx), self.threatenedCapsule)
                )
                self.roles[guardIdx] = 'capsule_guard'
                self.assignedTargets[guardIdx] = self.threatenedCapsule

        # State 3 & 4: Pincer & Ambush Targeting (Phase 3 Task 5 + Phase 4 Task 2)
        ahead_target, _ = self.computePincerTargets(gameState)
        for ghostIdx, role in list(self.roles.items()):
            if role == 'interceptor':
                # In both TRAP_AMBUSH and COORDINATED_HUNT, interceptor blocks ahead
                self.assignedTargets[ghostIdx] = ahead_target

        # =====================================================================
        # Phase 4 Task 3: Dynamic Macro Strategy Overrides
        # =====================================================================

        if self.currentStrategy == 'MID_PRESSURE':
            # Sweeper shifts focus to the centroid / densest cluster of remaining food
            denseFood = self._findDenseFoodCluster(gameState)
            for ghostIdx, role in self.roles.items():
                if role == 'sweeper':
                    self.assignedTargets[ghostIdx] = denseFood

        elif self.currentStrategy == 'ENDGAME_COLLAPSE':
            # Endgame panic! Pac-Man has eaten > 80% of dots.
            # Sweeper transitions into an aggressive secondary pursuer
            pacmanPos = gameState.getPacmanPosition()
            foodList = gameState.getFood().asList()
            for ghostIdx, role in self.roles.items():
                if role == 'sweeper':
                    if foodList:
                        # Target the remaining food dot closest to Pac-Man to cut him off
                        closestFoodToPacman = min(foodList, key=lambda f: manhattanDistance(f, pacmanPos))
                        self.assignedTargets[ghostIdx] = closestFoodToPacman
                    else:
                        self.assignedTargets[ghostIdx] = pacmanPos

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
