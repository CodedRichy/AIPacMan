"""Live play, v2 frames and commander feed tests. Plain asserts:
    python3 dashboard/tests/test_live.py
"""
import http.client
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(HERE)
sys.path.insert(0, DASH)

import commander as cmd  # noqa: E402
import live  # noqa: E402


class FakeCoord:
    """Looks like a coordinator; the feed may only report what it holds."""
    def __init__(self):
        self.currentTacticalState = 'COORDINATED_HUNT'
        self.currentStrategy = 'EARLY_SPREAD'
        self.roles = {1: 'chaser', 2: 'interceptor'}
        self.assignedTargets = {1: (3, 4), 2: (14, 7)}


def test_commander_messages_come_from_state_diffs():
    c, feed = FakeCoord(), cmd.CommanderFeed()
    m0 = feed.update(0, cmd.read_coordinator(c))
    texts = [(m['src'], m['text']) for m in m0]
    assert ('ALL', 'COORDINATED HUNT') in texts and ('G2', 'INTERCEPT (14,7)') in texts and ('G1', 'CHASE (3,4)') in texts
    assert feed.update(1, cmd.read_coordinator(c)) == []                 # nothing changed -> silence
    c.roles[2] = 'blocker'                                               # a real role change -> an order
    m = feed.update(2, cmd.read_coordinator(c))
    assert [(x['src'], x['text']) for x in m] == [('G2', 'BLOCK (14,7)')]
    c.assignedTargets[1] = (3, 5)                                        # small retarget: no new order
    assert feed.update(3, cmd.read_coordinator(c)) == []
    c.assignedTargets[1] = (20, 20)                                      # big jump, but after the throttle
    assert feed.update(30, cmd.read_coordinator(c))[0]['text'] == 'CHASE (20,20)'
    c.currentTacticalState = 'SCATTER'
    out = feed.update(31, cmd.read_coordinator(c))
    assert out[0]['text'] == 'SCATTER' and out[0]['ghost'] == 0
    assert cmd.CommanderFeed().update(0, cmd.read_coordinator(None)) == []   # no coordinator: no messages


def test_read_coordinator_prefers_telemetry():
    class T(FakeCoord):
        def getTelemetry(self):
            return dict(tacticalState='TRAP_AMBUSH', macroStrategy='MID_PRESSURE', roles={1: 'sweeper'},
                        targets={1: [5, 6]}, scaredTimers={1: 0})
    s = cmd.read_coordinator(T())
    assert s['source'] == 'getTelemetry' and s['tactical'] == 'TRAP_AMBUSH'
    assert s['roles'] == {1: 'sweeper'} and s['targets'] == {1: [5, 6]}
    assert cmd.read_coordinator(FakeCoord())['source'] == 'attributes'


def test_v2_arcade_recording_has_subtile_positions_and_commander():
    path, header, frames, footer = live.record_v2('originalClassic', 'GreedyAgent', 'ArcadeGhostTeam', True, 1,
                                                  seed=3, max_ticks=80, write=False)
    assert header['schema'] == 2 and header['arcade'] and header['house']['doorXs'] == [13, 14]
    assert frames[0]['schema'] == 2 and frames[5]['dt'] > 0
    xs = {f['pacman']['fpos'][0] for f in frames}
    assert any(abs(x - round(x)) > 0.01 for x in xs), 'Pac-Man must move in sub-tile steps'
    for f in frames:                                    # v1 fields still present and ints
        assert all(isinstance(c, int) for c in f['pacman']['pos'])
        for g in f['ghosts']:
            assert {'index', 'pos', 'scaredTimer', 'role', 'target', 'path', 'fpos', 'mode'} <= set(g)
    msgs = [m for f in frames for m in f['commander']['messages']]
    assert any(m['text'] == 'SCATTER' and m['src'] == 'ALL' for m in msgs)
    assert frames[10]['commander']['source'] == 'getTelemetry'
    assert footer['type'] == 'end'


def test_v2_with_enhanced_team_uses_its_telemetry():
    _, header, frames, _ = live.record_v2('mediumClassic', 'GreedyAgent', 'EnhancedCoordinatedGhostTeam', False, 1,
                                          seed=12, max_ticks=40, write=False)
    assert not header['arcade']
    msgs = [m for f in frames for m in f['commander']['messages']]
    assert msgs and all(m['text'] for m in msgs)
    assert {m['text'] for m in msgs if m['ghost'] == 0} & {'COORDINATED HUNT', 'SCATTER', 'DEFEND CAPSULE', 'TRAP AMBUSH'}
    assert frames[3]['telemetry']['roles']


def _req(port, method, path, body=None, host=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    h = {'Content-Type': 'application/json'}
    if host:
        h['Host'] = host
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    data = r.read()
    return r.status, data


def test_live_server_stream_keys_and_guards():
    srv = live.make_live_server('127.0.0.1', 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _req(port, 'GET', '/api/live/state')[0] == 200
        assert _req(port, 'GET', '/api/live/state', host='evil.example')[0] == 403        # DNS rebinding guard
        assert _req(port, 'POST', '/api/key', {'dir': 'East'}, host='evil.example:%d' % port)[0] == 403
        try:
            live.make_live_server('0.0.0.0', 0)
            raise AssertionError('must refuse non-loopback hosts')
        except ValueError:
            pass
        st, body = _req(port, 'POST', '/api/live/start', dict(layout='originalClassic', arcade=True, tickRate=60, level=1))
        assert st == 200, body
        assert _req(port, 'POST', '/api/live/start', dict(layout='no/such'))[0] == 400
        live.LIVE.session.params['readyDelay'] = 0.05
        for _ in range(100):
            if live.LIVE.session.agent is not None:
                break
            time.sleep(0.05)
        assert _req(port, 'POST', '/api/key', {'dir': 'West'})[1] == b'{"ok": true}'
        assert _req(port, 'POST', '/api/key', {'dir': 'Sideways'})[0] == 400
        # read the SSE stream: header first, then frames in which Pac-Man moves west in sub-tile steps
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        c.request('GET', '/live/stream')
        r = c.getresponse()
        events, deadline = [], time.time() + 8
        buf = b''
        while time.time() < deadline and sum(1 for e in events if e[0] == 'frame') < 12:
            buf += r.fp.read1(65536) if hasattr(r.fp, 'read1') else r.read(1)
            while b'\n\n' in buf:
                blk, buf = buf.split(b'\n\n', 1)
                lines = blk.decode().split('\n')
                ev = next((l[7:] for l in lines if l.startswith('event: ')), None)
                dat = next((l[6:] for l in lines if l.startswith('data: ')), None)
                if ev and dat:
                    events.append((ev, json.loads(dat)))
        c.close()
        names = [e[0] for e in events]
        assert names[0] == 'header' and 'frame' in names and 'status' in names
        pac = [e[1]['pacman']['fpos'][0] for e in events if e[0] == 'frame']
        assert pac[-1] < pac[0], 'Pac-Man should have moved west after the key press: %r' % pac
        assert st == 200
        assert _req(port, 'POST', '/api/live/pause', {'paused': True})[0] == 200
        assert live.LIVE.session.paused
        assert _req(port, 'POST', '/api/live/stop')[0] == 200
    finally:
        if live.LIVE.session:
            live.LIVE.session.stop()
        srv.shutdown()


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
