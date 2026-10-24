# chatterGhostAgents.py
# ---------------------
# Phase 10: ghosts that really talk to each other.
#
# The Phase 3/4 teams read one omniscient coordinator, so a message bus between
# them would be redundant. Here Pac-Man is hidden by an opt-in "fog": a ghost
# perceives him only when he is within FOG_RADIUS maze tiles or in straight
# line of sight along a corridor. Everything else a ghost knows about him comes
# from teammates through the MessageBus.
#
#   ChatterGhostTeam        fog + messages        (-g ChatterGhostTeam)
#   SilentFogGhostTeam      fog, same code, bus disabled (the control)
#   LossyChatterGhostTeam   fog + messages, 50% of deliveries dropped
#
# Teammate positions and scared timers stay public (the engine shows them);
# only Pac-Man is hidden. No decision reads Pac-Man's true position unless the
# deciding ghost currently perceives him.
#
# Delivery rule: a message is readable at the receiver's NEXT decision after the
# send. In this engine ghosts act one after another inside a tick, so a message
# from ghost 1 reaches ghosts 2..4 in the same tick and ghost 1 hears ghosts
# 2..4 in the next one. That is the lowest latency the sequential engine allows,
# it needs no extra buffering and it is deterministic (order = send order).
#
# Nothing here edits other modules; helpers are imported.

import os
import random
from collections import deque

from game import Agent, Directions, Actions
from util import manhattanDistance
from coordinatedGhostAgents import (MazeDistances, tileOf, ghostMoves, pickAction, reachTime,
                                    fleeAction, pincerTarget, approachTarget)

_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
_FAR = 10 ** 6
ROLES = ('chaser', 'interceptor', 'blocker', 'sweeper')
_PRIO = {'chaser': 1, 'capsule_guard': 1, 'rescue': 1, 'cutoff': 2, 'interceptor': 2,
         'blocker': 3, 'sweeper': 4, 'search': 5}

FOG_RADIUS = 6          # maze tiles
FRESH_AGE = 3           # belief this young (ticks) is hunted directly, older is searched
CLAIM_TTL = 8
CLAIM_REFRESH = 4
GAP_WINDOW = 6          # REQUEST_SUPPORT: chaser has not closed the gap in this many ticks
SUPPORT_TICKS = 8
MAX_SEARCH_AGE = 14

MSG_TYPES = ('SPOTTED', 'CLAIM', 'REQUEST_SUPPORT', 'ACK', 'HANDOFF', 'WARN_CAPSULE', 'SCARED', 'YIELD')


# =============================================================================
# Geometry
# =============================================================================

def lineOfSight(walls, a, b):
    """True when a and b share a row/column with no wall between them."""
    if a == b:
        return True
    if a[0] == b[0]:
        x = a[0]
        lo, hi = sorted((a[1], b[1]))
        return not any(walls[x][y] for y in range(lo + 1, hi))
    if a[1] == b[1]:
        y = a[1]
        lo, hi = sorted((a[0], b[0]))
        return not any(walls[x][y] for x in range(lo + 1, hi))
    return False


def canSense(md, ghostTile, target, radius):
    """Fog rule: within `radius` maze tiles, or straight line of sight."""
    d = md.distFrom(ghostTile).get(target)
    if d is not None and d <= radius:
        return True
    return lineOfSight(md.walls, ghostTile, target)


def advance(walls, tile, vel, steps):
    """Project `steps` tiles ahead: straight on, at a wall take an open non-reversing turn."""
    cur, v = tile, tuple(vel)
    if v == (0, 0):
        return cur
    for _ in range(steps):
        nxt = (cur[0] + v[0], cur[1] + v[1])
        if not walls[nxt[0]][nxt[1]]:
            cur = nxt
            continue
        opts = [d for d in _DIRS if not walls[cur[0] + d[0]][cur[1] + d[1]] and d != (-v[0], -v[1])]
        if not opts:
            break
        v = opts[0]
        cur = (cur[0] + v[0], cur[1] + v[1])
    return cur


# =============================================================================
# MessageBus
# =============================================================================

