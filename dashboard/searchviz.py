#!/usr/bin/env python3
"""Search visualiser backend: runs the REAL functions in search.py on the REAL PositionSearchProblem and
records the order in which cells were expanded.  search.py and searchAgents.py are not edited.

    python3 dashboard/searchviz.py --algo astar --maze mediumMaze        # prints JSON

The root-level modules (pacman, game, util, layout) share names with the multiagent/ ones used by the live
game, so this module always works in a SUBPROCESS with the repository root as cwd.  `run_isolated()` is
the entry point the server and the tests use.

Recording: `Recorder` wraps the problem object.  Every search function calls getSuccessors(state) exactly once
per expanded node, so the call order IS the expansion order, and the successors it returned are the cells put
on the frontier at that step.  Nothing is re-implemented here.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ALGOS = {'dfs': 'depthFirstSearch', 'bfs': 'breadthFirstSearch', 'ucs': 'uniformCostSearch',
         'astar': 'aStarSearch'}
MAZES = ('tinyMaze', 'mediumMaze', 'bigMaze')
LABELS = {'dfs': 'Depth-first', 'bfs': 'Breadth-first', 'ucs': 'Uniform-cost', 'astar': 'A* (Manhattan)'}


class Recorder:
    """Transparent proxy around a search problem that logs getSuccessors calls."""

    def __init__(self, problem):
        self._p = problem
        self.expanded, self.succ = [], []

    def __getattr__(self, name):
        return getattr(self._p, name)

    def getSuccessors(self, state):
        out = self._p.getSuccessors(state)
        self.expanded.append([state[0], state[1]])
        self.succ.append([[s[0][0], s[0][1]] for s in out])
        return out


def run(algo, maze):
    """In-process run (call only from a process whose cwd/sys.path is the repo root)."""
    if algo not in ALGOS or maze not in MAZES:
        raise ValueError('unknown algo/maze')
    os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import layout as layoutmod
    import pacman
    import search
    import searchAgents
    from game import Directions

    lay = layoutmod.getLayout(maze)
    if lay is None:
        raise ValueError('layout missing: %s' % maze)
    gs = pacman.GameState()
    gs.initialize(lay, 0)
    goal = tuple(gs.getFood().asList()[0])
    problem = searchAgents.PositionSearchProblem(gs, goal=goal, warn=False, visualize=False)
    rec = Recorder(problem)
    fn = getattr(search, ALGOS[algo])
    actions = fn(rec, searchAgents.manhattanHeuristic) if algo == 'astar' else fn(rec)
    vec = {Directions.NORTH: (0, 1), Directions.SOUTH: (0, -1), Directions.EAST: (1, 0), Directions.WEST: (-1, 0)}
    pos = tuple(problem.getStartState())
    path = [list(pos)]
    for a in actions:
        pos = (pos[0] + vec[a][0], pos[1] + vec[a][1])
        path.append(list(pos))
    walls = gs.getWalls()
    return dict(
        algo=algo, label=LABELS[algo], maze=maze, width=walls.width, height=walls.height,
        walls=[''.join('%' if walls[x][y] else ' ' for x in range(walls.width)) for y in range(walls.height - 1, -1, -1)],
        start=list(problem.getStartState()), goal=list(goal), expanded=rec.expanded, succ=rec.succ,
        actions=list(actions), path=path, cost=problem.getCostOfActions(actions),
        expandedCount=len(rec.expanded),
        source='search.py:%s' % ALGOS[algo])


def run_isolated(algo, maze, timeout=60):
    p = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'searchviz.py'), '--algo', algo, '--maze', maze],
                       cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[-400:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--algo', default='bfs')
    ap.add_argument('--maze', default='tinyMaze')
    a = ap.parse_args(argv)
    print(json.dumps(run(a.algo, a.maze), separators=(',', ':')))


if __name__ == '__main__':
    main()
