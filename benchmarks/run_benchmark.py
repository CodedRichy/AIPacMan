#!/usr/bin/env python3
"""Headless ghost-team benchmark for the AI Pac-Man project (stdlib only).

Usage (from the repo root):
    python3 benchmarks/run_benchmark.py                       # default matrix
    python3 benchmarks/run_benchmark.py --games 20 --pacman GreedyAgent \
        --layouts mediumClassic --ghosts CoordinatedGhostTeam RandomGhost
    python3 benchmarks/run_benchmark.py --quick               # tiny smoke run

Every game runs in its own subprocess (cwd = multiagent/), because the ghost
teams keep module-level singleton coordinators that would leak state between
games. Subprocesses also give us a hard per-game timeout.

`play_game(spec)` is importable for in-process use (tests, profiling); it
resets the singleton coordinators before every game.
"""
import argparse
import datetime
import json
import os
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MULTIAGENT = os.path.join(ROOT, 'multiagent')
RESULTS_DIR = os.path.join(ROOT, 'benchmarks', 'results')

DEFAULT_GHOSTS = ['CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam',
                  'DirectionalGhost', 'RandomGhost']
DEFAULT_PACMEN = ['GreedyAgent', 'ExpectimaxAgent:2', 'AlphaBetaAgent:2']
DEFAULT_LAYOUTS = ['mediumClassic', 'smallClassic', 'originalClassic',
                   'demo_corridor_trap', 'demo_pincer_arena',
                   'demo_capsule_corner', 'demo_open_field', 'demo_long_loop',
                   'demo_dead_end_comb']

# Depth-2 expectimax/alpha-beta against 4 ghosts on a fully open grid has ~4^9
# leaves per move (minutes per game), so search agents skip these layouts.
SEARCH_SKIP_LAYOUTS = {'demo_open_field'}


class MoveCap(Exception):
    """Raised inside the game loop when Pac-Man exceeds the move cap."""


def reset_singletons():
    """Ghost teams cache a coordinator at module/class level; clear it."""
    mod = sys.modules.get('coordinatedGhostAgents')
    if mod is not None:
        mod._coordinator_instance = None
    mod = sys.modules.get('enhancedGhostAgents')
    if mod is not None:
        mod.EnhancedCoordinatedGhostTeam._coordinator = None


class Probe:
    """Collects per-game observations through thin agent wrappers."""

    def __init__(self, max_moves, check_legal=True):
        self.max_moves = max_moves
        self.check_legal = check_legal
        self.pac_moves = 0
        self.ghost_times = []        # seconds per ghost decision
        self.illegal = []            # (pac_move, ghostIndex, action)
        self.frozen_ticks = 0        # longest run of an unchanged ghost config while Pac-Man moved
        self._last_cfg = None
        self._pac_seen = set()
        self._run = 0


def _wrap_pacman(agent, probe):
    orig = agent.getAction

    def getAction(state):
        probe.pac_moves += 1
        if probe.pac_moves > probe.max_moves:
            raise MoveCap()
        pac = state.getPacmanPosition()
        cfg = tuple(state.getGhostPositions())
        scared = any(g.scaredTimer > 0 for g in state.getGhostStates())
        if cfg == probe._last_cfg and not scared:
            probe._pac_seen.add(pac)
            if len(probe._pac_seen) > 1:
                probe._run += 1
        else:
            probe._run = 0
            probe._pac_seen = {pac}
        probe.frozen_ticks = max(probe.frozen_ticks, probe._run)
        probe._last_cfg = cfg
        return orig(state)
    agent.getAction = getAction
    return agent


def _wrap_ghost(agent, probe):
    orig = agent.getAction

    def getAction(state):
        t = time.perf_counter()
        action = orig(state)
        probe.ghost_times.append(time.perf_counter() - t)
        if probe.check_legal and action not in state.getLegalActions(agent.index):
            probe.illegal.append((probe.pac_moves, agent.index, action))
        return action
    agent.getAction = getAction
    return agent