class MessageBus:
    """
    Per-game message bus. A message is a dict
        {id, tick, sender, to ('all' | ghost index), type, payload, ackOf}
    ids grow monotonically, so delivery order = send order (deterministic).

    Memory is bounded: the log keeps `capacity` messages, every inbox keeps its
    newest `inboxCap`, and the per-tick list is capped. Loss (for the lossy
    ablation) uses a private seeded RNG, one draw per (message, receiver) in
    ascending receiver order. A lost delivery is recorded on the message under
    'lost'. With `enabled=False` send() does nothing (the silent control).
    """

    def __init__(self, capacity=256, inboxCap=16, loss=0.0, seed=0, enabled=True, tickCap=64, off=()):
        self.off = frozenset(off)     # message types suppressed (diagnostic ablation)
        self.capacity, self.inboxCap, self.loss, self.enabled, self.tickCap = capacity, inboxCap, loss, enabled, tickCap
        self.rng = random.Random(seed)
        self.tick = 0
        self.seq = 0
        self.members = []
        self.inbox = {}
        self.log = deque(maxlen=capacity)
        self.thisTick = []
        self.counts = {}
        self.sent = 0
        self.delivered = 0
        self.lostCount = 0

    def register(self, idx):
        if idx not in self.inbox:
            self.members = sorted(self.members + [idx])
            self.inbox[idx] = deque(maxlen=self.inboxCap)

    def newTick(self, tick):
        self.tick = tick
        self.thisTick = []

    def send(self, sender, to, mtype, payload=None, ackOf=None):
        if not self.enabled or mtype in self.off:
            return None
        self.seq += 1
        msg = {'id': self.seq, 'tick': self.tick, 'sender': sender, 'to': to, 'type': mtype,
               'payload': payload or {}, 'ackOf': ackOf}
        receivers = [r for r in self.members if r != sender] if to == 'all' else [r for r in self.members if r == to]
        lost = []
        for r in receivers:
            if self.loss > 0 and self.rng.random() < self.loss:
                lost.append(r)
                self.lostCount += 1
                continue
            self.inbox[r].append(msg)
            self.delivered += 1
        if lost:
            msg['lost'] = lost
        self.sent += 1
        self.counts[mtype] = self.counts.get(mtype, 0) + 1
        self.log.append(msg)
        if len(self.thisTick) < self.tickCap:
            self.thisTick.append(msg)
        return msg

    def receive(self, idx):
        box = self.inbox.get(idx)
        if not box:
            return []
        out = list(box)
        box.clear()
        return out


# =============================================================================
# Per-ghost mind
# =============================================================================

class Mind:
    """Everything one ghost knows. All containers are bounded."""

    def __init__(self):
        self.pac = None            # believed Pac-Man tile when last observed
        self.seen = 0              # tick of that observation
        self.vel = (0, 0)
        self.claims = {}           # sender -> (role, target, bid, tick)
        self.sentClaim = None      # (role, target, tick)
        self.role = None
        self.target = None
        self.heard = -99           # newest observation time learned from a message
        self.lastSpot = -99
        self.lastSpotVel = None
        self.forcedUntil = 0       # HANDOFF received
        self.handedUntil = 0       # HANDOFF sent
        self.cutoff = None         # (until, exit)
        self.guard = None          # (until, capsule)
        self.rescue = None         # until
        self.lock = None           # (until, role, target)  YIELD received
        self.supportUntil = 0
        self.lastReq = -99
        self.lastReqId = None
        self.gap = deque(maxlen=GAP_WINDOW + 2)
        self.prevTile = None
        self.prevScared = False
        self.lastWarn = {}
        self.lastScaredMsg = -99
        self.lastYield = {}


# =============================================================================
# The shared object (one per game): bus + minds + telemetry
# =============================================================================

