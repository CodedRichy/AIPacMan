// The project map: one "level" per phase.  Prose and diagram specs only; every number shown on a level page
// comes from /api/facts at runtime (PENDING_TASKS.md, dashboard/cache/autograder.json, benchmarks/results/*.json,
// dashboard/traces).  Nothing here states a result.

export const LEVELS = [
  {
    n: 1, code: 'SEARCH', title: 'Search', phase: 1, source: 'search.py', also: 'searchAgents.py',
    blurb: 'Find a path through the maze.',
    explain: [
      'Pac-Man has to get from here to there through a maze, and he cannot see the whole route at once.',
      'Search is a careful way of trying: keep a list of cells you could visit next, pick one, look at its neighbours, repeat.',
      'The four algorithms below differ in only one thing, which cell they pick next. Depth-first dives down one corridor, breadth-first spreads out evenly, uniform-cost always takes the cheapest so far, and A* adds a smart guess about how far the goal still is.',
      'Run them yourself and count how many cells each one has to look at.',
    ],
    flow: { nodes: [['FRONTIER', 'cells waiting to be visited'], ['PICK ONE', 'the rule is what differs'], ['EXPAND', 'add its neighbours']], loop: 'repeat until the goal is picked' },
    rows: [['DFS', 'last in, first out (a stack)'], ['BFS', 'first in, first out (a queue)'], ['UCS', 'lowest path cost so far'], ['A*', 'cost so far + Manhattan guess to the goal']],
    try: { label: 'RUN A* ON MEDIUMMAZE', go: '#/levels/1?try=1' },
  },
  {
    n: 2, code: 'MULTI-AGENT', title: 'Multi-agent', phase: 2, source: 'multiagent/multiAgents.py',
    blurb: 'Plan ahead against the ghosts.',
    explain: [
      'Now there are ghosts, and they move too, so the best move for Pac-Man depends on what they do next.',
      'Minimax imagines the worst case: Pac-Man picks his best move, then the ghosts pick the move that hurts him most, a few steps deep.',
      'Alpha-beta gives the same answer but skips branches that cannot change it, so it does less work. Expectimax assumes the ghosts move at random instead, which suits a random ghost better.',
      'The table below was measured by actually playing games, not copied from a book.',
    ],
    flow: { nodes: [['PAC-MAN', 'tries each move (max)'], ['GHOSTS', 'reply (min or chance)'], ['SCORE', 'rate the board'], ['BACK UP', 'best move wins']], loop: 'look deeper, repeat' },
    rows: [['Minimax', 'ghosts play their worst-for-Pac-Man move'], ['Alpha-beta', 'same answer, prunes branches it can ignore'], ['Expectimax', 'ghosts move at random, so it averages']],
    try: { label: 'WATCH ALPHA-BETA PLAY', go: '#/run?kind=watch&layout=smallClassic&pacman=AlphaBetaAgent&depth=2&ghosts=DirectionalGhost&arcade=0&preset=classic' },
    compare: true,
  },
  {
    n: 3, code: 'GHOST TEAMWORK', title: 'Ghost coordination', phase: 3, source: 'multiagent/coordinatedGhostAgents.py',
    blurb: 'Four ghosts, four jobs.',
    explain: [
      'The default ghosts each chase Pac-Man on their own, so they tend to bunch up in a line behind him.',
      'Our coordinated team shares one brain. It ranks the ghosts by how close they are to Pac-Man and hands out jobs: the closest chases, the next one cuts him off, the third blocks an exit, and the last sweeps the food he is heading for.',
      'Each ghost then plans its own route to its target. Switch on the COACH layers to see the jobs and targets drawn on the maze.',
    ],
    flow: { nodes: [['COORDINATOR', 'reads the whole board'], ['RANK', 'ghosts by distance to Pac-Man'], ['ASSIGN', 'chaser, interceptor, blocker, sweeper'], ['PLAN', 'each ghost walks to its target']], loop: 'every tick' },
    rows: [['Chaser', 'goes straight to Pac-Man'], ['Interceptor', 'goes to where he will be'], ['Blocker', 'sits in a choke point'], ['Sweeper', 'takes the food he is heading for']],
    try: { label: 'WATCH THE TEAM HUNT', go: '#/run?kind=watch&layout=mediumClassic&pacman=GreedyAgent&ghosts=CoordinatedGhostTeam&arcade=0&preset=coach' },
  },
  {
    n: 4, code: 'TACTICS', title: 'Tactical state machine', phase: 4, source: 'multiagent/enhancedGhostAgents.py',
    blurb: 'Switch plans when the situation changes.',
    explain: [
      'A good team changes plan. When Pac-Man eats a power pellet the ghosts become prey, so this team scatters to the corners instead of charging in.',
      'The enhanced team keeps a small state machine: hunt together, scatter when scared, guard the last power pellet, or trap Pac-Man in a corridor.',
      'It also changes strategy as the food runs out, and it tries to reserve the tile it steps onto so two ghosts do not collide.',
      'The numbers here are honest: they come from real games, and PENDING_TASKS.md says which parts have not been shown to help.',
    ],
    flow: { nodes: [['PERCEIVE', 'where is Pac-Man, who is scared'], ['STATE', 'hunt, scatter, defend, trap'], ['STRATEGY', 'early, mid, endgame'], ['RETARGET', 'roles follow the plan']], loop: 'every tick' },
    rows: [['SCATTER', 'Pac-Man is powered: ghosts run to corners'], ['DEFEND CAPSULE', 'one ghost guards the last pellet'], ['TRAP AMBUSH', 'Pac-Man is in a corridor'], ['COORDINATED HUNT', 'the default: hunt as a team']],
    try: { label: 'WATCH IT ON CAPSULE CORNER', go: '#/run?kind=watch&layout=demo_capsule_corner&pacman=GreedyAgent&ghosts=EnhancedCoordinatedGhostTeam&arcade=0&preset=teacher' },
  },
  {
    n: 5, code: 'DASHBOARD', title: 'Dashboard and replay', phase: 5, source: 'dashboard/record.py', also: 'dashboard/server.py',
    blurb: 'Record a game, then watch the reasons.',
    explain: [
      'A game moves too fast to follow, so we record it. A recorder plays a game and writes one line of JSON per round: where everyone was, and what the ghost coordinator had decided.',
      'A small web server streams those lines to this page, and a canvas draws them back with the decisions laid over the maze.',
      'Because the recording is just a file, you can pause, step and replay the same game as often as you like.',
    ],
    flow: { nodes: [['GAME', 'runs headless'], ['RECORDER', 'one JSON line per round'], ['SERVER', 'streams over SSE'], ['BROWSER', 'canvas draws the frames']], loop: null },
    rows: [['Trace', 'a .jsonl file: header, frames, footer'], ['Frame', 'positions, food, roles, targets, tactical state'], ['Layers', 'toggles that decide what the canvas draws']],
    try: { label: 'OPEN A RECORDED GAME', go: '#/replays/auto' },
  },
  {
    n: 6, code: 'BENCHMARKS', title: 'Benchmarks and config', phase: 6, source: 'benchmarks/run_benchmark.py', also: 'multiagent/ghostConfig.py',
    blurb: 'Measure instead of guess.',
    explain: [
      'It is easy to believe a clever idea works. The benchmark checks: it plays many games with each ghost team against the same Pac-Man on the same maze and the same random seeds.',
      'A better hunter lowers Pac-Man\'s average score and catches him sooner, so the High Scores table ranks the ghosts that way.',
      'Each game runs in its own process so one game cannot leak state into the next. The settings module for tuning the ghosts exists but is not wired in yet.',
    ],
    flow: { nodes: [['SPEC', 'pacman, maze, ghosts, seed'], ['GAME', 'one subprocess each'], ['SUMMARY', 'win rate, score, kill time'], ['JSON', 'saved in benchmarks/results']], loop: null },
    rows: [['Avg score', 'lower means stronger ghosts'], ['Kill time', 'moves until Pac-Man is caught'], ['Seeds', 'same seeds for every team']],
    try: { label: 'OPEN THE HIGH SCORES', go: '#/scores' },
  },
  {
    n: 7, code: 'BONUS: ARCADE', title: 'Arcade mode and Commander', phase: null, source: 'multiagent/arcadeRules.py', also: 'dashboard/commander.py',
    blurb: 'The real game\'s rules, plus a boss.',
    explain: [
      'Arcade mode swaps the Berkeley rules for the real game\'s: smooth movement at the arcade speed table, ghosts that scatter and chase on a timer, Blinky, Pinky, Inky and Clyde each with their own way of aiming, and a ghost house.',
      'The Commander is a crowned ghost that stands in the middle of the maze. It never plays. It prints what the ghost coordinator decides, as short orders, so you can read the team\'s thinking.',
      'Everything on this screen that looks like the arcade is the same game engine you just read about.',
    ],
    flow: { nodes: [['ROUND', '4 arcade frames'], ['SPEED TABLE', 'pixels per frame by level'], ['TARGET TILE', 'each ghost\'s own rule'], ['COMMANDER', 'prints the team\'s orders']], loop: 'every round' },
    rows: [['Blinky', 'aims at Pac-Man'], ['Pinky', 'aims 4 tiles ahead'], ['Inky', 'aims using Blinky and a point ahead'], ['Clyde', 'chases, then retreats when close']],
    try: { label: 'WATCH ARCADE GHOSTS', go: '#/run?kind=watch&layout=originalClassic&pacman=GreedyAgent&ghosts=ArcadeGhostTeam&arcade=1&preset=coach' },
  },
];

