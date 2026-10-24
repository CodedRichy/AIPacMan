"""Recorder, schema and server smoke tests. Plain asserts: run with either
    python3 dashboard/tests/test_dashboard.py      (no dependencies)
    python3 -m pytest dashboard/tests               (if pytest is installed)
"""
import json
import os
import sys
import tempfile
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(HERE)
sys.path.insert(0, DASH)

import record  # noqa: E402

DIRS = {'North', 'South', 'East', 'West', 'Stop'}


def _record(ghosts='EnhancedCoordinatedGhostTeam', ticks=50, out=None):
    return record.record_game('mediumClassic', 'GreedyAgent', ghosts, seed=3,
                              max_ticks=ticks, out_dir=out, write=out is not None)


def check_frame(fr, header):
    W, H = header['width'], header['height']
    assert fr['type'] == 'frame'
    assert isinstance(fr['score'], (int, float))
    assert fr['pacman']['dir'] in DIRS
    for key in ('pacman',):
        x, y = fr[key]['pos']
        assert 0 <= x < W and 0 <= y < H
    assert len(fr['ghosts']) == header['numGhosts']
    for g in fr['ghosts']:
        assert {'index', 'pos', 'scaredTimer', 'role', 'target', 'path'} <= set(g)
        assert g['scaredTimer'] >= 0
        if g['path']:
            assert g['path'][0] == g['pos']
            assert g['path'][-1] == g['target']
    for p in fr['food'] + fr['capsules']:
        assert not header['walls'][H - 1 - p[1]][p[0]] == '%'
    assert {'tacticalState', 'macroStrategy', 'predictedPacman', 'reservedTiles'} <= set(fr)
    json.dumps(fr)    # serialisable


def test_recorder_50_ticks():
    path, header, frames, footer = _record(ticks=50)
    assert header['schema'] == 1 and header['layout'] == 'mediumClassic'
    assert len(header['walls']) == header['height']
    assert all(len(r) == header['width'] for r in header['walls'])
    assert 10 < len(frames) <= 52          # ends early only if Pac-Man dies
    assert [f['tick'] for f in frames] == list(range(len(frames)))
    for fr in frames:
        check_frame(fr, header)
    assert frames[0]['score'] == 0
    assert any(f['tacticalState'] for f in frames)
    assert any(g['role'] for f in frames for g in f['ghosts'])
    assert footer['type'] == 'end' and footer['ticks'] == len(frames) - 1


def test_jsonl_roundtrip_and_baseline_team():
    with tempfile.TemporaryDirectory() as d:
        path, header, frames, footer = _record('CoordinatedGhostTeam', 30, d)
        lines = [json.loads(l) for l in open(path, encoding='utf-8')]
        assert lines[0]['type'] == 'header' and lines[-1]['type'] == 'end'
        assert len(lines) == len(frames) + 2
        # base coordinator has no tactical state; the recorder must cope
        assert all(f['tacticalState'] is None for f in frames)
        assert any(g['role'] == 'chaser' for f in frames for g in f['ghosts'])


def test_deterministic_with_seed():
    a = _record(ticks=20)[2]
    b = _record(ticks=20)[2]
    assert [f['pacman']['pos'] for f in a] == [f['pacman']['pos'] for f in b]


def test_server_smoke():
    import server
    with tempfile.TemporaryDirectory() as d:
        _record(ticks=15, out=d)
        server.TRACES = d
        os.environ['DASH_QUIET'] = '1'
        srv = server.make_server('127.0.0.1', 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % port
        try:
            page = urllib.request.urlopen(base + '/').read().decode('utf-8')
            assert '<canvas id="maze"' in page
            assert urllib.request.urlopen(base + '/app.js').status == 200
            traces = json.load(urllib.request.urlopen(base + '/api/traces'))
            assert len(traces) == 1 and traces[0]['layout'] == 'mediumClassic'
            name = traces[0]['name']
            body = urllib.request.urlopen(base + '/api/traces/' + name).read().decode('utf-8')
            assert body.splitlines()[0].startswith('{"type":"header"')
            sse = urllib.request.urlopen('%s/stream?trace=%s&speed=64&start=2' % (base, name)).read().decode('utf-8')
            assert 'event: header' in sse and 'event: end' in sse
            assert 'id: 2\nevent: frame' in sse and 'id: 1\nevent: frame' not in sse
            for bad in ('/api/traces/..%2Fserver.py', '/stream?trace=../x'):
                try:
                    urllib.request.urlopen(base + bad)
                    raise AssertionError('should have been rejected: ' + bad)
                except urllib.error.HTTPError as e:
                    assert e.code in (400, 403, 404)
        finally:
            srv.shutdown()


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
