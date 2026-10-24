#!/usr/bin/env python3
"""Headless game recorder: runs a Pac-Man game and writes a JSONL trace.

It never edits the framework. A recording display (duck-typed like
textDisplay.NullGraphics) is handed to ClassicGameRules, so every
display.update() call from Game.run() reaches us. We emit one frame per full
round (Pac-Man plus every ghost has moved), reading coordinator attributes
defensively.

    python3 dashboard/record.py -l mediumClassic -p GreedyAgent \
        -g EnhancedCoordinatedGhostTeam --seed 7 -n 1 --max-ticks 300
"""
import argparse
import json
import os
import random
import re
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GAME_DIR = os.environ.get('PACMAN_GAME_DIR', os.path.join(REPO, 'multiagent'))
TRACE_DIR = os.path.join(HERE, 'traces')
SCHEMA_VERSION = 1


def _tup(p):
    return [int(p[0]), int(p[1])] if p is not None else None


def _json_safe(v, depth=0):
    """Best-effort conversion of coordinator telemetry to JSON-able data."""
    if depth > 4:
        return str(v)
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [_json_safe(x, depth + 1) for x in v]
    return str(v)


def bfs_path(walls, start, goal, limit=80):
    """Shortest tile path start->goal (inclusive), or [] if none."""
    if start is None or goal is None:
        return []
    start, goal = tuple(start), tuple(goal)
    if start == goal:
        return [list(start)]
    W, H = walls.width, walls.height
    prev = {start: None}
    dq = deque([start])
    while dq:
        cur = dq.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            n = (cur[0] + dx, cur[1] + dy)
            if not (0 <= n[0] < W and 0 <= n[1] < H) or n in prev or walls[n[0]][n[1]]:
                continue
            prev[n] = cur
            if n == goal:
                path = [n]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                path.reverse()
                return [list(p) for p in path[:limit]]
            dq.append(n)
    return []


class RecordingDisplay:
    """Quacks like textDisplay.NullGraphics; captures frames instead of drawing."""

    def __init__(self, ghost_cls, meta, max_ticks):
        self.ghost_cls = ghost_cls
        self.meta = meta
        self.max_ticks = max_ticks
        self.header = None
        self.frames = []
        self.game = None          # set by the caller after newGame()
        self.num_agents = 1
        self._updates = 0
        self._last_data = None
        self.truncated = False

    # --- NullGraphics protocol -------------------------------------------
    def initialize(self, data, isBlue=False):
        walls = data.layout.walls
        self.num_agents = len(data.agentStates)
        self.header = dict(
            type='header', schema=SCHEMA_VERSION,
            width=walls.width, height=walls.height,
            walls=[''.join('%' if walls[x][y] else ' ' for x in range(walls.width))
                   for y in range(walls.height - 1, -1, -1)],   # row 0 = top
            numGhosts=self.num_agents - 1,
            foodTotal=data.food.count(), **self.meta)
        self._emit(data)

    def update(self, data):
        self._last_data = data
        self._updates += 1
        if self._updates % self.num_agents == 0:
            self._emit(data)
            if len(self.frames) > self.max_ticks and self.game is not None:
                self.truncated = True
                self.game.gameOver = True

    def finish(self):
        d = self._last_data
        if d is not None and self._updates % self.num_agents != 0:
            self._emit(d)       # game ended mid-round; keep the final state

    def checkNullDisplay(self):
        return True

    def pause(self):
        pass

    def draw(self, state):
        pass

    def updateDistributions(self, dist):
        pass

    # --- frame capture ----------------------------------------------------
    def _coordinator(self):
        c = getattr(self.ghost_cls, '_coordinator', None)
        if c is None:
            mod = sys.modules.get(self.ghost_cls.__module__)
            c = getattr(mod, '_coordinator_instance', None)
        return c

    def _emit(self, data):
        walls = data.layout.walls
        c = self._coordinator()
        roles, targets, reserved = {}, {}, {}
        tactical = macro = None
        extra = None
        if c is not None:
            roles = dict(getattr(c, 'roles', {}) or {})
            targets = dict(getattr(c, 'assignedTargets', {}) or {})
            reserved = dict(getattr(c, 'reservedTiles', {}) or {})
            tactical = getattr(c, 'currentTacticalState', None)
            macro = getattr(c, 'currentStrategy', None)
            tele = getattr(c, 'getTelemetry', None)
            if callable(tele):
                try:
                    t = tele()
                    if isinstance(t, dict):
                        extra = _json_safe(t)
                        tactical = t.get('tacticalState', t.get('currentTacticalState', tactical))
                        macro = t.get('macroStrategy', t.get('currentStrategy', macro))
                except Exception as exc:   # telemetry must never kill a recording
                    extra = {'error': repr(exc)}
        pac = data.agentStates[0]
        ghosts = []
        for i in range(1, len(data.agentStates)):
            s = data.agentStates[i]
            pos = _tup(s.configuration.getPosition())
            tgt = targets.get(i)
            ghosts.append(dict(
                index=i, pos=pos,
                dir=str(s.configuration.direction),
                scaredTimer=int(s.scaredTimer),
                role=roles.get(i), target=_tup(tgt),
                path=bfs_path(walls, pos, tgt) if tgt is not None else []))
        predicted = next((_tup(targets[i]) for i, r in roles.items()
                          if r == 'interceptor' and i in targets), None)
        if tactical == 'SCATTER':      # targets are flee tiles, not a prediction
            predicted = None
        frame = dict(
            type='frame', tick=len(self.frames),
            score=data.score,
            pacman=dict(pos=_tup(pac.configuration.getPosition()),
                        dir=str(pac.configuration.direction)),
            ghosts=ghosts,
            food=sorted([x, y] for x in range(walls.width)
                        for y in range(walls.height) if data.food[x][y]),
            capsules=[_tup(c_) for c_ in data.capsules],
            tacticalState=tactical, macroStrategy=macro,
            predictedPacman=predicted,
            reservedTiles=[dict(ghost=int(g), tile=_tup(t)) for g, t in sorted(reserved.items())],
        )
        if extra is not None:
            frame['telemetry'] = extra
        self.frames.append(frame)