/** Inline SVG: a vertical flow (reads well in a narrow column) with an optional loop-back arrow. Text is escaped here. */
export function flowSvg(flow) {
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const n = flow.nodes.length, bh = 50, gap = 24, W = 340, H = n * bh + (n - 1) * gap + (flow.loop ? 34 : 8) + 8;
  let s = `<svg class="flow" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(flow.nodes.map((x) => x[0]).join(' then '))}" preserveAspectRatio="xMidYMin meet">`;
  flow.nodes.forEach(([t, sub], i) => {
    const y = 4 + i * (bh + gap);
    s += `<rect x="4" y="${y}" width="300" height="${bh}" class="fb"/><text x="154" y="${y + 21}" class="ft">${esc(t)}</text><text x="154" y="${y + 38}" class="fs">${esc(sub)}</text>`;
    if (i < n - 1) s += `<path d="M154 ${y + bh + 3} V${y + bh + gap - 4}" class="fa"/><path d="M148 ${y + bh + gap - 11} l6 8 l6 -8" class="fa"/>`;
  });
  if (flow.loop) {
    const y0 = 4 + bh / 2, y1 = 4 + (n - 1) * (bh + gap) + bh / 2;
    s += `<path d="M304 ${y1} H326 V${y0} H310" class="fa dash"/><path d="M316 ${y0 - 6} l-8 6 l8 6" class="fa"/><text x="170" y="${H - 8}" class="fs mid">${esc(flow.loop)}</text>`;
  }
  return s + '</svg>';
}
