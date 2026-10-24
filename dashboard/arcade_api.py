"""HTTP API for the arcade front end (dashboard/static/play.html).  Stdlib only.

    GET  /play                    the single-page arcade shell
    GET  /api/meta                layouts, ghost teams, Pac-Man agents, mazes (read from the repo at request time)
    GET  /api/facts               per-level real numbers: PENDING_TASKS.md, autograder cache, benchmarks, traces
    GET  /api/highscores          ghost-team table built from the newest benchmarks/results/*.json
    GET  /api/searchviz?algo=&maze=   expansion order + path from the real search.py (subprocess)
    GET  /api/benchmark/status    POST /api/benchmark/run {games, layout}   (max 2 worker processes)
    GET  /api/compare             POST /api/compare/run     Minimax / AlphaBeta / Expectimax stat view
                                  (max 2 worker processes, cached in dashboard/cache/compare.json)

`handle_get` / `handle_post` return True when they answered the request.  Nothing here writes outside
benchmarks/results/ and dashboard/cache/.
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GAME = os.path.join(ROOT, 'multiagent')
RESULTS = os.environ.get('PACMAN_RESULTS_DIR', os.path.join(ROOT, 'benchmarks', 'results'))
CACHE = os.environ.get('PACMAN_CACHE_DIR', os.path.join(HERE, 'cache'))
TRACES = os.path.join(HERE, 'traces')
MAX_WORKERS = 2                  # this machine has had out-of-memory kills: never more than 2 child games at once

PLAY_LAYOUTS = ['originalClassic', 'mediumClassic', 'smallClassic']
TEAM_FILES = [  # (class, module file, label, blurb)
    ('DirectionalGhost', 'ghostAgents.py', 'Berkeley: chase', 'The course default. Each ghost heads for Pac-Man on its own.'),
    ('CoordinatedGhostTeam', 'coordinatedGhostAgents.py', 'Coordinated', 'Four roles: chaser, interceptor, blocker, sweeper.'),
    ('EnhancedCoordinatedGhostTeam', 'enhancedGhostAgents.py', 'Enhanced', 'Adds a tactical state machine, scared-ghost scatter and tile reservation.'),
    ('ArcadeGhostTeam', 'arcadeGhostAgents.py', 'Arcade', 'Blinky, Pinky, Inky and Clyde with their own targeting. Needs arcade rules.'),
]
PACMAN_AGENTS = [  # (class, takes depth, blurb)
    ('GreedyAgent', False, 'Steps to the neighbour that scores best right now.'),
    ('ReflexAgent', False, 'Scores each move by food, ghosts and capsules, then picks the best.'),
    ('MinimaxAgent', True, 'Looks ahead and assumes the ghosts play perfectly against it.'),
    ('AlphaBetaAgent', True, 'Minimax that skips branches that cannot change the answer.'),
    ('ExpectimaxAgent', True, 'Looks ahead and assumes the ghosts move at random.'),
]
IDENT = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')


def _read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------------------------------------
def meta():
    layouts = sorted(os.path.splitext(n)[0] for n in os.listdir(os.path.join(GAME, 'layouts')) if n.endswith('.lay'))
    ordered = [l for l in PLAY_LAYOUTS if l in layouts] + [l for l in layouts if l.startswith('demo_')]
    teams = [dict(name=c, label=l, blurb=b, arcadeOnly=c.startswith('Arcade'))
             for c, f, l, b in TEAM_FILES if os.path.isfile(os.path.join(GAME, f))]
    # Voronoi teams are optional: listed only if the module exists on this branch.
    vor = os.path.join(GAME, 'voronoiGhostAgents.py')
    if os.path.isfile(vor):
        with open(vor, 'r', encoding='utf-8') as f:
            for cls in re.findall(r'^class (\w+(?:Team|Ghost))\b', f.read(), re.M):
                teams.append(dict(name=cls, label='Voronoi', blurb='Territory-based hunting.', arcadeOnly=False))
    return dict(layouts=ordered, allLayouts=layouts, teams=teams,
                pacmen=[dict(name=n, depth=d, blurb=b) for n, d, b in PACMAN_AGENTS],
                mazes=['tinyMaze', 'mediumMaze', 'bigMaze'], voronoi=os.path.isfile(vor))


# ---------------------------------------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------------------------------------
def pending_tasks():
    """Parse PENDING_TASKS.md into {phaseNumber: {title, state, status, done, open, partial}}."""
    out, cur = {}, None
    try:
        with open(os.path.join(ROOT, 'PENDING_TASKS.md'), 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for ln in lines:
        m = re.match(r'^##\s+Phase\s+(\d+):\s*(.*?)\s*(?:\(([^)]*)\))?\s*$', ln)
        if m:
            cur = out[int(m.group(1))] = dict(title=m.group(2), state=m.group(3) or '', status='', done=0, open=0, partial=0)
        elif cur is not None:
            if ln.startswith('> Status:'):
                cur['status'] = ln[len('> Status:'):].strip()
            elif re.match(r'^- \[x\]', ln):
                cur['done'] += 1
            elif re.match(r'^- \[ \]', ln):
                cur['open'] += 1
            elif re.match(r'^- \[~\]', ln):
                cur['partial'] += 1
    return out


def autograder_cache():
    return _read_json(os.path.join(CACHE, 'autograder.json'), {})


def refresh_autograder():
    """Run both autograders (no graphics) and cache the totals.  Takes a minute; CLI only."""
    out = {}
    for key, cwd in (('search', ROOT), ('multiagent', GAME)):
        p = subprocess.run([sys.executable, 'autograder.py', '--no-graphics'], cwd=cwd, capture_output=True,
                           text=True, encoding='utf-8', timeout=900)
        m = re.findall(r'^Total: (\d+)/(\d+)', p.stdout, re.M)
        qs = re.findall(r'^Question (q\d+): ([\d.]+)/([\d.]+)', p.stdout, re.M)
        out[key] = dict(score=int(m[-1][0]) if m else None, max=int(m[-1][1]) if m else None,
                        questions=[dict(q=q, score=float(a), max=float(b)) for q, a, b in qs],
                        ranAt=time.strftime('%Y-%m-%dT%H:%M:%S'), command='python3 autograder.py --no-graphics',
                        cwd='.' if key == 'search' else 'multiagent')
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, 'autograder.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    return out


def benchmark_files():
    """[(timestamp, path)] newest first.  Order by the timestamp written inside the file, then mtime."""
    rows = []
    for p in glob.glob(os.path.join(RESULTS, '*.json')):
        d = _read_json(p)
        if isinstance(d, dict) and 'matchups' in d:
            rows.append((str(d.get('timestamp', '')), os.path.getmtime(p), p))
    rows.sort(reverse=True)
    return [(t, p) for t, _, p in rows]


def team_code(name):
    caps = re.findall(r'[A-Z]', name)
    if len(caps) >= 3:
        return ''.join(caps[:3])
    return name[:3].upper()


def aggregate(path):
    """Per ghost team over every matchup in a benchmark file."""
    d = _read_json(path, {})
    teams = {}
    for m in d.get('matchups', []):
        s = m.get('summary', {})
        if 'avg_score' not in s:
            continue
        t = teams.setdefault(m['ghost'], dict(games=0, score=0.0, losses=0, kill=0.0, wins=0, layouts=set(), pacmen=set()))
        g = s['games'] - s['failed']
        t['games'] += g
        t['score'] += s['avg_score'] * g
        n_loss = round(s['loss_rate'] * g)
        t['losses'] += n_loss
        t['wins'] += round(s['win_rate'] * g)
        if s.get('avg_kill_time') is not None:
            t['kill'] += s['avg_kill_time'] * n_loss
        t['layouts'].add(m['layout'])
        t['pacmen'].add(m['pacman'])
    out = []
    for name, t in teams.items():
        if not t['games']:
            continue
        out.append(dict(team=name, code=team_code(name), games=t['games'], avgScore=t['score'] / t['games'],
                        killTime=(t['kill'] / t['losses']) if t['losses'] else None,
                        killRate=t['losses'] / t['games'], pacmanWins=t['wins'],
                        layouts=sorted(t['layouts']), pacmen=sorted(t['pacmen'])))
    return dict(file=os.path.relpath(path, ROOT) if path.startswith(ROOT) else path, timestamp=d.get('timestamp'),
                teams=out)


def highscores(name=None):
    files = benchmark_files()
    if not files:
        return dict(file=None, timestamp=None, byScore=[], byKill=[], files=[])
    path = files[0][1]
    if name:
        for _, p in files:
            if os.path.basename(p) == name:
                path = p
    a = aggregate(path)
    by_score = sorted(a['teams'], key=lambda t: t['avgScore'])
    by_kill = sorted([t for t in a['teams'] if t['killTime'] is not None], key=lambda t: t['killTime'])
    return dict(file=a['file'], timestamp=a['timestamp'], byScore=by_score, byKill=by_kill,
                files=[os.path.basename(p) for _, p in files])


def trace_stats():
    n, arcade, schemas, tactical = 0, 0, set(), {}
    for p in glob.glob(os.path.join(TRACES, '*.jsonl')):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                h = json.loads(f.readline())
                n += 1
                schemas.add(h.get('schema', 1))
                arcade += 1 if h.get('arcade') else 0
                if 'Enhanced' in str(h.get('ghostTeam')):
                    for ln in f:
                        if '"type":"frame"' in ln[:20]:
                            ts = json.loads(ln).get('tacticalState')
                            if ts:
                                tactical[ts] = tactical.get(ts, 0) + 1
        except (OSError, ValueError):
            continue
    return dict(traces=n, arcade=arcade, schemas=sorted(schemas), tactical=tactical)


def facts():
    pt, ag, cmp_ = pending_tasks(), autograder_cache(), _read_json(os.path.join(CACHE, 'compare.json'))
    files, hs, ts = benchmark_files(), highscores(), trace_stats()
    bench_by = {t['team']: t for t in hs['byScore']}

    def phase(n):
        p = pt.get(n)
        return None if not p else dict(title=p['title'], state=p['state'], status=p['status'], done=p['done'],
                                       open=p['open'], partial=p['partial'], source='PENDING_TASKS.md')

    def team_line(name):
        t = bench_by.get(name)
        if not t:
            return None
        return dict(label=name, value='avg Pac-Man score %.1f, caught %.0f%% of games' % (t['avgScore'], 100 * t['killRate']),
                    source=hs['file'])
    levels = {}
    for n in range(1, 8):
        levels[str(n)] = dict(phase=phase(n) if n <= 6 else None, numbers=[])
    L = levels
    if ag.get('search'):
        a = ag['search']
        L['1']['numbers'].append(dict(label='Autograder (search)', value='%s / %s' % (a['score'], a['max']),
                                      source='dashboard/cache/autograder.json, run %s' % a['ranAt']))
    if ag.get('multiagent'):
        a = ag['multiagent']
        L['2']['numbers'].append(dict(label='Autograder (multi-agent)', value='%s / %s' % (a['score'], a['max']),
                                      source='dashboard/cache/autograder.json, run %s' % a['ranAt']))
    for n, teams in (('3', ['CoordinatedGhostTeam', 'DirectionalGhost', 'RandomGhost']),
                     ('4', ['EnhancedCoordinatedGhostTeam', 'CoordinatedGhostTeam'])):
        for t in teams:
            ln = team_line(t)
            if ln:
                L[n]['numbers'].append(ln)
    if ts['tactical']:
        tot = sum(ts['tactical'].values())
        top = sorted(ts['tactical'].items(), key=lambda kv: -kv[1])[:3]
        L['4']['numbers'].append(dict(label='Tactical states in recorded Enhanced traces',
                                      value=', '.join('%s %.0f%%' % (k.replace('_', ' '), 100 * v / tot) for k, v in top),
                                      source='dashboard/traces/*.jsonl (%d frames)' % tot))
    L['5']['numbers'].append(dict(label='Recorded traces', value='%d (%d with arcade rules)' % (ts['traces'], ts['arcade']),
                                  source='dashboard/traces/'))
    L['5']['numbers'].append(dict(label='Trace schema versions', value=', '.join('v%s' % s for s in ts['schemas']),
                                  source='dashboard/schema.md'))
    L['6']['numbers'].append(dict(label='Benchmark result files', value=str(len(files)), source='benchmarks/results/'))
    if files:
        d = _read_json(files[0][1], {})
        games = sum(m['summary'].get('games', 0) for m in d.get('matchups', []))
        L['6']['numbers'].append(dict(label='Newest result', value='%s: %d matchups, %d games' % (
            os.path.basename(files[0][1]), len(d.get('matchups', [])), games), source=os.path.relpath(files[0][1], ROOT)))
    cfg = os.path.isfile(os.path.join(GAME, 'ghostConfig.py'))
    L['6']['numbers'].append(dict(label='Config module', value='multiagent/ghostConfig.py ' + ('present' if cfg else 'missing') + ' (not wired into the ghosts, see docs/CONFIG_WIRING.md)',
                                  source='multiagent/ghostConfig.py'))
    n_arc = 0
    try:
        with open(os.path.join(GAME, 'tests_arcade.py'), 'r', encoding='utf-8') as f:
            n_arc = len(re.findall(r'^\s+def test', f.read(), re.M))
    except OSError:
        pass
    L['7']['numbers'].append(dict(label='Arcade unit tests', value=str(n_arc), source='multiagent/tests_arcade.py'))
    L['7']['numbers'].append(dict(label='Arcade traces recorded', value=str(ts['arcade']), source='dashboard/traces/'))
    return dict(levels=levels, compare=cmp_, autograder=ag)


# ---------------------------------------------------------------------------------------------------------
# long-running jobs (each limited to 2 child processes)
# ---------------------------------------------------------------------------------------------------------
class Bench:
    lock = threading.Lock()
    proc = None
    out = None
    started = None
    layout = None
    games = None
    log = None

    @classmethod
    def start(cls, games, layout):
        with cls.lock:
            if cls.proc is not None and cls.proc.poll() is None:
                raise RuntimeError('a benchmark is already running')
            os.makedirs(RESULTS, exist_ok=True)
            cls.out = os.path.join(RESULTS, 'ui-%s.json' % time.strftime('%Y%m%d-%H%M%S'))
            cls.log = open(os.devnull, 'w')
            cmd = [sys.executable, os.path.join(ROOT, 'benchmarks', 'run_benchmark.py'), '--games', str(games),
                   '--pacman', 'GreedyAgent', '--layouts', layout, '--jobs', str(MAX_WORKERS), '--timeout', '60',
                   '--out', cls.out]
            cls.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cls.started, cls.layout, cls.games = time.time(), layout, games

    @classmethod
    def status(cls):
        p = cls.proc
        if p is None:
            return dict(state='idle')
        rc = p.poll()
        if rc is None:
            return dict(state='running', seconds=round(time.time() - cls.started, 1), layout=cls.layout, games=cls.games)
        return dict(state='done' if rc == 0 else 'failed', returncode=rc, file=os.path.basename(cls.out),
                    seconds=round(time.time() - cls.started, 1))


class Compare:
    lock = threading.Lock()
    running = False
    progress = (0, 0)
    AGENTS = ('MinimaxAgent', 'AlphaBetaAgent', 'ExpectimaxAgent')

    @classmethod
    def start(cls, games=8, depth=3):
        with cls.lock:
            if cls.running:
                raise RuntimeError('a comparison is already running')
            cls.running = True
        threading.Thread(target=cls._run, args=(games, depth), daemon=True, name='compare').start()

    @classmethod
    def _one(cls, spec):
        p = subprocess.run([sys.executable, os.path.join(HERE, 'compare_worker.py'), json.dumps(spec)], cwd=ROOT,
                           capture_output=True, text=True, encoding='utf-8', timeout=180)
        for ln in reversed(p.stdout.splitlines()):
            if ln.startswith('@@RESULT@@'):
                return json.loads(ln[len('@@RESULT@@'):])
        return None

    @classmethod
    def _run(cls, games, depth):
        try:
            specs = [dict(agent=a, depth=depth, layout='smallClassic', ghost='DirectionalGhost', seed=100 + i, maxMoves=200)
                     for a in cls.AGENTS for i in range(games)]
            cls.progress = (0, len(specs))
            done = [0]

            def job(s):
                try:
                    return cls._one(s)
                except subprocess.TimeoutExpired:
                    return None
                finally:
                    done[0] += 1
                    cls.progress = (done[0], len(specs))
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                res = list(ex.map(job, specs))
            rows = []
            for a in cls.AGENTS:
                rs = [r for r in res if r and r['spec']['agent'] == a]
                if not rs:
                    continue
                n = len(rs)
                rows.append(dict(agent=a, games=n, wins=sum(r['win'] for r in rs), winRate=sum(r['win'] for r in rs) / n,
                                 avgScore=sum(r['score'] for r in rs) / n,
                                 msPerMove=sum(r['ms_per_move'] for r in rs) / n,
                                 nodesPerMove=sum(r['nodes_per_move'] for r in rs) / n))
            os.makedirs(CACHE, exist_ok=True)
            with open(os.path.join(CACHE, 'compare.json'), 'w', encoding='utf-8') as f:
                json.dump(dict(rows=rows, depth=depth, layout='smallClassic', ghost='DirectionalGhost',
                               games=games, ranAt=time.strftime('%Y-%m-%dT%H:%M:%S'),
                               command='dashboard/compare_worker.py (2 processes)'), f, indent=1)
        finally:
            cls.running = False


@lru_cache(maxsize=16)
def _viz(algo, maze):
    import searchviz
    return searchviz.run_isolated(algo, maze)


# ---------------------------------------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------------------------------------
def handle_get(h, u):
    p = u.path
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if p in ('/play', '/play/'):
        h._file(os.path.join(h_static(h), 'play.html'))
    elif p == '/api/meta':
        h._json(meta())
    elif p == '/api/facts':
        h._json(facts())
    elif p == '/api/highscores':
        h._json(highscores(q.get('file')))
    elif p == '/api/searchviz':
        try:
            if q.get('algo') not in ('dfs', 'bfs', 'ucs', 'astar') or q.get('maze') not in ('tinyMaze', 'mediumMaze', 'bigMaze'):
                raise ValueError('unknown algo/maze')
            h._json(_viz(q['algo'], q['maze']))
        except ValueError as e:
            h._err(400, str(e))
        except Exception as e:
            h._err(500, str(e))
    elif p == '/api/benchmark/status':
        h._json(Bench.status())
    elif p == '/api/compare':
        h._json(dict(running=Compare.running, progress=Compare.progress,
                     result=_read_json(os.path.join(CACHE, 'compare.json'))))
    else:
        return False
    return True


def h_static(h):
    return os.path.join(HERE, 'static')


def handle_post(h, path, body):
    if path == '/api/benchmark/run':
        try:
            games = max(2, min(int(body.get('games', 10)), 40))
            layout = str(body.get('layout', 'mediumClassic'))
            if layout not in PLAY_LAYOUTS[1:]:
                raise ValueError('layout must be one of %s' % PLAY_LAYOUTS[1:])
            Bench.start(games, layout)
        except RuntimeError as e:
            h._err(409, str(e))
        except (ValueError, TypeError) as e:
            h._err(400, str(e))
        else:
            h._json(Bench.status())
        return True
    if path == '/api/compare/run':
        try:
            Compare.start(max(2, min(int(body.get('games', 8)), 16)), max(1, min(int(body.get('depth', 3)), 3)))
        except RuntimeError as e:
            h._err(409, str(e))
        except (ValueError, TypeError) as e:
            h._err(400, str(e))
        else:
            h._json(dict(running=True))
        return True
    return False


if __name__ == '__main__':
    if sys.argv[1:] == ['refresh-autograder']:
        print(json.dumps(refresh_autograder(), indent=1))
    else:
        print('usage: python3 dashboard/arcade_api.py refresh-autograder')