def _reset_coordinators(ghost_cls):
    """Coordinators are process-level singletons; reset so games don't leak state."""
    if hasattr(ghost_cls, '_coordinator'):
        ghost_cls._coordinator = None
    mod = sys.modules.get(ghost_cls.__module__)
    if mod is not None and hasattr(mod, '_coordinator_instance'):
        mod._coordinator_instance = None


def _load_game_modules():
    if GAME_DIR not in sys.path:
        sys.path.insert(0, GAME_DIR)
    import pacman
    import layout as layout_mod
    return pacman, layout_mod


def record_game(layout_name='mediumClassic', pacman_agent='GreedyAgent',
                ghost_team='EnhancedCoordinatedGhostTeam', seed=0,
                max_ticks=400, game_no=1, out_dir=TRACE_DIR, write=True):
    """Run one game; return (path_or_None, header, frames, footer)."""
    prev_cwd = os.getcwd()
    os.chdir(GAME_DIR)
    try:
        pacman, layout_mod = _load_game_modules()
        lay = layout_mod.getLayout(layout_name)
        if lay is None:
            raise ValueError('layout not found: %s' % layout_name)
        pac_cls = pacman.loadAgent(pacman_agent, True)
        ghost_cls = pacman.loadAgent(ghost_team, True)
        _reset_coordinators(ghost_cls)
        random.seed(seed)
        pac = pac_cls()
        ghosts = [ghost_cls(i + 1) for i in range(lay.getNumGhosts())]
        meta = dict(layout=layout_name, pacmanAgent=pacman_agent, ghostTeam=ghost_team,
                    seed=seed, game=game_no, maxTicks=max_ticks,
                    recordedAt=time.strftime('%Y-%m-%dT%H:%M:%S'))
        disp = RecordingDisplay(ghost_cls, meta, max_ticks)
        rules = pacman.ClassicGameRules(30)
        game = rules.newGame(lay, pac, ghosts, disp, quiet=True)
        disp.game = game
        game.run()
        st = game.state
        footer = dict(type='end', ticks=len(disp.frames) - 1, score=st.getScore(),
                      win=bool(st.isWin()), lose=bool(st.isLose()), truncated=disp.truncated)
    finally:
        os.chdir(prev_cwd)
    path = None
    if write:
        os.makedirs(out_dir, exist_ok=True)
        slug = re.sub(r'[^A-Za-z0-9]+', '', ghost_team)
        path = os.path.join(out_dir, '%s_%s_%s_s%d_g%d.jsonl' % (
            layout_name, pacman_agent, slug, seed, game_no))
        with open(path, 'w', encoding='utf-8') as f:
            for rec in [disp.header] + disp.frames + [footer]:
                f.write(json.dumps(rec, separators=(',', ':')) + '\n')
    return path, disp.header, disp.frames, footer


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('-l', '--layout', default='mediumClassic')
    ap.add_argument('-p', '--pacman', default='GreedyAgent')
    ap.add_argument('-g', '--ghosts', default='EnhancedCoordinatedGhostTeam')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('-n', '--games', type=int, default=1)
    ap.add_argument('--max-ticks', type=int, default=400)
    ap.add_argument('--out-dir', default=TRACE_DIR)
    a = ap.parse_args(argv)
    for g in range(a.games):
        path, _, frames, footer = record_game(a.layout, a.pacman, a.ghosts, a.seed + g,
                                              a.max_ticks, g + 1, a.out_dir)
        print(json.dumps(dict(path=path, frames=len(frames), score=footer['score'],
                              win=footer['win'], lose=footer['lose'])))


if __name__ == '__main__':
    main()