def play_game(spec):
    """Play one headless game in-process (chdirs to multiagent/).

    spec keys: layout, pacman ('Name' or 'Name:depth'), ghost, seed,
               max_moves (default 1500), num_ghosts (default 4).
    Returns a plain dict of metrics. Exceptions inside the game are reported
    in the 'error' field rather than raised.
    """
    os.chdir(MULTIAGENT)
    if MULTIAGENT not in sys.path:
        sys.path.insert(0, MULTIAGENT)
    import layout as layoutmod
    import pacman as pacmanmod
    import textDisplay

    random.seed(spec['seed'])
    reset_singletons()
    lay = layoutmod.getLayout(spec['layout'])
    if lay is None:
        raise ValueError('layout not found: %s' % spec['layout'])

    pname, _, depth = spec['pacman'].partition(':')
    pac_cls = pacmanmod.loadAgent(pname, True)
    pac = pac_cls(depth=depth) if depth else pac_cls()
    ghost_cls = pacmanmod.loadAgent(spec['ghost'], True)
    probe = Probe(spec.get('max_moves', 1500), spec.get('check_legal', True))
    ghosts = [_wrap_ghost(ghost_cls(i + 1), probe) for i in range(spec.get('num_ghosts', 4))]
    _wrap_pacman(pac, probe)

    rules = pacmanmod.ClassicGameRules(30)
    game = rules.newGame(lay, pac, ghosts, textDisplay.NullGraphics(), True, False)
    capped = False
    error = None
    t0 = time.perf_counter()
    try:
        game.run()
    except MoveCap:
        capped = True
    except Exception as e:  # report, don't hide
        error = '%s: %s' % (type(e).__name__, e)
    wall = time.perf_counter() - t0
    st = game.state
    win = bool(st.isWin())
    lose = bool(st.isLose())
    return {
        'spec': spec, 'win': win, 'lose': lose, 'capped': capped, 'error': error,
        'score': st.getScore(), 'moves': probe.pac_moves,
        'kill_time': probe.pac_moves if lose else None,
        'ghost_decisions': len(probe.ghost_times),
        'ghost_ms_mean': (1000 * statistics.fmean(probe.ghost_times)) if probe.ghost_times else 0.0,
        'ghost_ms_max': (1000 * max(probe.ghost_times)) if probe.ghost_times else 0.0,
        'illegal_actions': len(probe.illegal),
        'max_frozen_ticks': probe.frozen_ticks,
        'wall_s': wall,
    }


def _run_subprocess(spec, timeout):
    cmd = [sys.executable, os.path.abspath(__file__), '--worker', json.dumps(spec)]
    try:
        p = subprocess.run(cmd, cwd=MULTIAGENT, capture_output=True, text=True,
                           encoding='utf-8', timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'spec': spec, 'timeout': True, 'error': 'timeout after %ss' % timeout}
    for line in reversed(p.stdout.splitlines()):
        if line.startswith('@@RESULT@@'):
            return json.loads(line[len('@@RESULT@@'):])
    return {'spec': spec, 'error': 'worker failed rc=%s: %s' % (p.returncode, p.stderr.strip()[-400:])}


def summarize(results):
    ok = [r for r in results if 'score' in r and not r.get('error')]
    bad = len(results) - len(ok)
    if not ok:
        return {'games': len(results), 'failed': bad}
    losses = [r['kill_time'] for r in ok if r['kill_time'] is not None]
    return {
        'games': len(results), 'failed': bad,
        'win_rate': sum(r['win'] for r in ok) / len(ok),
        'loss_rate': sum(r['lose'] for r in ok) / len(ok),
        'capped': sum(r['capped'] for r in ok),
        'avg_score': statistics.fmean(r['score'] for r in ok),
        'score_sd': statistics.pstdev([r['score'] for r in ok]),
        'avg_moves': statistics.fmean(r['moves'] for r in ok),
        'avg_kill_time': statistics.fmean(losses) if losses else None,
        'ghost_ms': statistics.fmean(r['ghost_ms_mean'] for r in ok),
        'ghost_ms_max': max(r['ghost_ms_max'] for r in ok),
        'illegal': sum(r['illegal_actions'] for r in ok),
        'max_frozen_ticks': max(r['max_frozen_ticks'] for r in ok),
    }


