"""Phase 9 tests: arcade front-end routes, search visualiser, campaign rules, layers logic, static hygiene.
Plain asserts:   python3 dashboard/tests/test_arcade.py        (node is optional: the layers test is skipped without it)
"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(HERE)
ROOT = os.path.dirname(DASH)
sys.path.insert(0, DASH)

import arcade_api  # noqa: E402
import live  # noqa: E402
import session  # noqa: E402

STATIC = os.path.join(DASH, 'static')


def _req(port, method, path, body=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'})
    r = c.getresponse()
    return r.status, r.read()


def _server():
    srv = live.make_live_server('127.0.0.1', 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# ---------------------------------------------------------------------------------------------- routes
def test_routes_serve_and_validate():
    srv, port = _server()
    try:
        st, body = _req(port, 'GET', '/play')
        assert st == 200 and b'play/app.js' in body
        for p in ('/', '/live.html', '/play/app.js', '/play/layers.js', '/arcade.css'):
            assert _req(port, 'GET', p)[0] == 200, p
        meta = json.loads(_req(port, 'GET', '/api/meta')[1])
        for want in ('originalClassic', 'mediumClassic', 'smallClassic', 'demo_capsule_corner'):
            assert want in meta['layouts'], want
        names = [t['name'] for t in meta['teams']]
        for want in ('DirectionalGhost', 'CoordinatedGhostTeam', 'EnhancedCoordinatedGhostTeam', 'ArcadeGhostTeam'):
            assert want in names, names
        assert meta['voronoi'] == os.path.isfile(os.path.join(ROOT, 'multiagent', 'voronoiGhostAgents.py'))
        assert [p['name'] for p in meta['pacmen']][:1] == ['GreedyAgent']
        facts = json.loads(_req(port, 'GET', '/api/facts')[1])
        assert set(facts['levels']) == {str(i) for i in range(1, 8)}
        assert facts['levels']['1']['phase']['title'] == 'Search'
        hs = json.loads(_req(port, 'GET', '/api/highscores')[1])
        assert hs['file'] and hs['byScore'] and all(len(t['code']) == 3 for t in hs['byScore'])
        assert hs['byScore'] == sorted(hs['byScore'], key=lambda t: t['avgScore'])
        assert _req(port, 'GET', '/api/searchviz?algo=nope&maze=tinyMaze')[0] == 400
        assert _req(port, 'GET', '/api/searchviz?algo=bfs&maze=../../etc/passwd')[0] == 400
        assert _req(port, 'GET', '/api/benchmark/status')[0] == 200
        assert _req(port, 'POST', '/api/benchmark/run', {'games': 5, 'layout': 'no/such'})[0] == 400
        assert _req(port, 'GET', '/api/compare')[0] == 200
        assert _req(port, 'POST', '/api/live/start', {'layout': 'no/such', 'campaign': True})[0] == 400
    finally:
        srv.shutdown()


def test_highscore_aggregation_is_weighted_and_from_newest_file():
    import tempfile
    d = tempfile.mkdtemp()
    old = arcade_api.RESULTS
    arcade_api.RESULTS = d
    try:
        def mk(ts, a, b):
            m = lambda g, n, avg, k: dict(pacman='GreedyAgent', layout='mediumClassic', ghost=g, summary=dict(
                games=n, failed=0, win_rate=0.0, loss_rate=1.0, avg_score=avg, avg_kill_time=k))
            with open(os.path.join(d, ts + '.json'), 'w', encoding='utf-8') as f:
                json.dump(dict(timestamp=ts, matchups=[m('AlphaGhost', 10, a, 20), m('BetaGhost', 10, b, 40)]), f)
        mk('20260101-000000', 5, 50)
        mk('20260202-000000', 100, 0)      # newest: Beta now stronger
        hs = arcade_api.highscores()
        assert hs['timestamp'] == '20260202-000000'
        assert [t['team'] for t in hs['byScore']] == ['BetaGhost', 'AlphaGhost']
        assert [t['team'] for t in hs['byKill']] == ['AlphaGhost', 'BetaGhost']
        assert arcade_api.team_code('EnhancedCoordinatedGhostTeam') == 'ECG' and arcade_api.team_code('Random') == 'RAN'
    finally:
        arcade_api.RESULTS = old
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------------------------ search viz
def _walls(d):
    return [[ch == '%' for ch in row] for row in d['walls']]            # row 0 = top


def test_searchviz_matches_search_py():
    import searchviz
    costs = {}
    for maze in ('tinyMaze', 'mediumMaze'):
        for algo in ('dfs', 'bfs', 'ucs', 'astar'):
            d = searchviz.run_isolated(algo, maze)
            walls = _walls(d)
            H = d['height']
            free = lambda c: not walls[H - 1 - c[1]][c[0]]
            ex = [tuple(c) for c in d['expanded']]
            assert ex[0] == tuple(d['start']), 'search starts by expanding the start cell'
            assert len(set(ex)) == len(ex), 'every cell is expanded at most once'
            assert all(free(c) for c in ex)
            assert tuple(d['goal']) in {tuple(s) for succ in d['succ'] for s in succ} or tuple(d['goal']) == ex[0]
            for (x, y), succ in zip(ex, d['succ']):                       # successors are neighbours
                assert all(abs(a - x) + abs(b - y) == 1 for a, b in succ)
            # a cell can only be expanded after something expanded earlier discovered it
            seen = {ex[0]}
            for i, c in enumerate(ex):
                assert c in seen, (algo, maze, i)
                seen.update(tuple(s) for s in d['succ'][i])
            path = [tuple(p) for p in d['path']]
            assert path[0] == tuple(d['start']) and path[-1] == tuple(d['goal'])
            assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 and free(b) for a, b in zip(path, path[1:]))
            assert d['cost'] == len(path) - 1 == len(d['actions']), 'unit step cost'
            assert d['expandedCount'] == len(ex)
            costs[(algo, maze)] = (d['cost'], d['expandedCount'])
    for maze in ('tinyMaze', 'mediumMaze'):
        opt = costs[('bfs', maze)][0]
        assert costs[('ucs', maze)][0] == opt == costs[('astar', maze)][0]
        assert costs[('dfs', maze)][0] >= opt
        assert costs[('astar', maze)][1] <= costs[('ucs', maze)][1], 'a consistent heuristic never expands more than UCS'
    # cross-check against search.py run directly in a clean process (same numbers, nothing recorded)
    code = ("import sys; sys.path.insert(0, %r); import layout, pacman, search, searchAgents; "
            "gs = pacman.GameState(); gs.initialize(layout.getLayout('mediumMaze'), 0); "
            "p = searchAgents.PositionSearchProblem(gs, warn=False, visualize=False); a = search.breadthFirstSearch(p); "
            "print(p.getCostOfActions(a), p._expanded)") % ROOT
    out = subprocess.run([sys.executable, '-I', '-c', code], cwd=ROOT, capture_output=True, text=True, encoding='utf-8').stdout.split()
    assert int(out[0]) == costs[('bfs', 'mediumMaze')][0]


def test_searchviz_route_matches_module():
    srv, port = _server()
    try:
        st, body = _req(port, 'GET', '/api/searchviz?algo=astar&maze=tinyMaze')
        d = json.loads(body)
        assert st == 200 and d['algo'] == 'astar' and d['cost'] == 8 and d['source'] == 'search.py:aStarSearch'
    finally:
        srv.shutdown()


# ------------------------------------------------------------------------------------------ session rules
def test_progress_lives_extra_life_and_game_over():
    p = session.ArcadeProgress()
    assert (p.lives, p.level) == (3, 1)
    assert not p.score_update(9990)
    assert p.score_update(10000) and p.lives == 4, 'extra life at 10,000'
    assert not p.score_update(20000) and p.lives == 4, 'only once'
    assert p.died() and p.lives == 3
    assert p.died() and p.died() and p.lives == 1
    assert not p.died() and p.lives == 0 and p.over, 'GAME OVER after the last life'
    assert p.cleared() == 2
    q = session.ArcadeProgress(lives=1)
    assert not q.died() and q.over
    assert session.fruit_for(1) == ('cherry', 100) and session.fruit_for(99)[0] == 'key' and session.fruit_for(0)[0] == 'cherry'


def test_campaign_session_plays_lives_to_game_over():
    hub = live.Hub()
    q = hub.subscribe()
    params = live.clean_params(dict(layout='smallClassic', pacman='GreedyAgent', ghosts='DirectionalGhost', arcade=False,
                                    campaign=True, lives=2, tickRate=60, seed=3))
    params['readyDelay'] = 0.05
    s = session.CampaignSession(hub, params)
    s.thread.start()
    s.thread.join(timeout=90)
    assert not s.thread.is_alive(), 'campaign must end by itself when lives run out'
    events, headers, phases, lives_seen = [], 0, [], set()
    while not q.empty():
        ev, data = q.get_nowait()
        events.append(ev)
        if ev == 'header':
            headers += 1
        if ev == 'status':
            phases.append(json.loads(data).get('phase'))
        if ev == 'frame':
            lives_seen.add(json.loads(data)['hud']['lives'])
    assert headers == 2, 'one game per life (2 lives, GreedyAgent is caught each time)'
    assert 'ready' in phases and 'dying' in phases and phases[-1] == 'gameover'
    assert lives_seen == {2, 1}
    assert s.result['gameover'] and s.prog.lives == 0 and events[-1] in ('status', 'end')


def test_dots_stay_eaten_after_a_death():
    hub = live.Hub()
    params = live.clean_params(dict(layout='smallClassic', pacman='GreedyAgent', ghosts='DirectionalGhost', arcade=False,
                                    campaign=True, lives=2, tickRate=60, seed=3))
    params['readyDelay'] = 0.05
    s = session.CampaignSession(hub, params)
    foods = []
    orig = s.after_move

    def spy(data):
        orig(data)
        foods.append((s.prog.lives, data.food.count()))
    s.after_move = spy
    s.thread.start()
    s.thread.join(timeout=90)
    first = [f for l, f in foods if l == 2]
    second = [f for l, f in foods if l == 1]
    assert first and second and second[0] <= first[-1] + 1, 'second life starts with the first life\'s dots still eaten'
    assert s.level_food >= max(f for _, f in foods)


# ------------------------------------------------------------------------------------------ static hygiene
def test_no_external_urls_in_static():
    bad = []
    pat = re.compile(r'''(?:src|href|url\(|@import|fetch\(|EventSource\(|import\s.*from)\s*=?\s*["']?\s*(https?:)?//''', re.I)
    for dirpath, _, files in os.walk(STATIC):
        for fn in files:
            if not fn.endswith(('.html', '.css', '.js', '.mjs')):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, 'r', encoding='utf-8') as f:
                for n, line in enumerate(f, 1):
                    if pat.search(line):
                        bad.append('%s:%d: %s' % (os.path.relpath(path, STATIC), n, line.strip()[:100]))
                    for m in re.finditer(r'https?://[^\s"\'<>)]+', line):
                        if 'www.w3.org' not in m.group(0):         # SVG namespace is not a fetch
                            bad.append('%s:%d: %s' % (os.path.relpath(path, STATIC), n, m.group(0)))
    assert not bad, 'external URLs found:\n' + '\n'.join(bad)
    for want in ('press-start-2p-latin-400-normal.woff2', 'OFL-PressStart2P.txt', 'space-mono-latin-400-normal.woff2'):
        assert os.path.isfile(os.path.join(STATIC, 'fonts', want)), want


def test_attract_and_pages_reference_only_local_files():
    with open(os.path.join(STATIC, 'play.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    for ref in re.findall(r'(?:src|href)="([^"#]+)"', html):
        if ref.startswith('data:'):
            continue
        assert os.path.isfile(os.path.join(STATIC, ref)), ref


# ------------------------------------------------------------------------------------------ layers (node)
def test_layers_logic_under_node():
    node = shutil.which('node')
    if not node:
        print('  (node not found: skipping layers_test.mjs)')
        return
    p = subprocess.run([node, os.path.join(HERE, 'layers_test.mjs')], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert p.returncode == 0 and 'ok layers_test' in p.stdout, p.stdout + p.stderr


def test_frames_carry_every_layer_input():
    """The layers need roles, targets, paths, predictedPacman, reservedTiles, tacticalState, scaredTimer on v2 frames."""
    name = 'mediumClassic_GreedyAgent_EnhancedCoordinatedGhostTeam_s12_v2.jsonl'
    with open(os.path.join(DASH, 'traces', name), 'r', encoding='utf-8') as f:
        recs = [json.loads(l) for l in f if l.strip()]
    fr = [r for r in recs if r['type'] == 'frame']
    keys = set(fr[0])
    assert {'tacticalState', 'macroStrategy', 'predictedPacman', 'reservedTiles'} <= keys
    g = fr[0]['ghosts'][0]
    assert {'role', 'target', 'path', 'scaredTimer', 'mode', 'fpos'} <= set(g)
    assert any(f['ghosts'][0]['path'] for f in fr)


# ------------------------------------------------------------------------------------------ Phase 12: modes
def test_mode_presets_under_node():
    node = shutil.which('node')
    if not node:
        print('  (node not found: skipping modes_test.mjs)')
        return
    p = subprocess.run([node, os.path.join(HERE, 'modes_test.mjs')], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert p.returncode == 0 and 'ok modes_test' in p.stdout, p.stdout + p.stderr


def _read(*parts):
    with open(os.path.join(STATIC, *parts), 'r', encoding='utf-8') as f:
        return f.read()


def test_mode_presets_point_at_things_that_exist():
    """Each mode's maze and ghost team must exist (the JS test pins the exact values; this pins reality)."""
    modes = _read('play', 'modes.js')
    meta = arcade_api.meta()
    teams = {t['name'] for t in meta['teams']}
    for layout, ghosts in re.findall(r"layout: '(\w+)', ghosts: '(\w+)'", modes):
        assert layout in meta['layouts'], layout
        assert ghosts in teams, ghosts
    for g in re.findall(r"versusGhosts: '(\w+)'", modes):
        assert g in teams, g
    assert "store.get('pac.lastMode', 'ours')" in _read('play', 'screens.js'), 'first run highlights OUR GHOSTS'


