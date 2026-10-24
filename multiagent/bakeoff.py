"""Phase 7 ghost bake-off.

Run from multiagent/:
    python3 bakeoff.py --phase dev      --games 40
    python3 bakeoff.py --phase holdout  --games 40

dev     = layouts mediumClassic, smallClassic, contestClassic;
          Pac-Man agents GreedyAgent, ExpectimaxAgent(d2), AlphaBetaAgent(d2)
holdout = layout trickyClassic and Pac-Man MinimaxAgent(d2); run only at the end.
          Cells: (holdout layout x all agents) + (dev layouts x holdout agent).
"""
import argparse
import json
import math
import os
import random
import sys
import time
import multiprocessing as mp
import resource

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEAMS = [
    'VoronoiGhostTeam',
    'VoronoiExpectimaxGhostTeam',
    'VoronoiExpectimaxGreedyTeam',
    'VoronoiExpectimaxPessimisticTeam',
    'MazeDistanceChaseTeam',
    'CoordinatedGhostTeam',
    'EnhancedCoordinatedGhostTeam',
    'DirectionalGhost',
    'RandomGhost',
]
DEV_LAYOUTS = ['mediumClassic', 'smallClassic', 'contestClassic', 'openClassic', 'originalClassic']
DEV_AGENTS = ['GreedyAgent', 'ExpectimaxAgent', 'AlphaBetaAgent']
HOLD_LAYOUTS = ['trickyClassic']
HOLD_AGENTS = ['MinimaxAgent']
MAX_ROUNDS = 1000  # games still running after this many rounds are cut off (counted as not-win)


AS_LIMIT = 2 * 1024 ** 3  # per-worker address-space cap: a runaway worker dies alone


def initWorker():
    resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))


def teamClass(name):
    import voronoiGhostAgents, ghostAgents, coordinatedGhostAgents, enhancedGhostAgents
    for m in (voronoiGhostAgents, ghostAgents, coordinatedGhostAgents, enhancedGhostAgents):
        if hasattr(m, name):
            return getattr(m, name)
    raise KeyError(name)


def pacAgent(name):
    import pacmanAgents, multiAgents
    if name == 'GreedyAgent':
        return pacmanAgents.GreedyAgent()
    return getattr(multiAgents, name)(depth='2')


class NoisyPac(object):
    """Pac-Man wrapper: with prob EPS plays a uniformly random legal move.
    Needed because ExpectimaxAgent/AlphaBetaAgent/MinimaxAgent are deterministic and the
    ghost teams are deterministic too, so without noise every seed replays one game."""
    EPS = 0.1

    def __init__(self, inner, rng):
        self.inner, self.rng, self.index = inner, rng, 0

    def getAction(self, state):
        a = self.inner.getAction(state)
        if self.rng.random() < NoisyPac.EPS:
            legal = state.getLegalActions(0)
            return self.rng.choice(legal)
        return a


class TimedGhost(object):
    """Wraps a ghost agent and accumulates wall time spent in getAction."""
    clock = [0.0]

    def __init__(self, inner):
        self.inner = inner
        self.index = inner.index

    def getAction(self, state):
        t = time.perf_counter()
        a = self.inner.getAction(state)
        TimedGhost.clock[0] += time.perf_counter() - t
        return a


def playOne(task):
    team, agent, layoutName, seed = task
    import layout as layoutmod
    import pacman, textDisplay
    random.seed(1000003 * seed + 17)
    lay = layoutmod.getLayout(layoutName)
    cls = teamClass(team)
    if hasattr(cls, '_reset'):
        cls._reset()
        cls._lastKey = None
    ghosts = [TimedGhost(cls(i + 1)) for i in range(lay.getNumGhosts())]
    TimedGhost.clock[0] = 0.0

    class Rules(pacman.ClassicGameRules):
        def process(self, state, game):
            pacman.ClassicGameRules.process(self, state, game)
            if not game.gameOver and len(game.moveHistory) > MAX_ROUNDS * len(game.agents):
                game.gameOver = True
                game.cutoff = True

    rules = Rules(30)
    rules.quiet = True
    game = rules.newGame(lay, NoisyPac(pacAgent(agent), random.Random(seed * 7919 + 3)), ghosts, textDisplay.NullGraphics(), True, False)
    game.cutoff = False
    game.run()
    rounds = max(1, sum(1 for a, _ in game.moveHistory if a == 0))
    return dict(team=team, agent=agent, layout=layoutName, seed=seed,
                score=game.state.getScore(), win=bool(game.state.isWin()),
                cutoff=bool(game.cutoff), rounds=rounds,
                ms=1000.0 * TimedGhost.clock[0] / rounds,
                rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0)


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n)
    return m, 1.96 * se, var, n


