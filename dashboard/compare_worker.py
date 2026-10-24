#!/usr/bin/env python3
"""One game of a game-tree Pac-Man agent, with decision time and node counts (used by the Level 2 stat view).

    python3 dashboard/compare_worker.py '{"agent":"AlphaBetaAgent","depth":2,"layout":"smallClassic","ghost":"DirectionalGhost","seed":1,"maxMoves":150}'

Runs in its own process (cwd = multiagent/) so one game's memory is returned to the OS when it ends.  "Nodes" are
calls to GameState.generateSuccessor made while the agent is choosing a move (wrapped here; multiAgents.py is
not edited).  Prints one JSON line.
"""
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, 'multiagent')


def play(spec):
    os.chdir(GAME)
    sys.path.insert(0, GAME)
    import layout as layoutmod
    import pacman
    import textDisplay

    counter = [0]
    orig = pacman.GameState.generateSuccessor

    def counted(self, i, a):
        counter[0] += 1
        return orig(self, i, a)
    pacman.GameState.generateSuccessor = counted

    random.seed(spec['seed'])
    lay = layoutmod.getLayout(spec['layout'])
    cls = pacman.loadAgent(spec['agent'], True)
    agent = cls(depth=str(spec['depth']))
    ghost_cls = pacman.loadAgent(spec['ghost'], True)
    ghosts = [ghost_cls(i + 1) for i in range(lay.getNumGhosts())]
    stats = dict(n=0, ms=0.0, nodes=0)
    inner = agent.getAction

    class Cap(Exception):
        pass

    def timed(state):
        if stats['n'] >= spec['maxMoves']:
            raise Cap()
        n0, t0 = counter[0], time.perf_counter()
        a = inner(state)
        stats['ms'] += 1000 * (time.perf_counter() - t0)
        stats['nodes'] += counter[0] - n0
        stats['n'] += 1
        return a
    agent.getAction = timed
    game = pacman.ClassicGameRules(30).newGame(lay, agent, ghosts, textDisplay.NullGraphics(), True, False)
    capped = False
    try:
        game.run()
    except Cap:
        capped = True
    st = game.state
    n = max(stats['n'], 1)
    return dict(spec=spec, win=bool(st.isWin()), lose=bool(st.isLose()), capped=capped, score=st.getScore(),
                moves=stats['n'], ms_per_move=stats['ms'] / n, nodes_per_move=stats['nodes'] / n)


if __name__ == '__main__':
    print('@@RESULT@@' + json.dumps(play(json.loads(sys.argv[1]))))