class ChatterHub:
    def __init__(self, comms=True, loss=0.0, radius=FOG_RADIUS, seed=0, off=()):
        self.comms = comms
        self.radius = radius
        self.off = tuple(off)
        self.bus = MessageBus(loss=loss, seed=seed, enabled=comms, off=off)
        self.minds = {}
        self.tick = 0
        self.lastCaller = _FAR
        self.lastFood = 0
        self.started = False
        self.numGhosts = 0
        self.roles = {}
        self.assignedTargets = {}
        self.reservedTiles = {}
        self.scaredTimers = {}
        self.currentTacticalState = 'SEARCH'
        self.currentStrategy = None
        self.decisions = 0
        self.stats = {'yieldsSent': 0, 'handoffs': 0, 'supportAcks': 0}

    # --- lifecycle -------------------------------------------------------
    def start(self, state):
        n = state.getNumAgents() - 1
        self.numGhosts = n
        self.minds = {i: Mind() for i in range(1, n + 1)}
        start = tileOf(state.getPacmanPosition())
        for i, m in self.minds.items():
            m.pac, m.seen = start, 0
            m.prevTile = tileOf(state.getGhostPosition(i))
            self.bus.register(i)
        self.tick = 0
        self.lastCaller = _FAR
        self.lastFood = state.getNumFood()
        self.started = True

    def begin(self, idx, state):
        food = state.getNumFood()
        if not self.started or food > self.lastFood:     # first call, or a new game reusing this hub
            self.__init__(self.comms, self.bus.loss, self.radius, 12345, self.off)
            self.start(state)
        self.lastFood = food
        if idx <= self.lastCaller:
            self.tick += 1
            self.bus.newTick(self.tick)
        self.lastCaller = idx

    # --- helpers -----------------------------------------------------------
    def _pred(self, m, md):
        age = min(self.tick - m.seen, MAX_SEARCH_AGE)
        return advance(md.walls, m.pac, m.vel, age)

    def _learn(self, m, pac, heading, obsTick, fromMsg=True):
        if obsTick > m.seen or m.pac is None:
            m.pac, m.seen, m.vel = tuple(pac), obsTick, tuple(heading)
        if fromMsg:
            m.heard = max(m.heard, obsTick)

    def _fresh(self, c):
        return self.tick - c[3] <= CLAIM_TTL

    def _send(self, sender, to, mtype, payload, ackOf=None):
        return self.bus.send(sender, to, mtype, payload, ackOf)

    @staticmethod
    def _exitTile(md, pac, chaserTile):
        """Far side of Pac-Man from the chaser, 3-5 tiles out: where he would run to."""
        dp, dc = md.distFrom(pac), md.distFrom(chaserTile)
        base = dc.get(pac, _FAR)
        best = None
        for t, d in dp.items():
            if 3 <= d <= 5 and dc.get(t, _FAR) == base + d:
                key = (d, t)
                if best is None or key > best:
                    best = key
        return best[1] if best else None

    # --- message handling (each branch changes this ghost's later decision) --
    def _handle(self, idx, m, msg, ctx):
        t, p, tick = msg['type'], msg['payload'], self.tick
        if 'pac' in p:
            self._learn(m, p['pac'], p.get('heading', (0, 0)), msg['tick'] - p.get('age', 0))
        if t == 'CLAIM':
            m.claims[msg['sender']] = (p['role'], tuple(p['target']), p['bid'], msg['tick'])
        elif t == 'REQUEST_SUPPORT':
            self._onSupportRequest(idx, m, msg, ctx)
        elif t == 'ACK':
            if msg['ackOf'] == m.lastReqId:
                m.supportUntil = tick + SUPPORT_TICKS
        elif t == 'HANDOFF':
            m.forcedUntil = tick + 6
        elif t == 'WARN_CAPSULE':
            self._onWarn(idx, m, tuple(p['cap']), ctx)
        elif t == 'SCARED':
            self._onScared(idx, m, ctx)
        elif t == 'YIELD':
            m.lock = (tick + 4, m.role, m.target)

    def _onSupportRequest(self, idx, m, msg, ctx):
        p = msg['payload']
        md, tiles, scared = ctx['md'], ctx['tiles'], ctx['scared']
        exit_ = tuple(p['exit']) if p.get('exit') else None
        if exit_ is None:
            return
        elig = [g for g in tiles if g != msg['sender'] and not scared[g]]
        if idx not in elig:
            return
        winner = min(elig, key=lambda g: (md.distFrom(exit_).get(tiles[g], _FAR), g))
        if winner == idx:
            m.cutoff = (self.tick + SUPPORT_TICKS, exit_)
            self.stats['supportAcks'] += 1
            self._send(idx, msg['sender'], 'ACK', {'exit': list(exit_),
                       'eta': md.distFrom(exit_).get(tiles[idx], _FAR)}, ackOf=msg['id'])

    def _onWarn(self, idx, m, cap, ctx):
        md, tiles, scared = ctx['md'], ctx['tiles'], ctx['scared']
        pac = self._pred(m, md)
        racers = [g for g in tiles if not scared[g] and
                  md.distFrom(tiles[g]).get(cap, _FAR) <= md.distFrom(pac).get(cap, _FAR)]
        holders = {h for h, c in m.claims.items() if self._fresh(c) and c[0] == 'chaser'}
        pool = [g for g in racers if g not in holders] or racers
        if pool and min(pool, key=lambda g: (md.distFrom(tiles[g]).get(cap, _FAR), g)) == idx:
            m.guard = (self.tick + 6, cap)

    def _onScared(self, idx, m, ctx):
        md, tiles, scared = ctx['md'], ctx['tiles'], ctx['scared']
        if scared[idx]:
            return
        pac = self._pred(m, md)
        free = [g for g in tiles if not scared[g]]
        if free and min(free, key=lambda g: (md.distFrom(tiles[g]).get(pac, _FAR), g)) == idx:
            m.rescue = self.tick + 5

    # --- the decision ---------------------------------------------------------
    def decide(self, idx, state):
        self.decisions += 1
        tick = self.tick
        m = self.minds[idx]
        md = MazeDistances.get(state.getWalls())
        moves = ghostMoves(state, idx)
        if not moves:
            return Directions.STOP
        n = self.numGhosts
        tiles = {g: tileOf(state.getGhostPosition(g)) for g in range(1, n + 1)}
        scared = {g: state.getGhostState(g).scaredTimer > 0 for g in tiles}
        self.scaredTimers[idx] = int(state.getGhostState(idx).scaredTimer)
        myTile, iScared = tiles[idx], scared[idx]
        ctx = {'md': md, 'tiles': tiles, 'scared': scared}
        walls = md.walls

        # 1. own senses
        pacTrue = tileOf(state.getPacmanPosition())
        sees = canSense(md, myTile, pacTrue, self.radius)
        if sees:
            hv = Actions.directionToVector(state.getPacmanState().getDirection())
            heading = (int(hv[0]), int(hv[1]))
            self._learn(m, pacTrue, heading, tick, fromMsg=False)
        eaten = m.prevScared and m.prevTile is not None and manhattanDistance(m.prevTile, myTile) > 2
        if eaten and self.comms:
            self._send(idx, 'all', 'SCARED', {'event': 'eaten', 'pac': list(m.prevTile),
                                              'heading': [0, 0], 'age': 1})
            self.stats['eatenReports'] = self.stats.get('eatenReports', 0) + 1

        # 2. inbox
        for msg in self.bus.receive(idx):
            self._handle(idx, m, msg, ctx)

        age = tick - m.seen
        pred = self._pred(m, md)

        # 3. broadcast what I perceive (skip if a teammate already reported it this tick or last)
        if sees and self.comms:
            redundant = m.heard >= tick - 1
            if not redundant and (tick - m.lastSpot >= 3 or m.lastSpotVel != m.vel or m.lastSpot < tick - 3):
                self._send(idx, 'all', 'SPOTTED', {'pac': list(pacTrue), 'heading': list(m.vel), 'age': 0})
                m.lastSpot, m.lastSpotVel = tick, m.vel
            if iScared and tick - m.lastScaredMsg >= 3:
                self._send(idx, 'all', 'SCARED', {'event': 'scared', 'pac': list(pacTrue),
                                                  'heading': list(m.vel), 'age': 0, 'timer': self.scaredTimers[idx]})
                m.lastScaredMsg = tick
            dpac = md.distFrom(pacTrue)
            for cap in state.getCapsules():
                cap = (int(cap[0]), int(cap[1]))
                if dpac.get(cap, _FAR) <= 5 and tick - m.lastWarn.get(cap, -99) >= 6:
                    m.lastWarn[cap] = tick
                    self._send(idx, 'all', 'WARN_CAPSULE', {'cap': list(cap), 'pac': list(pacTrue),
                                                            'heading': list(m.vel), 'age': 0})
                    if not iScared and 'WARN_CAPSULE' not in self.off:
                        self._onWarn(idx, m, cap, ctx)

        # 4. role and target
        role, target, flee = self._resolve(idx, m, state, md, moves, ctx, age, pred, sees)
        m.role, m.target = role, target
        m.prevTile, m.prevScared = myTile, iScared
        self.roles[idx], self.assignedTargets[idx] = role, target if target is not None else myTile

        # 5. claims go out when role/target changed or are about to expire
        if self.comms and not iScared and target is not None and role in ROLES + ('search',):
            sc = m.sentClaim
            if sc is None or sc[0] != role or manhattanDistance(sc[1], target) > 2 or tick - sc[2] >= CLAIM_REFRESH:
                bid = self._bid(m, md, myTile, pred, age, role)
                if self._send(idx, 'all', 'CLAIM', {'role': role, 'target': list(target), 'bid': bid}):
                    m.sentClaim = (role, target, tick)

        # 6. move
        if flee is not None:
            return flee
        occupied = {t for g, t in tiles.items() if g != idx}
        return pickAction(moves, target, md, blocked=occupied)

    def _bid(self, m, md, myTile, pred, age, role):
        base = md.distFrom(pred).get(myTile, _FAR) + 3 * max(age, 0)
        if role == 'search':
            return age
        return base - (2 if m.role == role else 0)

    def _resolve(self, idx, m, state, md, moves, ctx, age, pred, sees):
        """Returns (role, target, fleeAction-or-None)."""
        tick, tiles, scared = self.tick, ctx['tiles'], ctx['scared']
        myTile = tiles[idx]
        # scared: flee from where I believe he is
        if scared[idx]:
            return 'scared', pred, fleeAction(moves, pred, myTile, md)
        # message-driven overrides
        if m.cutoff and m.cutoff[0] >= tick:
            return 'cutoff', m.cutoff[1], None
        if m.guard and m.guard[0] >= tick:
            cap = m.guard[1]
            if cap in [(int(c[0]), int(c[1])) for c in state.getCapsules()] and \
                    reachTime(moves, cap, md) <= md.distFrom(pred).get(cap, _FAR):
                return 'capsule_guard', cap, None
        if m.rescue and m.rescue >= tick and age <= FRESH_AGE:
            return 'rescue', pred, None

        active = sorted(g for g in tiles if not scared[g])
        if age > FRESH_AGE:
            return self._search(idx, m, md, ctx, age, active)

        dp = md.distFrom(pred)
        ranked = sorted(active, key=lambda g: (dp.get(tiles[g], _FAR), g))
        pref = ranked.index(idx) if idx in ranked else len(ROLES) - 1
        role = ROLES[min(pref, 3)]
        claims = {h: c for h, c in m.claims.items()
                  if h != idx and self._fresh(c) and not scared.get(h, True)}
        if tick < m.forcedUntil:
            role = 'chaser'
        else:
            if role == 'chaser' and tick < m.handedUntil:
                role = 'interceptor'
            if self.comms:
                k = ROLES.index(role)
                myBid = lambda r: self._bid(m, md, myTile, pred, age, r)
                while k < 3:
                    r = ROLES[k]
                    rivals = [(c[2], h) for h, c in claims.items() if c[0] == r]
                    if not rivals or (myBid(r), idx) < min(rivals):
                        break
                    k += 1
                role = ROLES[k]
        # chaser tile: the claimed holder if I hear one, else the nearest ghost by my belief
        chaserTile = None
        if role != 'chaser':
            holders = [h for h, c in claims.items() if c[0] == 'chaser']
            if holders:
                chaserTile = tiles[min(holders)]
            else:
                others = [g for g in ranked if g != idx]
                chaserTile = tiles[others[0]] if others else None
        if role == 'chaser' or chaserTile is None:
            target = pred
        elif role == 'interceptor':
            target = pincerTarget(moves, pred, chaserTile, md)
        elif role == 'blocker':
            target = pincerTarget(moves, pred, chaserTile, md, radius=8, nearest=False)
        else:
            target = approachTarget(moves, pred, chaserTile, md)

        # YIELD: a higher-priority ghost already claims (about) this tile
        if self.comms and role in ('interceptor', 'blocker', 'sweeper'):
            for h, c in sorted(claims.items()):
                if _PRIO.get(c[0], 9) < _PRIO[role] and manhattanDistance(c[1], target) <= 0:
                    alt = self._alt(md, moves, pred, c[1], target)
                    sent = None
                    if tick - m.lastYield.get(h, -99) >= 4:
                        m.lastYield[h] = tick
                        sent = self._send(idx, h, 'YIELD', {'tile': list(target), 'alt': list(alt)})
                        self.stats['yieldsSent'] += 1
                    if sent or tick - m.lastYield.get(h, -99) < 4 and 'YIELD' not in self.off:
                        target = alt
                    break
        if m.lock and m.lock[0] >= tick and m.lock[1] == role and m.lock[2] is not None:
            target = m.lock[2]
        if self.comms and role == 'chaser':
            self._chaserDuties(idx, m, md, moves, ctx, pred, age, sees)
        return role, target, None

    @staticmethod
    def _alt(md, moves, pred, avoid, near):
        """Replacement for a contested tile: closest-to-contested tile (within 3) that is not the winner's
        tile and still lies within 6 of Pac-Man, so the yielding ghost keeps its side of the squeeze."""
        best, bestKey = None, None
        dpac = md.distFrom(pred)
        for t, d in md.distFrom(near).items():
            if 1 <= d <= 3 and t != avoid and dpac.get(t, _FAR) <= 6 and \
                    md.distFrom(avoid).get(t, _FAR) >= 2:
                key = (d, reachTime(moves, t, md), t)
                if bestKey is None or key < bestKey:
                    best, bestKey = t, key
        return best if best is not None else near

    def _chaserDuties(self, idx, m, md, moves, ctx, pred, age, sees):
        """The chaser may ask for support or hand the chase to the ghost ahead of Pac-Man."""
        tick, tiles, scared = self.tick, ctx['tiles'], ctx['scared']
        if age > 1:
            m.gap.clear()
            return
        myTile = tiles[idx]
        dp = md.distFrom(pred)
        d = dp.get(myTile, _FAR)
        m.gap.append((tick, d))
        # HANDOFF: a teammate is clearly closer and Pac-Man is running toward it
        if m.vel != (0, 0):
            ahead = (pred[0] + m.vel[0], pred[1] + m.vel[1])
            cands = []
            for g, t in tiles.items():
                if g == idx or scared[g]:
                    continue
                dg = dp.get(t, _FAR)
                if dg <= d - 2 and md.distFrom(t).get(ahead, _FAR) < dg:
                    cands.append((dg, g))
            if cands and tick >= m.handedUntil:
                g = min(cands)[1]
                if self._send(idx, g, 'HANDOFF', {'pac': list(pred), 'heading': list(m.vel), 'age': age}):
                    m.handedUntil = tick + 6
                    self.stats['handoffs'] += 1
                    return
        # REQUEST_SUPPORT: not closing in
        if (len(m.gap) >= GAP_WINDOW and m.gap[-GAP_WINDOW][0] >= tick - GAP_WINDOW - 1 and
                m.gap[-GAP_WINDOW][1] - d < 1 and d >= 3 and tick - m.lastReq >= 10 and tick >= m.supportUntil):
            exit_ = self._exitTile(md, pred, myTile)
            if exit_ is not None:
                msg = self._send(idx, 'all', 'REQUEST_SUPPORT',
                                 {'pac': list(pred), 'heading': list(m.vel), 'age': age,
                                  'exit': list(exit_), 'gap': d, 'ticks': GAP_WINDOW})
                m.lastReq = tick
                m.lastReqId = msg['id'] if msg else None

    def _search(self, idx, m, md, ctx, age, active):
        """Stale belief: spread over where he could be (reachable since last seen, not sensed by me)."""
        tick, tiles = self.tick, ctx['tiles']
        myTile = tiles[idx]
        a = min(age, MAX_SEARCH_AGE)
        dl = md.distFrom(m.pac)
        dm = md.distFrom(myTile)
        walls = md.walls

        def sensed(t):
            return dm.get(t, _FAR) <= self.radius or lineOfSight(walls, myTile, t)
        cand = [t for t, d in dl.items() if max(1, a - 2) <= d <= a and not sensed(t)]
        if not cand:
            cand = [t for t, d in dl.items() if d <= a and not sensed(t)]
        if not cand:
            cand = sorted((t for t in dl if not sensed(t)), key=lambda t: (dl[t], t))[:40]
        if not cand:
            return 'search', m.pac, None
        cand.sort()
        searchers = list(active)
        if self.comms:
            for h, c in m.claims.items():
                if h == idx or not self._fresh(c) or h not in searchers:
                    continue
                if c[0] == 'search':
                    cand2 = [t for t in cand if manhattanDistance(t, c[1]) > 2]
                    cand = cand2 or cand
                    searchers.remove(h)
                elif c[0] in ROLES:
                    searchers.remove(h)          # already hunting on live information
        if idx not in searchers:
            searchers.append(idx)
            searchers.sort()
        proj = advance(walls, m.pac, m.vel, a)
        seeds = [min(cand, key=lambda t: (manhattanDistance(t, proj), t))]
        while len(seeds) < len(searchers) and len(seeds) < len(cand):
            seeds.append(max((t for t in cand if t not in seeds),
                             key=lambda t: (min(md.distFrom(s).get(t, _FAR) for s in seeds), t)))
        # greedy nearest ghost <-> seed assignment
        free, mine = list(searchers), None
        pool = list(seeds)
        while free and pool:
            g, s = min(((g, s) for g in free for s in pool),
                       key=lambda gs: (md.distFrom(tiles[gs[0]]).get(gs[1], _FAR), gs[0], gs[1]))
            if g == idx:
                mine = s
                break
            free.remove(g)
            pool.remove(s)
        return 'search', mine if mine is not None else seeds[0], None

    # --- telemetry ---------------------------------------------------------
    def getTelemetry(self):
        walls_free = True
        anyScared = any(t > 0 for t in self.scaredTimers.values())
        hunting = any(self.tick - m.seen <= FRESH_AGE for m in self.minds.values())
        self.currentTacticalState = 'SCATTER' if anyScared else ('COORDINATED_HUNT' if hunting else 'SEARCH')
        msgs = []
        for g in self.bus.thisTick:
            d = {'id': g['id'], 'tick': g['tick'], 'from': g['sender'], 'to': g['to'], 'type': g['type'],
                 'payload': dict(g['payload'])}
            if g['ackOf'] is not None:
                d['ackOf'] = g['ackOf']
            if g.get('lost'):
                d['lost'] = list(g['lost'])
            msgs.append(d)
        return {
            'tacticalState': self.currentTacticalState,
            'macroStrategy': None,
            'roles': {int(g): str(r) for g, r in self.roles.items()},
            'targets': {int(g): [int(t[0]), int(t[1])] for g, t in self.assignedTargets.items()},
            'scaredTimers': {int(g): int(t) for g, t in self.scaredTimers.items()},
            'messages': msgs,
            'beliefs': {int(g): {'pacTile': None if m.pac is None else [int(m.pac[0]), int(m.pac[1])],
                                 'age': int(self.tick - m.seen)} for g, m in sorted(self.minds.items())},
            'messageCounts': dict(self.bus.counts),
            'comms': bool(self.comms),
            'fogRadius': int(self.radius),
            'tick': int(self.tick),
        }


