"""Arcade campaign layer: lives, READY!, GAME OVER, extra life, level progression, bonus fruit.

This sits on top of dashboard/live.py.  The game engine (multiagent/pacman.py) plays ONE life on ONE maze and
ends when Pac-Man is caught or the maze is cleared.  A CampaignSession runs a sequence of those games:

    life lost  -> new game on the same maze, the dots already eaten stay eaten, the score carries over
    maze clear -> new game, level + 1 (arcade mode: the arcade speed/fright tables for that level)
    last life  -> GAME OVER

Nothing in the framework is edited.  Scoring is whatever the rules in force give (Berkeley or arcade); the
only points this layer adds are bonus fruit (arcade rules only).  `ArcadeProgress` holds the pure rules so
they can be unit tested without a game.
"""
import json
import time
from functools import partial

import live

EXTRA_LIFE_AT = 10000
START_LIVES = 3
# level -> (fruit, points).  Classic order of the Pac-Man bonus items; levels past 13 stay on the key.
FRUIT_TABLE = [('cherry', 100), ('strawberry', 300), ('orange', 500), ('orange', 500), ('apple', 700),
               ('apple', 700), ('melon', 1000), ('melon', 1000), ('galaxian', 2000), ('galaxian', 2000),
               ('bell', 3000), ('bell', 3000), ('key', 5000)]
FRUIT_AT = (0.30, 0.70)           # fraction of the maze's dots eaten when a fruit appears
FRUIT_SECONDS = 9.5


def fruit_for(level):
    return FRUIT_TABLE[min(max(level, 1), len(FRUIT_TABLE)) - 1]


class ArcadeProgress:
    """Lives and level bookkeeping.  `lives` counts Pac-Mans left INCLUDING the one in play."""

    def __init__(self, lives=START_LIVES, extra_at=EXTRA_LIFE_AT, level=1):
        self.lives = int(lives)
        self.level = int(level)
        self.extra_at = extra_at
        self.extra_given = False
        self.over = False

    def score_update(self, score):
        """Call with the running score; returns True exactly once, when the extra life is awarded."""
        if not self.extra_given and score >= self.extra_at:
            self.extra_given = True
            self.lives += 1
            return True
        return False

    def died(self):
        """Pac-Man was caught.  Returns True when another life remains, False on GAME OVER."""
        self.lives -= 1
        if self.lives <= 0:
            self.lives, self.over = 0, True
            return False
        return True

    def cleared(self):
        self.level += 1
        return self.level


def install_node_counter(mod):
    """Count GameState.generateSuccessor calls (a stand-in for 'nodes expanded' in game-tree agents)."""
    gs = mod.GameState
    if getattr(gs, '_nodes_counted', False):
        return
    orig = gs.generateSuccessor

    def generateSuccessor(self, agentIndex, action):
        COUNTER[0] += 1
        return orig(self, agentIndex, action)
    gs.generateSuccessor = generateSuccessor
    gs._nodes_counted = True


COUNTER = [0]


class StatPaced(live.Paced):
    """Paced AI Pac-Man that records decision time and game-tree nodes per move."""

    def __init__(self, inner, session):
        super().__init__(inner, session)
        self.n = 0
        self.total_ms = 0.0
        self.total_nodes = 0
        self.last_ms = 0.0
        self.last_nodes = 0
        self.max_ms = 0.0

    def getAction(self, state):
        self.session.wait_tick()
        n0, t0 = COUNTER[0], time.perf_counter()
        action = self.inner.getAction(state)
        self.last_ms = 1000 * (time.perf_counter() - t0)
        self.last_nodes = COUNTER[0] - n0
        self.n += 1
        self.total_ms += self.last_ms
        self.total_nodes += self.last_nodes
        self.max_ms = max(self.max_ms, self.last_ms)
        return action

    def stats(self, name, depth):
        n = max(self.n, 1)
        return dict(name=name, depth=depth, decisions=self.n, lastMs=round(self.last_ms, 2),
                    avgMs=round(self.total_ms / n, 2), maxMs=round(self.max_ms, 2),
                    lastNodes=self.last_nodes, avgNodes=round(self.total_nodes / n, 1))


class HudBuilder(live.FrameBuilder):
    """FrameBuilder + the arcade HUD block and AI decision stats."""

    def __init__(self, ghost_cls, state, session=None):
        super().__init__(ghost_cls, state)
        self.session = session

    def header(self, state, meta):
        h = super().header(state, meta)
        if self.session is not None and self.session.level_food:
            h['foodTotal'] = self.session.level_food
        return h

    def frame(self, state, tick, dt):
        f = super().frame(state, tick, dt)
        s = self.session
        if s is not None:
            f['hud'] = s.hud()
            if isinstance(s.agent, StatPaced):
                f['ai'] = s.agent.stats(s.params['pacman'], s.params.get('depth'))
        return f


class CampaignDisplay(live.FrameDisplay):
    """FrameDisplay that also applies fruit pickups and the extra life before each frame is cut."""

    def update(self, data):
        s = self.builder.session
        if s is not None and self.game is not None:
            s.after_move(self.game.state.data)
        super().update(data)


