"""Commander feed: turns real coordinator state into short order messages.

The "commander" in the dashboard is a display element only (a ring on the maze and
a ticker); it is never a game agent.  Every message here is a *diff of actual
coordinator state* between two ticks, read from `getTelemetry()` when the
coordinator offers it and from its attributes (`roles`, `assignedTargets`,
`currentTacticalState`, `currentStrategy`) otherwise.  Nothing is scripted: with no
coordinator (RandomGhost, DirectionalGhost) the feed stays empty.

    feed = CommanderFeed()
    msgs = feed.update(tick, read_coordinator(coord))
"""

# role / mode -> order verb.  The verb is presentation; the role, mode and target are read from the coordinator.
VERBS = {
    'chaser': 'CHASE', 'interceptor': 'INTERCEPT', 'blocker': 'BLOCK', 'sweeper': 'SWEEP',
    'capsule_guard': 'GUARD',
    'blinky': 'CHASE', 'pinky': 'AMBUSH', 'inky': 'FLANK', 'clyde': 'ROAM',
}
MODE_VERBS = {'eyes': 'RETURN', 'house': 'HOLD', 'exit': 'EXIT', 'frightened': 'FLEE'}

JUMP_TILES = 5        # a retarget this far (Manhattan) counts as a new order ...
JUMP_TICKS = 12       # ... but not more often than this per ghost


def read_coordinator(c):
    """Snapshot of a coordinator as plain data, or None when there is none."""
    if c is None:
        return None
    tactical = getattr(c, 'currentTacticalState', None)
    macro = getattr(c, 'currentStrategy', None)
    roles = dict(getattr(c, 'roles', {}) or {})
    targets = dict(getattr(c, 'assignedTargets', {}) or {})
    modes = dict(getattr(c, 'modes', {}) or {})
    source = 'attributes'
    tele = getattr(c, 'getTelemetry', None)
    extra = None
    if callable(tele):
        try:
            t = tele()
        except Exception:         # telemetry must never break a game
            t = None
        if isinstance(t, dict):
            extra = t
            source = 'getTelemetry'
            tactical = t.get('tacticalState', t.get('currentTacticalState', tactical))
            macro = t.get('macroStrategy', t.get('currentStrategy', macro))
            if isinstance(t.get('roles'), dict):
                roles = {int(k): v for k, v in t['roles'].items()}
            for key in ('assignedTargets', 'targets'):      # EnhancedCoordinatedGhostTeam uses 'targets'
                if isinstance(t.get(key), dict):
                    targets = {int(k): v for k, v in t[key].items()}
            if isinstance(t.get('scaredTimers'), dict) and not modes:
                modes = {int(k): ('frightened' if v > 0 else 'active') for k, v in t['scaredTimers'].items()}
            if isinstance(t.get('modes'), dict):
                modes = {int(k): v for k, v in t['modes'].items()}
    return dict(tactical=tactical, macro=macro, roles=roles, targets=targets, modes=modes,
                source=source, telemetry=extra)


def _tile(t):
    return None if t is None else (int(t[0]), int(t[1]))


def _label(s):
    return str(s).replace('_', ' ').upper()


class CommanderFeed:
    def __init__(self):
        self.tactical = self.macro = None
        self.roles, self.modes, self.targets, self.lastOrder = {}, {}, {}, {}
        self.seq = 0

    def _msg(self, tick, ghost, text, target=None, kind='order'):
        self.seq += 1
        return dict(id=self.seq, tick=tick, ghost=ghost, src='ALL' if ghost == 0 else 'G%d' % ghost,
                    text=text, target=list(target) if target else None, kind=kind)

    def update(self, tick, snap):
        """Return the new messages for this tick (possibly empty)."""
        if snap is None:
            return []
        out = []
        flipped = snap['tactical'] != self.tactical and snap['tactical'] is not None
        if flipped:
            out.append(self._msg(tick, 0, _label(snap['tactical']), kind='state'))
        if snap['macro'] != self.macro and snap['macro'] is not None:
            out.append(self._msg(tick, 0, _label(snap['macro']), kind='state'))
        self.tactical, self.macro = snap['tactical'], snap['macro']
        for g in sorted(set(snap['roles']) | set(snap['modes'])):
            role, mode, tgt = snap['roles'].get(g), snap['modes'].get(g), _tile(snap['targets'].get(g))
            normal = mode in (None, 'active')
            changed = (role != self.roles.get(g)) or (mode != self.modes.get(g)) or (flipped and tgt is not None)
            prev = self.targets.get(g)
            jump = (not changed and tgt is not None and prev is not None and
                    abs(tgt[0] - prev[0]) + abs(tgt[1] - prev[1]) >= JUMP_TILES and
                    tick - self.lastOrder.get(g, -10**9) >= JUMP_TICKS)
            if (changed and (role is not None or mode is not None)) or jump:
                if not normal:
                    verb = MODE_VERBS.get(mode, _label(mode))
                elif snap['tactical'] == 'SCATTER':
                    verb = 'SCATTER'                  # the target is a scatter/flee tile, not a hunt target
                else:
                    verb = VERBS.get(role, _label(role) if role else 'HOLD')
                text = verb + (' (%d,%d)' % tgt if tgt and mode not in ('house', 'frightened') else '')
                out.append(self._msg(tick, g, text, tgt))
                self.lastOrder[g] = tick
                self.targets[g] = tgt
            elif tgt is not None and prev is None:
                self.targets[g] = tgt
            self.roles[g], self.modes[g] = role, mode
        return out
