"""VERSUS: one Pac-Man agent, one maze, one seed, played against the original ghosts and against our ghosts.

Both games are real runs of the live engine (live.build_game + live.FrameDisplay, the same code the arcade
uses), recorded frame by frame.  The browser then plays the two recordings side by side and shows the
counters and the verdict, so every number on screen comes from a finished game.

Why the two games run one after the other and not at the same time: the engine seeds the process-wide random
generator and keeps rule and coordinator state in module globals, so two concurrent games would change each
other's dice.  One after the other with the same seed is deterministic: the same request always gives the
same two games.

Memory: one worker thread, at most MAX_TICKS frames per side, results kept as one JSON string and dropped on
stop().  Nothing is written to disk.

    POST /api/versus/start  {layout, seed, maxTicks}      GET /api/versus      POST /api/versus/stop
"""
import json
import sys
import threading
import time
from functools import partial

import live

SIDES = (
    dict(id='stock', ghosts='DirectionalGhost', label='ORIGINAL GHOSTS'),
    dict(id='ours', ghosts='EnhancedCoordinatedGhostTeam', label='OUR GHOSTS'),
)
PACMAN = 'GreedyAgent'
DEFAULT_LAYOUT = 'mediumClassic'
DEFAULT_SEED = 7
DEFAULT_MAX_TICKS = 400
MAX_TICKS = 600


class _CancelDisplay(live.FrameDisplay):
    """FrameDisplay that ends the game as soon as the run is cancelled."""

    def __init__(self, builder, meta, sink, max_ticks=None, cancel=None):
        super().__init__(builder, meta, sink, max_ticks)
        self.cancel = cancel

    def update(self, data):
        super().update(data)
        if self.cancel is not None and self.cancel.is_set() and self.game is not None:
            self.game.gameOver = True


class _Sink:
    def __init__(self, rate):
        self.h, self.frames, self.rate = None, [], rate

    def header(self, h): self.h = h
    def frame(self, f): self.frames.append(f)
    def dt(self): return round(1.0 / self.rate, 4)


def clean(raw):
    layout = str(raw.get('layout') or DEFAULT_LAYOUT)
    if not live.IDENT_RE.match(layout):
        raise ValueError('bad layout: %r' % layout)
    return dict(layout=layout, pacman=PACMAN, seed=int(raw.get('seed', DEFAULT_SEED)),
                maxTicks=max(50, min(int(raw.get('maxTicks', DEFAULT_MAX_TICKS)), MAX_TICKS)))


def play_side(side, p, cancel=None, rate=15.0):
    """One real game.  Returns dict(id, label, ghosts, header, frames, ticks, caughtAt, cleared, score, ...)."""
    params = live.clean_params(dict(layout=p['layout'], pacman=p['pacman'], ghosts=side['ghosts'], arcade=False,
                                    seed=p['seed'], tickRate=rate, maxTicks=p['maxTicks']))
    sink = _Sink(params['tickRate'])
    b = live.build_game(params, sink, live=False, display_cls=partial(_CancelDisplay, cancel=cancel))
    b['game'].run()
    st = b['game'].state
    ticks = len(sink.frames) - 1
    lose, win = bool(st.isLose()), bool(st.isWin())
    return dict(id=side['id'], label=side['label'], ghosts=side['ghosts'], header=sink.h, frames=sink.frames,
                ticks=ticks, caughtAt=ticks if lose else None, cleared=win, score=st.getScore(),
                foodLeft=st.getNumFood(), truncated=bool(b['display'].truncated))


def _moves(n):
    return '%d move%s' % (n, '' if n == 1 else 's')


def verdict(stock, ours, max_ticks):
    """One plain sentence (two at most) built only from the two finished runs (dicts from play_side)."""
    a, b = stock['caughtAt'], ours['caughtAt']
    if a is not None and b is not None:
        if a == b:
            return 'Both teams caught Pac-Man in %s. A tie on this maze and seed.' % _moves(a)
        fast, slow = (('OUR GHOSTS', b), ('the original ghosts', a)) if b < a else (('The original ghosts', a), ('our ghosts', b))
        return '%s caught Pac-Man in %s, %s needed %s: %s faster.' % (fast[0], _moves(min(a, b)), slow[0], _moves(max(a, b)),
                                                                     _moves(abs(a - b)))
    if b is not None:
        return 'OUR GHOSTS caught Pac-Man in %s. The original ghosts did not catch him in %s.' % (
            _moves(b), _moves(stock['ticks']))
    if a is not None:
        return 'The original ghosts caught Pac-Man in %s. Our ghosts did not catch him in %s.' % (
            _moves(a), _moves(ours['ticks']))
    return 'Neither team caught Pac-Man in %d moves. Final scores: original %d, ours %d.' % (
        max_ticks, stock['score'], ours['score'])


class Versus:
    """The single VERSUS job (one at a time, one worker thread)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.thread = None
        self.reset()

    def reset(self):
        self.state, self.params, self.error, self.done_sides, self.payload = 'idle', None, None, 0, None

    def start(self, raw):
        p = clean(raw)
        self.stop()
        for mod in {id(m): m for m in (live, sys.modules.get('__main__'))}.values():
            s = getattr(getattr(mod, 'LIVE', None), 'session', None)     # server run as a script: two copies of live
            if s is not None:                  # a live game would share the random generator
                s.stop()
                s.thread.join(timeout=3)
        with self.lock:
            self.cancel = threading.Event()
            self.reset()
            self.state, self.params = 'running', p
            self.thread = threading.Thread(target=self._run, args=(p, self.cancel), daemon=True, name='versus')
            self.thread.start()
        return p

    def _run(self, p, cancel):
        try:
            sides = []
            for side in SIDES:
                sides.append(play_side(side, p, cancel))
                self.done_sides = len(sides)
                if cancel.is_set():
                    return
            text = verdict(sides[0], sides[1], p['maxTicks'])
            payload = json.dumps(dict(params=p, verdict=text, sides=sides), separators=(',', ':'))
            if not cancel.is_set():
                self.payload, self.state = payload, 'done'
        except Exception as exc:              # surface to the page
            import traceback
            traceback.print_exc()
            self.error, self.state = str(exc), 'error'

    def status(self):
        d = dict(state=self.state, params=self.params, doneSides=self.done_sides, sides=len(SIDES))
        if self.error:
            d['error'] = self.error
        return d

    def stop(self):
        """Cancel a running job, wait for the worker and drop the stored frames."""
        t = self.thread
        self.cancel.set()
        if t is not None and t.is_alive():
            t.join(timeout=10)
        with self.lock:
            self.reset()
        self.thread = None


VERSUS = Versus()
