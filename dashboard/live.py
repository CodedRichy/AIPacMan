#!/usr/bin/env python3
"""Live play + smooth replay for the Hunt Table dashboard (stdlib only, 127.0.0.1 only).

    python3 dashboard/live.py [--port 8765] [--autostart]          # server with live play at /live
    python3 dashboard/live.py record -l originalClassic -p GreedyAgent -g ArcadeGhostTeam --arcade --max-ticks 600

The game loop runs in this process on a worker thread.  Frames go to the browser over
Server-Sent Events (`GET /live/stream`); the keyboard comes back as small POSTs
(`POST /api/key`).  The Pac-Man agent (`BrowserKeyboardAgent`) is also the metronome:
its getAction waits for the next tick, so one framework round = one tick = one frame.

Routes added on top of server.py (which is reused, not edited)
  GET  /live                     the live page (static/live.html)
  GET  /live/stream              SSE: header, frame, status, end
  GET  /api/live/state           current session summary
  POST /api/live/start           {layout, ghosts, pacman, arcade, level, tickRate, seed}
  POST /api/live/pause           {paused: bool}  (omit to toggle)
  POST /api/live/rate            {tickRate: n}
  POST /api/live/stop
  POST /api/key                  {dir: "North|South|East|West"} or {key: "ArrowUp|w|..."}

Frame schema v2 = v1 plus: `schema`, `dt`, `pacman.fpos`, `ghosts[].fpos`, `ghosts[].mode`,
`arcade`, `commander` (see schema.md).  v1 readers keep working: `pos` is still the nearest tile.
"""
import argparse
import contextlib
import json
import os
import queue
import random
import re
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GAME_DIR = os.environ.get('PACMAN_GAME_DIR', os.path.join(REPO, 'multiagent'))
for _p in (HERE, GAME_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import commander as cmd          # noqa: E402
import record as rec             # noqa: E402
import server as base            # noqa: E402
from game import Agent, Directions   # noqa: E402

SCHEMA_VERSION = 2
IDENT_RE = base.IDENT_RE
_cwd_lock = threading.RLock()


@contextlib.contextmanager
def in_game_dir():
    """loadAgent() and layouts use paths relative to the game directory."""
    with _cwd_lock:
        prev = os.getcwd()
        os.chdir(GAME_DIR)
        try:
            yield
        finally:
            os.chdir(prev)


KEYMAP = {
    'North': 'North', 'South': 'South', 'East': 'East', 'West': 'West',
    'ArrowUp': 'North', 'ArrowDown': 'South', 'ArrowRight': 'East', 'ArrowLeft': 'West',
    'w': 'North', 's': 'South', 'd': 'East', 'a': 'West',
    'W': 'North', 'S': 'South', 'D': 'East', 'A': 'West',
}


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class BrowserKeyboardAgent(Agent):
    """Pac-Man steered from the browser, and the game's metronome.

    The browser POSTs a direction; the agent remembers the latest one (a held joystick) and
    takes it as soon as it is legal, which gives the arcade's pre-turn feel at corners."""

    def __init__(self, session=None, index=0):
        self.index = index
        self.session = session
        self.want = None
        self.last = Directions.WEST
        self.lock = threading.Lock()

    def press(self, direction):
        with self.lock:
            self.want = direction

    def getAction(self, state):
        if self.session is not None:
            self.session.wait_tick()
        legal = state.getLegalActions(self.index)
        with self.lock:
            want = self.want
        if want in legal:
            move = want
        elif self.last in legal:
            move = self.last
        else:
            move = Directions.STOP if Directions.STOP in legal else legal[0]
        if move != Directions.STOP:
            self.last = move
        return move


class SnapGhost(Agent):
    """Lets Berkeley-style ghost teams (which assume whole-tile positions) play under arcade rules:
    they decide on a copy of the state with every agent snapped to its nearest tile; the answer is used
    when it is legal, otherwise the first legal action."""

    def __init__(self, inner):
        self.inner, self.index = inner, inner.index

    def getAction(self, state):
        from game import Configuration
        legal = state.getLegalActions(self.index)
        if len(legal) <= 1:
            return legal[0] if legal else Directions.STOP
        snap = state.deepCopy()
        for a in snap.data.agentStates:
            x, y = a.configuration.pos
            a.configuration = Configuration((int(x + 0.5), int(y + 0.5)), a.configuration.direction)
        act = self.inner.getAction(snap)
        return act if act in legal else legal[0]


class Paced(Agent):
    """Wraps an AI Pac-Man so a live session paces it like the keyboard agent (attract mode)."""

    def __init__(self, inner, session):
        self.inner, self.session, self.index = inner, session, 0

    def registerInitialState(self, state):
        if hasattr(self.inner, 'registerInitialState'):
            self.inner.registerInitialState(state)

    def getAction(self, state):
        self.session.wait_tick()
        return self.inner.getAction(state)


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
class FrameBuilder:
    """Builds v2 frames from a live GameState. Also owns the commander feed."""

    def __init__(self, ghost_cls, state):
        self.ghost_cls = ghost_cls
        self.feed = cmd.CommanderFeed()
        self.walls = state.data.layout.walls
        self.arcade = hasattr(state.data.agentStates[0], 'arcade')

    def coordinator(self):
        c = getattr(self.ghost_cls, '_coordinator', None)
        if c is None:
            mod = sys.modules.get(self.ghost_cls.__module__)
            c = getattr(mod, '_coordinator_instance', None)
        return c

    def header(self, state, meta):
        walls = self.walls
        h = dict(type='header', schema=SCHEMA_VERSION, width=walls.width, height=walls.height,
                 walls=[''.join('%' if walls[x][y] else ' ' for x in range(walls.width))
                        for y in range(walls.height - 1, -1, -1)],
                 numGhosts=state.getNumAgents() - 1, foodTotal=state.getNumFood(), arcade=self.arcade, **meta)
        if self.arcade:
            import arcadeRules as ar
            hs = ar.CFG.house
            h['house'] = None if hs is None else dict(
                y=hs.y, x0=hs.x0, x1=hs.x1, doorY=hs.doorY, doorXs=list(hs.doorXs), exitTile=list(hs.exitTile))
            h['level'] = ar.CFG.level
            h['framesPerRound'] = ar.CFG.frames
        return h

    def frame(self, state, tick, dt):
        d = state.data
        snap = cmd.read_coordinator(self.coordinator())
        msgs = self.feed.update(tick, snap)
        tactical = snap['tactical'] if snap else None
        macro = snap['macro'] if snap else None
        roles = snap['roles'] if snap else {}
        targets = snap['targets'] if snap else {}
        arcade = None
        if self.arcade:
            import arcadeRules as ar
            arcade = ar.snapshot(state)
            if tactical is None:
                tactical = arcade['mode'].upper()
        pac = d.agentStates[0]
        ghosts = []
        for i in range(1, len(d.agentStates)):
            s = d.agentStates[i]
            pos = s.configuration.getPosition()
            tgt = targets.get(i)
            mode = arcade['ghostModes'][i - 1] if arcade else ('frightened' if s.scaredTimer > 0 else 'active')
            ghosts.append(dict(
                index=i, pos=rec._tup(tuple(int(c + 0.5) for c in pos)),
                fpos=[round(pos[0], 4), round(pos[1], 4)], dir=str(s.configuration.direction),
                scaredTimer=int(s.scaredTimer), mode=mode,
                role=roles.get(i), target=rec._tup(tgt),
                path=rec.bfs_path(self.walls, tuple(int(c + 0.5) for c in pos), tgt) if tgt is not None else []))
        pp = pac.configuration.getPosition()
        predicted = next((rec._tup(targets[i]) for i, r in roles.items() if r == 'interceptor' and i in targets), None)
        if tactical == 'SCATTER':
            predicted = None
        f = dict(
            type='frame', schema=SCHEMA_VERSION, tick=tick, dt=dt, score=d.score,
            pacman=dict(pos=rec._tup(tuple(int(c + 0.5) for c in pp)), fpos=[round(pp[0], 4), round(pp[1], 4)],
                        dir=str(pac.configuration.direction)),
            ghosts=ghosts,
            food=sorted([x, y] for x in range(self.walls.width) for y in range(self.walls.height) if d.food[x][y]),
            capsules=[rec._tup(c) for c in d.capsules],
            tacticalState=tactical, macroStrategy=macro, predictedPacman=predicted,
            reservedTiles=[], arcade=arcade,
            commander=dict(source=snap['source'] if snap else 'none', messages=msgs))
        if snap and snap.get('telemetry') is not None:
            f['telemetry'] = rec._json_safe(snap['telemetry'])
        c = self.coordinator()
        res = getattr(c, 'reservedTiles', None) if c is not None else None
        if res:
            f['reservedTiles'] = [dict(ghost=int(g), tile=rec._tup(t)) for g, t in sorted(res.items())]
        return f


class FrameDisplay:
    """textDisplay.NullGraphics look-alike that turns every completed round into a frame."""

    def __init__(self, builder, meta, sink, max_ticks=None):
        self.builder, self.meta, self.sink = builder, meta, sink
        self.max_ticks = max_ticks
        self.game = None
        self.n = 1
        self.updates = 0
        self.tick = -1
        self.header = None
        self.truncated = False

    def initialize(self, data, isBlue=False):
        self.n = len(data.agentStates)
        self.header = self.builder.header(self.game.state, self.meta)
        self.sink.header(self.header)
        self._emit()

    def update(self, data):
        self.updates += 1
        if self.updates % self.n == 0:
            self._emit()
            if self.max_ticks is not None and self.tick >= self.max_ticks:
                self.truncated = True
                self.game.gameOver = True

    def _emit(self):
        self.tick += 1
        self.sink.frame(self.builder.frame(self.game.state, self.tick, self.sink.dt()))

    def finish(self):
        if self.updates % self.n != 0:
            self._emit()

    def checkNullDisplay(self): return True
    def pause(self): pass
    def draw(self, state): pass
    def updateDistributions(self, dist): pass


# ---------------------------------------------------------------------------
# SSE hub and live session
# ---------------------------------------------------------------------------
class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.subs = []
        self.header = None
        self.last = None
        self.status = None

    def subscribe(self):
        q = queue.Queue(maxsize=400)
        with self.lock:
            self.subs.append(q)
            for ev in (('header', self.header), ('frame', self.last), ('status', self.status)):
                if ev[1] is not None:
                    q.put(ev)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def publish(self, event, data):
        with self.lock:
            if event == 'header':
                self.header, self.last = data, None
            elif event == 'frame':
                self.last = data
            elif event == 'status':
                self.status = data
            for q in list(self.subs):
                try:
                    q.put_nowait((event, data))
                except queue.Full:
                    with contextlib.suppress(queue.Empty):
                        q.get_nowait()          # slow client: drop the oldest message
                    with contextlib.suppress(queue.Full):
                        q.put_nowait((event, data))


class Session:
    """One live game on a worker thread."""

    def __init__(self, hub, params):
        self.hub, self.params = hub, params
        self.tickRate = float(params['tickRate'])
        self.paused = False
        self.stopped = False
        self.state = 'starting'
        self.tick = 0
        self.next = None
        self.agent = None
        self.game = None
        self.result = None
        self.thread = threading.Thread(target=self._run, daemon=True, name='live-game')
        self.lock = threading.Lock()

    # sink interface used by FrameDisplay
    def header(self, h):
        self.hub.publish('header', json.dumps(h))

    def frame(self, f):
        self.tick = f['tick']
        self.hub.publish('frame', json.dumps(f, separators=(',', ':')))

    def dt(self):
        return round(1.0 / self.tickRate, 4)

    def status(self):
        s = dict(state=self.state, paused=self.paused, tickRate=self.tickRate, tick=self.tick, params=self.params)
        if self.result:
            s['result'] = self.result
        return s

    def publish_status(self):
        self.hub.publish('status', json.dumps(self.status()))

    def set_paused(self, v):
        with self.lock:
            self.paused = bool(v)
            if self.state in ('running', 'paused'):
                self.state = 'paused' if self.paused else 'running'
        self.publish_status()

    def set_rate(self, r):
        self.tickRate = min(max(float(r), 2.0), 60.0)
        self.params['tickRate'] = self.tickRate
        self.publish_status()

    def stop(self):
        self.stopped = True
        if self.game is not None:
            self.game.gameOver = True

    def wait_tick(self):
        if self.next is None:
            self.next = time.monotonic() + float(self.params.get('readyDelay', 1.2))
        while not self.stopped:
            if self.paused:
                time.sleep(0.03)
                self.next = time.monotonic() + 1.0 / self.tickRate
                continue
            now = time.monotonic()
            if now >= self.next:
                break
            time.sleep(min(self.next - now, 0.02))
        now = time.monotonic()
        self.next += 1.0 / self.tickRate
        if self.next < now - 0.5:
            self.next = now

    def _run(self):
        try:
            build = build_game(self.params, self, live=True)
            self.game, self.agent = build['game'], build['agent']
            self.state = 'running'
            self.publish_status()
            self.game.run()
            st = self.game.state
            self.result = dict(score=st.getScore(), win=bool(st.isWin()), lose=bool(st.isLose()), stopped=self.stopped)
            self.state = 'over'
            self.hub.publish('end', json.dumps(dict(type='end', ticks=self.tick, **self.result)))
        except Exception as exc:     # surface failures to the page instead of dying silently
            import traceback
            traceback.print_exc()
            self.state = 'error'
            self.result = dict(error=str(exc))
            self.hub.publish('end', json.dumps(dict(type='end', error=str(exc))))
        finally:
            self.publish_status()


def build_game(params, sink, live):
    """Create the game from validated params. Returns dict(game, agent, display)."""
    with in_game_dir():
        import layout as layout_mod
        import pacman
        import arcadeRules
        lay = layout_mod.getLayout(params['layout'])
        if lay is None:
            raise ValueError('layout not found: %s' % params['layout'])
        if params['arcade']:
            arcadeRules.install(pacman, params['level'])
        else:
            arcadeRules.uninstall()
        random.seed(params['seed'])
        ghost_cls = pacman.loadAgent(params['ghosts'], True)
        if hasattr(ghost_cls, '_coordinator'):
            ghost_cls._coordinator = None
        mod = sys.modules.get(ghost_cls.__module__)
        if mod is not None and hasattr(mod, '_coordinator_instance'):
            mod._coordinator_instance = None
        ghosts = [ghost_cls(i + 1) for i in range(lay.getNumGhosts())]
        if params['arcade'] and not params['ghosts'].startswith('Arcade'):
            ghosts = [SnapGhost(g) for g in ghosts]
        if params['pacman'] == 'browser':
            agent = BrowserKeyboardAgent(sink if live else None)
        else:
            agent = pacman.loadAgent(params['pacman'], True)()
            if live:
                agent = Paced(agent, sink)
        rules = pacman.ClassicGameRules(30)
        meta = dict(layout=params['layout'], pacmanAgent=params['pacman'], ghostTeam=params['ghosts'],
                    seed=params['seed'], game=1, maxTicks=params.get('maxTicks'), tickRate=params['tickRate'],
                    recordedAt=time.strftime('%Y-%m-%dT%H:%M:%S'), live=live)
        # first build with a placeholder display to get the initial state, then swap in the real one
        display = FrameDisplay(None, meta, sink, params.get('maxTicks'))
        game = rules.newGame(lay, agent, ghosts, display, quiet=True)
        display.builder = FrameBuilder(ghost_cls, game.state)
        display.game = game
        return dict(game=game, agent=agent, display=display)


def clean_params(raw):
    def ident(key, default):
        v = str(raw.get(key, default))
        if not IDENT_RE.match(v):
            raise ValueError('bad %s: %r' % (key, v))
        return v
    arcade = raw.get('arcade', True)
    if isinstance(arcade, str):
        arcade = arcade.lower() in ('1', 'true', 'yes', 'on')
    ghosts = ident('ghosts', 'ArcadeGhostTeam' if arcade else 'DirectionalGhost')
    if not arcade and ghosts.startswith('Arcade'):
        ghosts = 'DirectionalGhost'           # arcade ghosts need the arcade rules
    p = dict(layout=ident('layout', 'originalClassic'),
             ghosts=ghosts,
             pacman=ident('pacman', 'browser'), arcade=bool(arcade),
             level=max(1, min(int(raw.get('level', 1)), 99)),
             tickRate=min(max(float(raw.get('tickRate', 15)), 2.0), 60.0),
             seed=int(raw.get('seed', 0)))
    if 'maxTicks' in raw and raw['maxTicks'] is not None:
        p['maxTicks'] = max(1, min(int(raw['maxTicks']), 20000))
    return p


class Live:
    def __init__(self):
        self.hub = Hub()
        self.session = None
        self.lock = threading.Lock()

    def start(self, raw):
        params = clean_params(raw)
        with self.lock:
            if self.session is not None:
                self.session.stop()
                self.session.thread.join(timeout=3)
            self.session = Session(self.hub, params)
            self.session.thread.start()
            return self.session

    def key(self, raw):
        d = KEYMAP.get(str(raw.get('dir') or raw.get('key') or ''))
        s = self.session
        if d is None:
            raise ValueError('unknown key')
        if s is None or not hasattr(s.agent, 'press'):
            return False
        s.agent.press(d)
        return True


LIVE = Live()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _hosts_ok(port):
    return {'127.0.0.1:%d' % port, 'localhost:%d' % port, '[::1]:%d' % port}


class LiveHandler(base.Handler):
    server_version = 'PacLive/1'

    def _guard(self):
        """Reject DNS-rebinding and cross-site POSTs: only loopback Host / Origin."""
        port = self.server.server_address[1]
        host = self.headers.get('Host', '')
        if host not in _hosts_ok(port):
            self._err(403, 'bad host')
            return False
        origin = self.headers.get('Origin')
        if origin and re.sub(r'^https?://', '', origin) not in _hosts_ok(port):
            self._err(403, 'bad origin')
            return False
        return True

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(min(n, 65536)).decode('utf-8'))

    def do_GET(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        if u.path == '/live':
            return self._file(os.path.join(base.STATIC, 'live.html'))
        if u.path == '/live/stream':
            return self._live_stream()
        if u.path == '/api/live/state':
            s = LIVE.session
            return self._json(s.status() if s else dict(state='idle'))
        return super().do_GET()

    def do_POST(self):
        if not self._guard():
            return
        p = urlparse(self.path).path
        if not p.startswith(('/api/key', '/api/live/')):
            return super().do_POST()
        try:
            body = self._body()
        except ValueError:
            return self._err(400, 'bad json')
        try:
            if p == '/api/key':
                return self._json(dict(ok=LIVE.key(body)))
            if p == '/api/live/start':
                s = LIVE.start(body)
                return self._json(dict(ok=True, params=s.params))
            s = LIVE.session
            if s is None:
                return self._err(409, 'no session')
            if p == '/api/live/pause':
                s.set_paused(body.get('paused', not s.paused))
            elif p == '/api/live/rate':
                s.set_rate(body.get('tickRate', s.tickRate))
            elif p == '/api/live/stop':
                s.stop()
            else:
                return self._err(404, 'not found')
            return self._json(dict(ok=True, **{k: v for k, v in s.status().items() if k != 'params'}))
        except (ValueError, TypeError) as e:
            return self._err(400, str(e))

    def _live_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        q = LIVE.hub.subscribe()
        try:
            self.wfile.write(b'retry: 1000\n\n')
            while True:
                try:
                    event, data = q.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
                    continue
                self.wfile.write(('event: %s\ndata: %s\n\n' % (event, data)).encode('utf-8'))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            LIVE.hub.unsubscribe(q)


def make_live_server(host='127.0.0.1', port=8765):
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('live play is localhost only (got host %r)' % host)
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), LiveHandler)