# =============================================================================
# Teams (pass to -g)
# =============================================================================

class _FogTeam(Agent):
    COMMS = True
    LOSS = 0.0
    _coordinator = None        # one ChatterHub per concrete class; replaced at every game start

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        cls._coordinator = None

    def __init__(self, index=1):
        self.index = index

    @classmethod
    def _newHub(cls):
        radius = int(os.environ.get('GHOST_FOG_RADIUS', FOG_RADIUS))
        off = [t for t in os.environ.get('GHOST_MSG_OFF', '').split(',') if t]
        return ChatterHub(comms=cls.COMMS, loss=cls.LOSS, radius=radius, seed=12345, off=off)

    def registerInitialState(self, state):
        cls = type(self)
        hub = cls._coordinator
        # all ghosts register before the first move: the first creates the hub, the rest share it
        if hub is None or hub.started and hub.lastCaller != _FAR:
            hub = cls._coordinator = cls._newHub()
        if not hub.started:
            hub.start(state)

    def getAction(self, state):
        cls = type(self)
        hub = cls._coordinator
        if hub is None:
            hub = cls._coordinator = cls._newHub()
        hub.begin(self.index, state)
        return hub.decide(self.index, state)


class ChatterGhostTeam(_FogTeam):
    """Fog of war plus a real message bus."""
    COMMS = True


class SilentFogGhostTeam(_FogTeam):
    """Same logic and same fog, bus disabled: the control for the ablation."""
    COMMS = False


class LossyChatterGhostTeam(_FogTeam):
    """ChatterGhostTeam where each delivery is dropped with probability 0.5."""
    COMMS = True
    LOSS = 0.5
