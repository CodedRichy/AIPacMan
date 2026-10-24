#!/usr/bin/env python3
"""Does ghost-to-ghost communication help under partial observability?  (Phase 10)

Conditions (same Pac-Man agent, layout and seeds in every row):
  full    EnhancedCoordinatedGhostTeam   omniscient shared coordinator, no fog
  silent  SilentFogGhostTeam             fog (6 maze tiles / straight line of sight), bus disabled
  chatter ChatterGhostTeam               fog + real message bus
  lossy   LossyChatterGhostTeam          fog + bus, half of all deliveries dropped

Run from the repo root, under the memory cap:
    tools/capped -m 4G -- python3 benchmarks/chatter_ablation.py --games 100
    tools/capped -m 4G -- python3 benchmarks/chatter_ablation.py --quick

At most 4 worker processes (--jobs is clamped), each limited to 2 GiB address space
(RLIMIT_AS) and recycled every 20 games. Game i uses seed `seed + i` in every condition,
so rows are paired. Reported: Pac-Man mean score and kill time with 95% CIs
(1.96 * sd / sqrt(n)), the paired score difference against `silent`, messages per game
and ms per ghost decision.
"""
import argparse
import datetime
import json
import math
import multiprocessing as mp
import os
import resource
import signal
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'benchmarks'))
sys.path.insert(0, os.path.join(ROOT, 'multiagent'))

CONDITIONS = [('full', 'EnhancedCoordinatedGhostTeam'), ('silent', 'SilentFogGhostTeam'),
              ('chatter', 'ChatterGhostTeam'), ('lossy', 'LossyChatterGhostTeam')]
LAYOUTS = ['mediumClassic', 'originalClassic']
PACMEN = ['GreedyAgent', 'ExpectimaxAgent:2']
GAME_TIMEOUT = 240


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout()


def _init_worker():
    lim = 2 * 1024 ** 3
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    signal.signal(signal.SIGALRM, _alarm)


def _play(spec):
    import run_benchmark as rb
    os.environ['GHOST_MSG_OFF'] = spec.get('off', '')
    sys.setrecursionlimit(5000)
    signal.alarm(GAME_TIMEOUT)
    try:
        r = rb.play_game(spec)
    except BaseException as e:           # MemoryError, Timeout, anything: report, never crash the pool
        return {'spec': spec, 'error': '%s: %s' % (type(e).__name__, e)}
    finally:
        signal.alarm(0)
    msgs = 0
    mod = sys.modules.get('chatterGhostAgents')
    if mod is not None:
        hub = getattr(getattr(mod, spec['ghost'], None), '_coordinator', None)
        if hub is not None:
            msgs = hub.bus.sent
            r['msg_counts'] = dict(hub.bus.counts)
            r['msg_lost'] = hub.bus.lostCount
    r['messages'] = msgs
    return r


def ci95(xs):
    if len(xs) < 2:
        return 0.0
    return 1.96 * statistics.stdev(xs) / math.sqrt(len(xs))


def summarize(rs):
    ok = [r for r in rs if 'score' in r and not r.get('error')]
    out = {'games': len(rs), 'failed': len(rs) - len(ok)}
    if not ok:
        return out
    sc = [r['score'] for r in ok]
    kt = [r['kill_time'] for r in ok if r['kill_time'] is not None]
    out.update(score=statistics.fmean(sc), score_ci=ci95(sc), score_sd=statistics.pstdev(sc),
               kill=statistics.fmean(kt) if kt else None, kill_ci=ci95(kt) if kt else None,
               win=sum(r['win'] for r in ok) / len(ok), capped=sum(r['capped'] for r in ok),
               msgs=statistics.fmean(r['messages'] for r in ok),
               msgs_per_move=statistics.fmean(r['messages'] / max(1, r['moves']) for r in ok),
               ms=statistics.fmean(r['ghost_ms_mean'] for r in ok),
               illegal=sum(r['illegal_actions'] for r in ok),
               distinct_scores=len(set(sc)))
    types = {}
    for r in ok:
        for k, v in r.get('msg_counts', {}).items():
            types[k] = types.get(k, 0) + v
    out['msgs_by_type_per_game'] = {k: v / len(ok) for k, v in sorted(types.items())}
    return out


