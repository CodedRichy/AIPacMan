# benchmark_ghosts.py -- measure ghost teams against a Pac-Man agent.
# Usage (from multiagent/):
#   python3 benchmark_ghosts.py -g EnhancedCoordinatedGhostTeam -p GreedyAgent -l mediumClassic -n 50
import sys
import time
import pacman
import os
DEBUG = bool(os.environ.get('GDEBUG'))


def main(argv):
    args = pacman.readCommand(argv + ['-q', '-f'])
    ghosts = args['ghosts']
    times = []
    stats = {'capTick': [], 'ghostEats': 0, 'deathTick': [], 'cur': None}

    def wrap(g):
        orig = g.getAction

        def timed(state):
            t = time.perf_counter()
            if g.index == 1:
                cur = stats['cur']
                if cur is not None and (state.getNumFood() > cur['food'] or state.getScore() < cur['score'] - 400):
                    stats.setdefault('done', []).append(cur)
                if cur is None or state.getNumFood() > cur['food'] or state.getScore() < cur['score'] - 400:
                    cur = stats['cur'] = {'t': 0, 'food': state.getNumFood(), 'score': state.getScore(),
                                          'caps': len(state.getCapsules()), 'capT': None}
                cur['t'] += 1
                if state.getScore() - cur['score'] >= 190:
                    stats['ghostEats'] += 1
                    if DEBUG:
                        print('EAT t=%d prev=%s now=%s' % (cur['t'], stats.get('hist', [])[-4:], [(gs.scaredTimer, gs.getPosition()) for gs in state.getGhostStates()]), 'pac', state.getPacmanPosition())
                cur['score'] = state.getScore()
                stats.setdefault('hist', []).append((state.getPacmanPosition(), [(gs.scaredTimer, gs.getPosition()) for gs in state.getGhostStates()]))
                cur['food'] = state.getNumFood()
                if len(state.getCapsules()) < cur['caps'] and cur['capT'] is None:
                    cur['capT'] = cur['t']
                    stats['capTick'].append(cur['t'])
                cur['caps'] = len(state.getCapsules())
            a = orig(state)
            times.append(time.perf_counter() - t)
            if a not in state.getLegalActions(g.index):
                raise Exception('illegal ghost action %s' % a)
            return a
        g.getAction = timed
    for g in ghosts:
        wrap(g)
    games = pacman.runGames(**args)
    scores = [g.state.getScore() for g in games]
    wins = [g.state.isWin() for g in games]
    initCaps = args['layout'].capsules
    capGames = sum(1 for g in games if len(g.state.getCapsules()) < len(initCaps))
    lens = [len(g.moveHistory) / (len(ghosts) + 1) for g in games]
    stats.setdefault('done', []).append(stats['cur'])
    nc = [c['t'] for c in stats['done'] if c['capT'] is None]
    wc = [c['t'] for c in stats['done'] if c['capT'] is not None]
    print('noCapsuleGames n=%d avgLen=%.1f | capsuleGames n=%d avgLen=%.1f' % (len(nc), sum(nc) / max(1, len(nc)), len(wc), sum(wc) / max(1, len(wc))))
    ct = stats['capTick']
    print('capsuleEatenAtTick avg=%.1f n=%d ghostEats=%d' % (sum(ct) / max(1, len(ct)), len(ct), stats['ghostEats']))
    print('RESULT avg=%.1f wins=%d/%d avgLen=%.1f msPerDecision=%.3f capsuleGames=%d' % (
        sum(scores) / len(scores), sum(wins), len(wins), sum(lens) / len(lens),
        1000 * sum(times) / max(1, len(times)), capGames))


if __name__ == '__main__':
    main(sys.argv[1:])