def test_old_deep_links_still_resolve():
    app, levels, screens = _read('play', 'app.js'), _read('play', 'levels.js'), _read('play', 'screens.js')
    for route in ('menu', 'play', 'watch', 'run', 'levels', 'scores', 'replays', 'options', 'about', 'versus', 'more'):
        assert "case '%s'" % route in app, route
    run_links = re.findall(r"#/run\?[^'\"]+", levels)
    assert len(run_links) >= 4
    meta = arcade_api.meta()
    for link in run_links:
        from urllib.parse import parse_qs
        q = {k: v[0] for k, v in parse_qs(link.split('?', 1)[1]).items()}
        assert q['kind'] in ('play', 'watch') and q['layout'] in meta['layouts'], link
        assert q['ghosts'] in {t['name'] for t in meta['teams']}, link
        assert q['preset'] in ('classic', 'coach', 'teacher'), link          # old presets still parsed by run()
    assert "['classic', 'coach', 'teacher'].includes(q.preset)" in screens
    for hsh in ('#/levels/1?try=1', '#/replays/auto', '#/scores'):
        assert hsh in levels, hsh


def test_experimental_teams_are_grouped_with_one_line_descriptions():
    meta = arcade_api.meta()
    by = {t['name']: t for t in meta['teams']}
    for n in ('SilentFogGhostTeam', 'LossyChatterGhostTeam', 'VoronoiExpectimaxGhostTeam'):
        assert by[n]['group'] == 'experimental' and by[n]['blurb'].startswith('Experimental'), n
    for n in ('DirectionalGhost', 'EnhancedCoordinatedGhostTeam', 'ArcadeGhostTeam'):
        assert by[n]['group'] == 'main'
    names = [t['name'] for t in meta['teams']]
    first_exp = min(i for i, t in enumerate(meta['teams']) if t['group'] == 'experimental')
    assert all(t['group'] == 'experimental' for t in meta['teams'][first_exp:]), 'experimental teams sit at the bottom'
    assert all(t['blurb'] and '\n' not in t['blurb'] and t['label'] for t in meta['teams']), names