# ---------------------------------------------------------------------------
# Headless recording (v2 traces, optionally in arcade mode)
# ---------------------------------------------------------------------------
class _ListSink:
    def __init__(self):
        self.h, self.frames, self.rate = None, [], 15.0

    def header(self, h): self.h = h
    def frame(self, f): self.frames.append(f)
    def dt(self): return round(1.0 / self.rate, 4)


def record_v2(layout='originalClassic', pacman='GreedyAgent', ghosts='ArcadeGhostTeam', arcade=True, level=1,
              seed=0, max_ticks=600, tick_rate=15.0, out_dir=rec.TRACE_DIR, write=True):
    params = clean_params(dict(layout=layout, pacman=pacman, ghosts=ghosts, arcade=arcade, level=level,
                               seed=seed, tickRate=tick_rate, maxTicks=max_ticks))
    sink = _ListSink()
    sink.rate = params['tickRate']
    b = build_game(params, sink, live=False)
    b['game'].run()
    st = b['game'].state
    footer = dict(type='end', ticks=len(sink.frames) - 1, score=st.getScore(), win=bool(st.isWin()),
                  lose=bool(st.isLose()), truncated=b['display'].truncated)
    path = None
    if write:
        os.makedirs(out_dir, exist_ok=True)
        slug = re.sub(r'[^A-Za-z0-9]+', '', params['ghosts'])
        path = os.path.join(out_dir, '%s_%s_%s%s_s%d_v2.jsonl' % (
            params['layout'], params['pacman'], slug, '_arcadeL%d' % params['level'] if params['arcade'] else '',
            params['seed']))
        with open(path, 'w', encoding='utf-8') as f:
            for r in [sink.h] + sink.frames + [footer]:
                f.write(json.dumps(r, separators=(',', ':')) + '\n')
    return path, sink.h, sink.frames, footer


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'record':
        ap = argparse.ArgumentParser(prog='live.py record')
        ap.add_argument('-l', '--layout', default='originalClassic')
        ap.add_argument('-p', '--pacman', default='GreedyAgent')
        ap.add_argument('-g', '--ghosts', default=None)
        ap.add_argument('--arcade', action='store_true')
        ap.add_argument('--level', type=int, default=1)
        ap.add_argument('--seed', type=int, default=0)
        ap.add_argument('--max-ticks', type=int, default=600)
        a = ap.parse_args(argv[1:])
        g = a.ghosts or ('ArcadeGhostTeam' if a.arcade else 'DirectionalGhost')
        path, _, frames, footer = record_v2(a.layout, a.pacman, g, a.arcade, a.level, a.seed, a.max_ticks)
        print(json.dumps(dict(path=path, frames=len(frames), score=footer['score'], win=footer['win'],
                              lose=footer['lose'])))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--autostart', action='store_true', help='start an arcade game as soon as the server is up')
    a = ap.parse_args(argv)
    srv = make_live_server(a.host, a.port)
    if a.autostart:
        LIVE.start(dict(arcade=True))
    print('Pac-Man dashboard on http://%s:%d/  (live play: /live)' % (a.host, a.port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