def paired(a, b):
    """Mean and 95% CI of score(a) - score(b) over seeds both finished."""
    da = {r['spec']['seed']: r['score'] for r in a if 'score' in r and not r.get('error')}
    db = {r['spec']['seed']: r['score'] for r in b if 'score' in r and not r.get('error')}
    d = [da[s] - db[s] for s in da if s in db]
    return (statistics.fmean(d), ci95(d)) if d else (None, None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--games', type=int, default=100)
    ap.add_argument('--seed', type=int, default=7000)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--layouts', nargs='+', default=LAYOUTS)
    ap.add_argument('--pacman', nargs='+', default=PACMEN)
    ap.add_argument('--conditions', nargs='+', default=[c for c, _ in CONDITIONS],
                    help='full silent chatter lossy, or chatter-no<TYPE>[+<TYPE>] (diagnostic leave-out)')
    ap.add_argument('--max-moves', type=int, default=1500)
    ap.add_argument('--quick', action='store_true', help='6 games, mediumClassic, GreedyAgent')
    ap.add_argument('--out', default=os.path.join(ROOT, 'benchmarks', 'results', 'chatter_ablation.json'))
    a = ap.parse_args(argv)
    if a.quick:
        a.games, a.layouts, a.pacman = 6, ['mediumClassic'], ['GreedyAgent']
    jobs = max(1, min(4, a.jobs))
    cond = dict(CONDITIONS)
    off = {}
    for c in a.conditions:              # 'chatter-noYIELD+HANDOFF' = ChatterGhostTeam with those types suppressed
        if c.startswith('chatter-no'):
            cond[c], off[c] = 'ChatterGhostTeam', c[len('chatter-no'):].replace('+', ',')

    cells = [(p, l, c) for p in a.pacman for l in a.layouts for c in a.conditions]
    results = {}
    t0 = time.time()
    with mp.get_context('fork').Pool(jobs, initializer=_init_worker, maxtasksperchild=20) as pool:
        for (p, l, c) in cells:
            specs = [{'pacman': p, 'layout': l, 'ghost': cond[c], 'seed': a.seed + i,
                      'max_moves': a.max_moves, 'off': off.get(c, '')} for i in range(a.games)]
            rs = pool.map(_play, specs, chunksize=1)
            results[(p, l, c)] = rs
            s = summarize(rs)
            print('%-18s %-16s %-8s n=%d failed=%d score=%s  (%.0fs)' % (
                p, l, c, s['games'], s['failed'], '%.0f' % s['score'] if 'score' in s else '-',
                time.time() - t0), file=sys.stderr, flush=True)

    rows = ['| Pac-Man | Layout | Ghosts | n (failed) | Score mean +/- 95% CI | d vs silent (paired) | '
            'Kill time +/- CI | Win % | Distinct scores | Msgs/game | Msgs/move | ms/decision |',
            '|---|---|---|---|---|---|---|---|---|---|---|---|']
    out = []
    for (p, l, c) in cells:
        rs = results[(p, l, c)]
        s = summarize(rs)
        d, dci = paired(rs, results.get((p, l, 'silent'), [])) if 'silent' in a.conditions else (None, None)
        out.append({'pacman': p, 'layout': l, 'condition': c, 'ghost': cond[c], 'summary': s, 'games': rs,
                    'paired_vs_silent': [d, dci]})
        if 'score' not in s:
            rows.append('| %s | %s | %s | %d (%d) | - | - | - | - | - | - | - | - |' % (
                p, l, c, s['games'], s['failed']))
            continue
        dtxt = '-' if d is None or c == 'silent' else '%+.0f +/- %.0f' % (d, dci)
        kt = '-' if s['kill'] is None else '%.1f +/- %.1f' % (s['kill'], s['kill_ci'])
        rows.append('| %s | %s | %s | %d (%d) | %.0f +/- %.0f | %s | %s | %.0f | %d | %.0f | %.2f | %.2f |' % (
            p, l, c, s['games'], s['failed'], s['score'], s['score_ci'], dtxt, kt, 100 * s['win'],
            s['distinct_scores'], s['msgs'], s['msgs_per_move'], s['ms']))
    table = '\n'.join(rows)
    for (p, l, c) in cells:
        bt = summarize(results[(p, l, c)]).get('msgs_by_type_per_game')
        if bt:
            print('# %s / %s / %s msgs per game by type: %s' % (p, l, c, ', '.join('%s %.1f' % kv for kv in bt.items())),
                  file=sys.stderr)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': datetime.datetime.now().isoformat(), 'args': vars(a), 'python': sys.version,
                   'table_markdown': table, 'cells': out}, f, indent=1)
    print(table)
    print('JSON: %s  (total %.0fs)' % (a.out, time.time() - t0), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