def test_main_flow_has_no_internal_jargon():
    text = _read('play', 'screens.js') + _read('play', 'modes.js')
    menu = text[text.index('const MENU'):text.index('// ---- custom setup')]
    for bad in ('BFS', 'recorder', 'telemetry', 'hub', 'preset', 'HIGH SCORES', 'LEVEL SELECT', 'WATCH AI'):
        assert bad not in menu.replace('preset:', '').replace('q.preset', ''), bad
    for want in ('PLAY', 'WATCH', 'LEARN', 'SCORES', 'MORE'):
        assert "label: '%s'" % want in menu, want
    assert menu.count("hash: '#/") == 8       # 5 main items + 3 under MORE


# ------------------------------------------------------------------------------------------ Phase 12: VERSUS
def test_versus_verdict_is_built_from_the_runs():
    import versus
    mk = lambda c, t, s=0: dict(caughtAt=c, ticks=t, score=s)
    assert 'OUR GHOSTS caught Pac-Man in 11 moves' in versus.verdict(mk(63, 63), mk(11, 11), 400)
    assert '52 moves faster' in versus.verdict(mk(63, 63), mk(11, 11), 400)
    assert versus.verdict(mk(20, 20), mk(30, 30), 400).startswith('The original ghosts caught Pac-Man in 20 moves')
    assert 'tie' in versus.verdict(mk(9, 9), mk(9, 9), 400)
    assert 'did not catch him in 400 moves' in versus.verdict(mk(None, 400), mk(15, 15), 400)
    assert versus.verdict(mk(None, 400, 5), mk(None, 400, 7), 400).startswith('Neither team caught Pac-Man in 400 moves')
    assert 'in 1 move.' in versus.verdict(mk(None, 5), mk(1, 1), 400) or '1 move' in versus.verdict(mk(None, 5), mk(1, 1), 400)