class CampaignSession(live.Session):
    def __init__(self, hub, params):
        super().__init__(hub, params)
        self.prog = ArcadeProgress(params.get('lives', START_LIVES), level=params.get('level', 1))
        self.phase = 'ready'
        self.score = 0
        self.level_food = None
        self.fruit = None            # dict(kind, points, pos, ttl)
        self.fruit_spawned = 0
        self.pac_start = None
        self.events = []
        self.params.setdefault('readyDelay', 2.0)

    # ---- state shared with the frames --------------------------------------------------------------
    def hud(self):
        self.tick_fruit()
        ev, self.events = self.events, []
        return dict(lives=self.prog.lives, level=self.prog.level, phase=self.phase, events=ev,
                    fruit=self.fruit and dict(kind=self.fruit['kind'], points=self.fruit['points'],
                                              pos=list(self.fruit['pos'])),
                    fruitHistory=[fruit_for(l)[0] for l in range(max(1, self.prog.level - 6), self.prog.level + 1)])

    def status(self):
        s = super().status()
        s.update(phase=self.phase, lives=self.prog.lives, level=self.prog.level, score=self.score)
        return s

    def pace(self, inner):
        return StatPaced(inner, self)

    def wait_tick(self):
        super().wait_tick()
        if self.phase == 'ready' and not self.stopped:
            self.phase = 'playing'
            self.publish_status()

    # ---- per-move rules ------------------------------------------------------------------------------
    def after_move(self, data):
        self.score = data.score
        if self.params['arcade'] and self.pac_start is not None:
            eaten = self.level_food - data.food.count() if self.level_food else 0
            if self.fruit is None and self.fruit_spawned < len(FRUIT_AT) and self.level_food and \
                    eaten >= FRUIT_AT[self.fruit_spawned] * self.level_food:
                kind, pts = fruit_for(self.prog.level)
                self.fruit = dict(kind=kind, points=pts, pos=self.pac_start,
                                  ttl=int(FRUIT_SECONDS * self.tickRate))
                self.fruit_spawned += 1
            if self.fruit is not None:
                pp = data.agentStates[0].configuration.getPosition()
                if (int(pp[0] + 0.5), int(pp[1] + 0.5)) == self.fruit['pos']:
                    data.score += self.fruit['points']
                    self.events.append(['fruit', self.fruit['kind'], self.fruit['points']])
                    self.fruit = None
                    self.score = data.score
        if self.prog.score_update(data.score):
            self.events.append(['extra'])

    def tick_fruit(self):
        if self.fruit is not None:
            self.fruit['ttl'] -= 1
            if self.fruit['ttl'] <= 0:
                self.fruit = None

    # ---- main loop -------------------------------------------------------------------------------------
    def _sleep(self, secs):
        end = time.monotonic() + secs
        while not self.stopped and time.monotonic() < end:
            time.sleep(0.03)

    def _run(self):
        try:
            with live.in_game_dir():
                import pacman
            install_node_counter(pacman)
            carry_score, carry_food, carry_caps, n = 0, None, None, 0
            while not self.stopped:
                p = dict(self.params)
                p['level'] = self.prog.level
                p['seed'] = self.params['seed'] + n
                n += 1
                self.phase, self.next, self.fruit, self.events = 'ready', None, None, []
                b = live.build_game(p, self, live=True, display_cls=CampaignDisplay,
                                    builder_cls=partial(HudBuilder, session=self))
                self.game, self.agent = b['game'], b['agent']
                d = self.game.state.data
                self.pac_start = tuple(int(c + 0.5) for c in d.agentStates[0].start.getPosition())
                if carry_food is None:
                    self.level_food, self.fruit_spawned = d.food.count(), 0
                else:
                    d.food, d.capsules = carry_food, carry_caps
                d.score = carry_score
                self.score = d.score
                self.state = 'running'
                self.publish_status()
                self.game.run()
                st = self.game.state
                self.score = st.getScore()
                if self.stopped:
                    break
                if st.isWin():
                    self.phase = 'cleared'
                    self.publish_status()
                    self._sleep(2.2)
                    self.prog.cleared()
                    carry_score, carry_food, carry_caps = st.getScore(), None, None
                elif st.isLose():
                    self.phase = 'dying'
                    self.publish_status()
                    self._sleep(1.8)
                    carry_score = st.getScore()
                    carry_food, carry_caps = st.data.food, list(st.data.capsules)
                    if not self.prog.died():
                        break
                else:
                    break
            over = self.prog.over
            if over:
                self.phase = 'gameover'
            self.result = dict(score=self.score, win=False, lose=over, gameover=over, stopped=self.stopped,
                               level=self.prog.level, lives=self.prog.lives)
            self.state = 'over'
            self.hub.publish('end', json.dumps(dict(type='end', ticks=self.tick, **self.result)))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.state = 'error'
            self.result = dict(error=str(exc))
            self.hub.publish('end', json.dumps(dict(type='end', error=str(exc))))
        finally:
            self.publish_status()
