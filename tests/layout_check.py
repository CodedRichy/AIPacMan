"""Static sanity checks for demo layouts (rectangular, 1 Pac-Man, reachable food)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYOUT_DIR = os.path.join(ROOT, 'multiagent', 'layouts')


def check_layout_file(path):
    """Return a list of problems (empty list = fine)."""
    with open(path, encoding='utf-8') as f:
        rows = [l.rstrip('\n') for l in f if l.strip()]
    problems = []
    if len({len(r) for r in rows}) != 1:
        problems.append('ragged rows: %s' % sorted({len(r) for r in rows}))
        return problems
    h, w = len(rows), len(rows[0])
    pac = [(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == 'P']
    if len(pac) != 1:
        problems.append('expected exactly 1 P, found %d' % len(pac))
        return problems
    if not any('G' in r for r in rows):
        problems.append('no ghosts')
    for y in range(h):
        for x in range(w):
            if (x in (0, w - 1) or y in (0, h - 1)) and rows[y][x] != '%':
                problems.append('border not wall at %s' % ((x, y),))
    seen, stack = {pac[0]}, [pac[0]]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and rows[ny][nx] != '%' and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    for y in range(h):
        for x in range(w):
            if rows[y][x] in '.oG' and (x, y) not in seen:
                problems.append('unreachable %r at %s' % (rows[y][x], (x, y)))
    if not any(c == '.' for r in rows for c in r):
        problems.append('no food')
    return problems


if __name__ == '__main__':
    import sys
    bad = 0
    for name in sorted(os.listdir(LAYOUT_DIR)):
        if name.startswith('demo_') and name.endswith('.lay'):
            p = check_layout_file(os.path.join(LAYOUT_DIR, name))
            print(name, 'OK' if not p else p)
            bad += bool(p)
    sys.exit(1 if bad else 0)
