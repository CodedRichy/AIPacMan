# benchmark_phase4.py -- Phase 4 measurement only (not part of the game).
# Usage (from multiagent/): python3 benchmark_phase4.py [-n 30] [--off macro,tactical,flee,sticky]
import time, random, argparse, json
import pacman, layout, textDisplay
import pacmanAgents
import enhancedGhostAgents as E


def run(ghostCls, n=30, off=(), layoutName='mediumClassic'):
    lay = layout.getLayout(layoutName)
    E.EnhancedGhostCoordinator.DEFAULT_FEATURES = {
        k: (k not in off) for k in ('macro', 'tactical', 'flee', 'sticky')}
    scores, wins, times = [], 0, []
    rules = pacman.ClassicGameRules(30)
    rules.quiet = True
    for i in range(n):
        random.seed('p4-%d' % i)
        E.EnhancedCoordinatedGhostTeam._coordinator = None
        ghosts = [ghostCls(j + 1) for j in range(lay.getNumGhosts())]
        t = time.time()
        g = rules.newGame(lay, pacmanAgents.GreedyAgent(), ghosts,
                          textDisplay.NullGraphics(), True, False)
        g.run()
        times.append(time.time() - t)
        scores.append(g.state.getScore())
        wins += g.state.isWin()
    return sum(scores) / float(n), wins, sum(times) / n, scores


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=30)
    ap.add_argument('--off', default='')
    ap.add_argument('--set', default='')
    ap.add_argument('--team', default='EnhancedCoordinatedGhostTeam')
    a = ap.parse_args()
    import coordinatedGhostAgents as C
    cls = getattr(E, a.team, None) or getattr(C, a.team)
    for kv in [x for x in a.set.split(',') if x]:
        k, v = kv.split('=')
        setattr(E.EnhancedGhostCoordinator, k, int(v))
    off = [x for x in a.off.split(',') if x]
    avg, w, t, sc = run(cls, a.n, off)
    print(json.dumps({'team': a.team, 'off': off, 'avg': avg, 'wins': w, 'sec/game': round(t, 2)}))