def markdown_table(matchups):
    hdr = ('| Pac-Man | Layout | Ghosts | Games (failed) | Win % | Loss % | Capped | Avg score (sd) | '
           'Avg moves | Avg kill time | ms/ghost decision |\n'
           '|---|---|---|---|---|---|---|---|---|---|---|\n')
    rows = []
    for m in matchups:
        s = m['summary']
        if 'avg_score' not in s:
            rows.append('| %s | %s | %s | %d (%d) | - | - | - | - | - | - | - |' % (
                m['pacman'], m['layout'], m['ghost'], s['games'], s['failed']))
            continue
        kt = '-' if s['avg_kill_time'] is None else '%.0f' % s['avg_kill_time']
        rows.append('| %s | %s | %s | %d (%d) | %.0f | %.0f | %d | %.1f (%.0f) | %.0f | %s | %.2f |' % (
            m['pacman'], m['layout'], m['ghost'], s['games'], s['failed'],
            100 * s['win_rate'], 100 * s['loss_rate'], s['capped'], s['avg_score'],
            s['score_sd'], s['avg_moves'], kt, s['ghost_ms']))
    return hdr + '\n'.join(rows) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--worker', help=argparse.SUPPRESS)
    ap.add_argument('--games', type=int, default=10)
    ap.add_argument('--seed', type=int, default=1000, help='base seed; game i uses seed+i')
    ap.add_argument('--pacman', nargs='+', default=DEFAULT_PACMEN, help='Name or Name:depth')
    ap.add_argument('--layouts', nargs='+', default=DEFAULT_LAYOUTS)
    ap.add_argument('--ghosts', nargs='+', default=DEFAULT_GHOSTS)
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--timeout', type=int, default=300, help='per-game wall-clock timeout (s)')
    ap.add_argument('--max-moves', type=int, default=1500, help='Pac-Man move cap per game')
    ap.add_argument('--quick', action='store_true', help='2 games, GreedyAgent, mediumClassic only')
    ap.add_argument('--out', default=None, help='JSON path (default benchmarks/results/<ts>.json)')
    a = ap.parse_args(argv)

    if a.worker:
        res = play_game(json.loads(a.worker))
        print('@@RESULT@@' + json.dumps(res))
        return 0

    if a.quick:
        a.games, a.pacman, a.layouts = 2, ['GreedyAgent'], ['mediumClassic']

    specs = []
    for pac in a.pacman:
        for lay in a.layouts:
            if pac != 'GreedyAgent' and lay in SEARCH_SKIP_LAYOUTS:
                continue
            for gh in a.ghosts:
                for i in range(a.games):
                    specs.append({'pacman': pac, 'layout': lay, 'ghost': gh,
                                  'seed': a.seed + i, 'max_moves': a.max_moves})
    print('Running %d games on %d workers...' % (len(specs), a.jobs), file=sys.stderr)
    t0 = time.time()
    done = [0]

    def job(spec):
        r = _run_subprocess(spec, a.timeout)
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(specs):
            print('  %d/%d done (%.0fs)' % (done[0], len(specs), time.time() - t0), file=sys.stderr)
        return r

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        results = list(ex.map(job, specs))

    matchups = []
    for pac in a.pacman:
        for lay in a.layouts:
            if pac != 'GreedyAgent' and lay in SEARCH_SKIP_LAYOUTS:
                continue
            for gh in a.ghosts:
                rs = [r for r in results if r['spec']['pacman'] == pac
                      and r['spec']['layout'] == lay and r['spec']['ghost'] == gh]
                matchups.append({'pacman': pac, 'layout': lay, 'ghost': gh,
                                 'summary': summarize(rs), 'games': rs})
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    out = a.out or os.path.join(RESULTS_DIR, ts + '.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': ts, 'args': vars(a), 'python': sys.version,
                   'matchups': matchups}, f, indent=1)
    print(markdown_table(matchups))
    print('JSON: %s  (total %.0fs)' % (out, time.time() - t0), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
