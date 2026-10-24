"""Compact markdown table (mean +- 95% CI of Pac-Man score) from a bakeoff JSON.
Usage: python3 bakeoff_table.py results.json "Title"
"""
import json
import math
import sys

TEAMS = ['VoronoiGhostTeam', 'VoronoiExpectimaxGhostTeam', 'CoordinatedGhostTeam',
         'EnhancedCoordinatedGhostTeam', 'DirectionalGhost', 'MazeDistanceChaseTeam', 'RandomGhost']
SHORT = {'VoronoiGhostTeam': 'A Voronoi', 'VoronoiExpectimaxGhostTeam': 'B Vor+Expectimax',
         'CoordinatedGhostTeam': 'Coordinated', 'EnhancedCoordinatedGhostTeam': 'Enhanced',
         'DirectionalGhost': 'Directional', 'MazeDistanceChaseTeam': 'C MazeChase',
         'RandomGhost': 'Random'}


def main(fn, title):
    with open(fn, encoding='utf-8') as f:
        r = json.load(f)
    cells = []
    for x in r:
        c = (x['layout'], x['agent'])
        if c not in cells:
            cells.append(c)
    print('\n**%s**\n' % title)
    print('| Layout / Pac-Man | ' + ' | '.join(SHORT[t] for t in TEAMS) + ' |')
    print('|---|' + '---|' * len(TEAMS))
    for c in cells:
        vals = []
        for t in TEAMS:
            sc = [x['score'] for x in r if (x['layout'], x['agent'], x['team']) == (c[0], c[1], t)]
            if not sc:
                vals.append(None)
                continue
            m = sum(sc) / len(sc)
            sd = math.sqrt(sum((v - m) ** 2 for v in sc) / (len(sc) - 1))
            vals.append((m, 1.96 * sd / math.sqrt(len(sc))))
        best = min(i for i, v in enumerate(vals) if v) if False else min(
            (i for i, v in enumerate(vals) if v), key=lambda i: vals[i][0])
        row = []
        for i, v in enumerate(vals):
            s = '-' if v is None else '%d ± %d' % v
            row.append('**%s**' % s if i == best else s)
        print('| %s / %s | ' % c + ' | '.join(row) + ' |')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