def welchP(a, b):
    ma, _, va, na = stats(a)
    mb, _, vb, nb = stats(b)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 1.0
    z = (ma - mb) / se
    return math.erfc(abs(z) / math.sqrt(2))  # two-sided, normal approx (n>=40)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['dev', 'holdout'], default='dev')
    ap.add_argument('--games', type=int, default=40)
    ap.add_argument('--jobs', '--workers', dest='workers', type=int, default=4,
                    help='worker processes (default 4; never raise on a shared machine)')
    ap.add_argument('--teams', default=','.join(TEAMS))
    ap.add_argument('--layouts', default=None)
    ap.add_argument('--agents', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--seed0', type=int, default=0, help='first seed (tune on 1000+, report on 0..)')
    ap.add_argument('--merge', default=None, help='comma list of result JSONs to re-report (no games run)')
    args = ap.parse_args()
    if args.merge:
        res = []
        for fn in args.merge.split(','):
            with open(fn, encoding='utf-8') as f:
                res += json.load(f)
        teams = [t for t in TEAMS if any(r['team'] == t for r in res)]
        cells = []
        for r in res:
            if (r['layout'], r['agent']) not in cells:
                cells.append((r['layout'], r['agent']))
        report(res, teams, cells)
        return

    teams = args.teams.split(',')
    if args.phase == 'dev':
        cells = [(l, a) for l in DEV_LAYOUTS for a in DEV_AGENTS]
    else:
        cells = [(l, a) for l in HOLD_LAYOUTS for a in DEV_AGENTS + HOLD_AGENTS]
        cells += [(l, a) for l in DEV_LAYOUTS for a in HOLD_AGENTS]
    if args.layouts:
        ls = args.layouts.split(',')
        cells = [c for c in cells if c[0] in ls]
    if args.agents:
        ag = args.agents.split(',')
        cells = [c for c in cells if c[1] in ag]
    tasks = [(t, a, l, s) for (l, a) in cells for t in teams for s in range(args.seed0, args.seed0 + args.games)]
    # slowest first for load balance
    tasks.sort(key=lambda t: (t[1] == 'GreedyAgent', t[1] == 'MinimaxAgent'))
    t0 = time.time()
    with mp.Pool(min(args.workers, 4), initializer=initWorker, maxtasksperchild=200) as pool:
        res = pool.map(playOne, tasks, chunksize=1)
    print('# %d games in %.0fs' % (len(res), time.time() - t0), file=sys.stderr)
    out = args.out or ('bakeoff_%s.json' % args.phase)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(res, f)
    report(res, teams, cells)


def report(res, teams, cells):
    by = {}
    for r in res:
        by.setdefault((r['layout'], r['agent'], r['team']), []).append(r)
    print('Score = Pac-Man average score (LOWER = better ghosts); +-95% CI. '
          'ms = ghost-team ms per round. p = Welch two-sided p of that row vs the best row.\n')
    for (l, a) in cells:
        print('### %s / %s' % (l, a))
        print('| Team | Pac win | Score (mean +- 95% CI) | Rounds | Cutoffs | ms/round |')
        print('|---|---|---|---|---|---|')
        rows = []
        for t in teams:
            rs = by[(l, a, t)]
            m, ci, _, n = stats([r['score'] for r in rs])
            rows.append((m, t, ci, rs))
        rows.sort()
        best = rows[0][3]
        for m, t, ci, rs in rows:
            wins = sum(r['win'] for r in rs)
            rounds = sum(r['rounds'] for r in rs) / len(rs)
            cut = sum(r['cutoff'] for r in rs)
            ms = sum(r['ms'] for r in rs) / len(rs)
            p = welchP([r['score'] for r in best], [r['score'] for r in rs]) if rs is not best else None
            mark = '' if p is None else (' (p=%.3f vs best)' % p)
            print('| %s | %d/%d (%.0f%%) | %.0f +- %.0f%s | %.0f | %d | %.2f |' % (
                t, wins, len(rs), 100.0 * wins / len(rs), m, ci, mark, rounds, cut, ms))
        print()
    # pooled ranking across cells (mean of per-cell mean scores, mean win rate)
    print('### Pooled over all cells above (equal weight per cell)')
    print('| Team | Mean score | Mean Pac win | Mean ms/round |')
    print('|---|---|---|---|')
    pool = []
    for t in teams:
        ms_, wr, tm = [], [], []
        for (l, a) in cells:
            rs = by[(l, a, t)]
            ms_.append(sum(r['score'] for r in rs) / len(rs))
            wr.append(sum(r['win'] for r in rs) / len(rs))
            tm.append(sum(r['ms'] for r in rs) / len(rs))
        pool.append((sum(ms_) / len(ms_), t, sum(wr) / len(wr), sum(tm) / len(tm)))
    for m, t, w, tm in sorted(pool):
        print('| %s | %.0f | %.0f%% | %.2f |' % (t, m, 100 * w, tm))


if __name__ == '__main__':
    main()