def test_versus_runs_are_real_and_deterministic():
    import versus
    p = versus.clean(dict(layout='smallClassic', seed=7, maxTicks=200))
    a = [versus.play_side(s, p) for s in versus.SIDES]
    b = [versus.play_side(s, p) for s in versus.SIDES]
    for x, y in zip(a, b):
        assert (x['ticks'], x['caughtAt'], x['score']) == (y['ticks'], y['caughtAt'], y['score']), 'same seed, same game'
        assert x['frames'][-1]['score'] == x['score'], 'last frame carries the real final score'
        assert x['header']['ghostTeam'] == x['ghosts'] and x['header']['pacmanAgent'] == 'GreedyAgent'
        assert x['header']['seed'] == 7 and x['header']['layout'] == 'smallClassic'
        assert len(x['frames']) == x['ticks'] + 1
    assert [x['ghosts'] for x in a] == ['DirectionalGhost', 'EnhancedCoordinatedGhostTeam']
    assert a[0]['frames'][0]['pacman']['pos'] == a[1]['frames'][0]['pacman']['pos'], 'same start'
    assert all(x['caughtAt'] is not None for x in a), 'GreedyAgent is caught on smallClassic'


def test_versus_api_end_to_end_and_cleanup():
    import time
    import versus
    srv, port = _server()
    try:
        assert _req(port, 'POST', '/api/versus/start', {'layout': 'no/such'})[0] == 400
        assert _req(port, 'GET', '/api/versus/result')[0] == 409
        st, _ = _req(port, 'POST', '/api/versus/start', {'layout': 'smallClassic', 'seed': 7, 'maxTicks': 200})
        assert st == 200
        for _i in range(200):
            s = json.loads(_req(port, 'GET', '/api/versus')[1])
            if s['state'] != 'running':
                break
            time.sleep(0.1)
        assert s['state'] == 'done', s
        d = json.loads(_req(port, 'GET', '/api/versus/result')[1])
        assert [x['id'] for x in d['sides']] == ['stock', 'ours']
        expect = versus.verdict(d['sides'][0], d['sides'][1], d['params']['maxTicks'])
        assert d['verdict'] == expect, 'the verdict line is computed from the same two results'
        for x in d['sides']:
            assert x['frames'] and x['ticks'] == len(x['frames']) - 1
        _req(port, 'POST', '/api/versus/stop', {})
        assert json.loads(_req(port, 'GET', '/api/versus')[1])['state'] == 'idle'
        assert versus.VERSUS.payload is None, 'frames are dropped when the player leaves'
    finally:
        versus.VERSUS.stop()
        srv.shutdown()


def test_navigation_stays_shallow():
    screens = _read('play', 'screens.js')
    assert screens.count('numbers: true') == 3, 'main menu, MORE and the mode picker jump with number keys'
    for want in ("['Esc', 'MENU']", "['Esc', 'BACK']", "['Esc', 'TITLE']"):
        assert want in screens, want
    with open(os.path.join(DASH, 'DESIGN.md'), 'r', encoding='utf-8') as f:
        assert 'Key presses from the title' in f.read()


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
