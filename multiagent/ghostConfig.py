"""Tunable parameters for the coordinated ghost teams.

NOT yet wired into coordinatedGhostAgents.py / enhancedGhostAgents.py -- see
docs/CONFIG_WIRING.md for the constant -> field mapping. Every default below
equals the value currently hard-coded in those files, so wiring this in with
defaults must not change behaviour.

Usage:
    from ghostConfig import GhostConfig, load_config
    cfg = load_config()                      # defaults + GHOST_CONFIG file + env overrides
    cfg = load_config('my.json')             # explicit file
    cfg.save('out.json')

Env overrides: GHOST_CONFIG=<path to JSON>, then any field as GHOST_<FIELD_UPPER>,
e.g. GHOST_PREDICTION_HORIZON=8 GHOST_USE_RESERVATION=false
GHOST_ROLE_PRIORITY='{"chaser":1,"interceptor":2,"blocker":3,"sweeper":4}'
"""
import dataclasses
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional


def _default_priority():
    return {'chaser': 1, 'interceptor': 2, 'blocker': 3, 'sweeper': 4}


@dataclass
class GhostConfig:
    # --- Trajectory prediction -------------------------------------------
    prediction_horizon: int = 5          # enhanced predictPacmanPosition steps
    base_prediction_horizon: int = 4     # base GhostCoordinator.predictPacmanPosition steps
    history_len: int = 6                 # Pac-Man position ring buffer length

    # --- Pincer ------------------------------------------------------------
    pincer_distance: int = 5             # tiles the interceptor looks ahead of Pac-Man
    use_pincer: bool = True              # False -> interceptor keeps base-class prediction target

    # --- Choke-point scoring (base coordinator, blocker role) ---------------
    choke_max_exits: int = 2             # tile counts as choke if open neighbours <= this
    choke_weight: float = 10.0           # score = (3 - exits) * weight / (dist + 1)

    # --- Path reservation ----------------------------------------------------
    use_reservation: bool = True
    role_priority: Dict[str, int] = field(default_factory=_default_priority)
    default_priority: int = 4            # priority of unknown roles (e.g. capsule_guard)

    # --- Tactical state machine ---------------------------------------------
    use_tactical_states: bool = True
    capsule_threat_distance: int = 4     # DEFEND_CAPSULE if Pac-Man within this Manhattan dist
    trap_max_exits: int = 2              # TRAP_AMBUSH if Pac-Man tile has <= this many exits
    # NEW knob (no current equivalent): minimum ticks a tactical state is held
    # before it may change. 0 reproduces today's per-tick re-evaluation.
    state_dwell_ticks: int = 0

    # --- Dynamic strategy switching -----------------------------------------
    use_strategy_switching: bool = True
    early_food_ratio: float = 0.50       # food ratio above this -> EARLY_SPREAD
    endgame_food_ratio: float = 0.20     # food ratio at/below this -> ENDGAME_COLLAPSE
    endgame_food_count: int = 5          # or <= this many dots left -> ENDGAME_COLLAPSE

    # --- Scared coordination --------------------------------------------------
    use_scared_scatter: bool = True
    # Ghosts flee while any ghost scaredTimer > this (0 = flee as soon as scared).
    scared_flee_threshold: int = 0
    flee_corner_inset: int = 2           # corner target = 2 tiles from the wall
    flee_search_span: int = 4            # tries offsets 0..span-1 along the diagonal

    # ----------------------------------------------------------------------
    def validate(self):
        errs = []
        for name in ('prediction_horizon', 'base_prediction_horizon', 'history_len',
                     'pincer_distance', 'capsule_threat_distance'):
            if getattr(self, name) < 1:
                errs.append('%s must be >= 1' % name)
        for name in ('state_dwell_ticks', 'scared_flee_threshold', 'flee_corner_inset',
                     'endgame_food_count'):
            if getattr(self, name) < 0:
                errs.append('%s must be >= 0' % name)
        if not 0.0 <= self.endgame_food_ratio <= self.early_food_ratio <= 1.0:
            errs.append('need 0 <= endgame_food_ratio <= early_food_ratio <= 1')
        if errs:
            raise ValueError('invalid GhostConfig: ' + '; '.join(errs))
        return self

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError('unknown GhostConfig fields: %s' % sorted(unknown))
        return cls(**d).validate()

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
            f.write('\n')

    @classmethod
    def load(cls, path):
        with open(path, encoding='utf-8') as f:
            return cls.from_dict(json.load(f))

    def with_env_overrides(self, environ=None):
        """Return a copy with GHOST_<FIELD> env vars applied."""
        env = os.environ if environ is None else environ
        values = self.to_dict()
        for f in dataclasses.fields(self):
            raw = env.get('GHOST_' + f.name.upper())
            if raw is None:
                continue
            values[f.name] = _coerce(f, raw)
        return GhostConfig.from_dict(values)


def _coerce(f, raw):
    t = f.type if not isinstance(f.type, str) else {
        'int': int, 'float': float, 'bool': bool}.get(f.type, f.type)
    if t is bool:
        v = raw.strip().lower()
        if v in ('1', 'true', 'yes', 'on'):
            return True
        if v in ('0', 'false', 'no', 'off'):
            return False
        raise ValueError('GHOST_%s: not a boolean: %r' % (f.name.upper(), raw))
    if t is int:
        return int(raw)
    if t is float:
        return float(raw)
    return json.loads(raw)   # dict-valued fields


def load_config(path: Optional[str] = None, environ=None) -> GhostConfig:
    """defaults <- JSON file (path arg, else $GHOST_CONFIG) <- GHOST_* env vars."""
    env = os.environ if environ is None else environ
    path = path or env.get('GHOST_CONFIG')
    cfg = GhostConfig.load(path) if path else GhostConfig()
    return cfg.with_env_overrides(env)


if __name__ == '__main__':
    import sys
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(cfg.to_dict(), indent=2, sort_keys=True))
