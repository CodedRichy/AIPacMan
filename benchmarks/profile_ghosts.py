#!/usr/bin/env python3
"""cProfile one game per ghost team and print the hottest functions.

    python3 benchmarks/profile_ghosts.py [--layout mediumClassic] [--seed 1] [--top 12] [--games 1]
"""
import argparse
import cProfile
import io
import os
import pstats
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmarks import run_benchmark as rb  # noqa: E402

TEAMS = ['CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam', 'DirectionalGhost', 'RandomGhost']


def short(func):
    fn, line, name = func
    return '%s:%d(%s)' % (os.path.basename(fn), line, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--layout', default='mediumClassic')
    ap.add_argument('--pacman', default='GreedyAgent')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--games', type=int, default=1, help='games per team inside one profile')
    ap.add_argument('--top', type=int, default=12)
    ap.add_argument('--teams', nargs='+', default=TEAMS)
    a = ap.parse_args()

    for team in a.teams:
        pr = cProfile.Profile()
        results = []
        pr.enable()
        for i in range(a.games):
            results.append(rb.play_game({'pacman': a.pacman, 'layout': a.layout, 'ghost': team,
                                         'seed': a.seed + i, 'max_moves': 600,
                                         'check_legal': False}))
        pr.disable()
        st = pstats.Stats(pr, stream=io.StringIO())
        st.sort_stats('tottime')
        total = st.total_tt
        moves = sum(r['moves'] for r in results)
        ghost_ms = sum(r['ghost_ms_mean'] for r in results) / len(results)
        print('\n### %s  (%s vs %s, seed %d, %d game(s), %d Pac-Man moves)'
              % (team, a.pacman, a.layout, a.seed, a.games, moves))
        print('total profiled time %.3fs; mean ghost decision %.3f ms (incl. profiler overhead)'
              % (total, ghost_ms))
        print('')
        print('| tottime s | % | calls | function |')
        print('|---|---|---|---|')
        rows = sorted(st.stats.items(), key=lambda kv: kv[1][2], reverse=True)[:a.top]
        for func, (cc, nc, tt, ct, _callers) in rows:
            print('| %.4f | %.1f | %d | `%s` |' % (tt, 100 * tt / total if total else 0, nc, short(func)))
        ghost_rows = [(f, v) for f, v in st.stats.items()
                      if os.path.basename(f[0]) in ('coordinatedGhostAgents.py',
                                                    'enhancedGhostAgents.py', 'ghostAgents.py')]
        ghost_rows.sort(key=lambda kv: kv[1][3], reverse=True)
        if ghost_rows:
            print('\nGhost-code functions by cumulative time:\n')
            print('| cumtime s | calls | function |')
            print('|---|---|---|')
            for func, (cc, nc, tt, ct, _c) in ghost_rows[:6]:
                print('| %.4f | %d | `%s` |' % (ct, nc, short(func)))


if __name__ == '__main__':
    main()
