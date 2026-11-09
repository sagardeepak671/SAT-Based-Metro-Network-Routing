"""Shared, encoder-independent helpers for the metro routing project.

Everything here works purely on the external conventions of SPEC.md:
(x, y) with x = column (0..N-1, increasing rightward) and y = row
(0..M-1, increasing downward).  Moves are L/R/U/D unit steps.

Contents:
  Problem / parse_city / format_city   .city file contract
  route_cells / count_turns            route geometry
  check_solution                       independent validity check of a witness
  enumerate_routes / brute_force       tiny exhaustive reference solver for
                                       small instances (evidence for expectations)

None of this reads the CNF or depends on encoder.cpp, so it can be used
to judge the encoder rather than merely mirror it.
"""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

Cell = Tuple[int, int]

MOVES: Dict[str, Cell] = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}


@dataclass
class Problem:
    scenario: int
    N: int  # columns
    M: int  # rows
    K: int  # lines
    J: int  # max turns per line
    lines: List[Tuple[int, int, int, int]] = field(default_factory=list)  # (sx, sy, ex, ey)
    popular: List[Cell] = field(default_factory=list)

    @property
    def P(self) -> int:
        return len(self.popular)

    def in_bounds(self, c: Cell) -> bool:
        return 0 <= c[0] < self.N and 0 <= c[1] < self.M

    def endpoints(self) -> Set[Cell]:
        s: Set[Cell] = set()
        for sx, sy, ex, ey in self.lines:
            s.add((sx, sy))
            s.add((ex, ey))
        return s


def parse_city(text: str) -> Problem:
    """Parse the .city format from SPEC.md. Raises ValueError on malformed input."""
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    if len(lines) < 2:
        raise ValueError("city file needs at least a scenario line and a header line")
    scenario = int(lines[0].split()[0])
    if scenario not in (1, 2):
        raise ValueError("scenario must be 1 or 2, got %r" % lines[0])
    header = [int(t) for t in lines[1].split()]
    if scenario == 1:
        if len(header) != 4:
            raise ValueError("scenario 1 header must be 'N M K J'")
        N, M, K, J = header
        P = 0
    else:
        if len(header) != 5:
            raise ValueError("scenario 2 header must be 'N M K J P'")
        N, M, K, J, P = header
    if N <= 0 or M <= 0 or K <= 0 or J < 0 or P < 0:
        raise ValueError("bad header values: %r" % header)
    if len(lines) < 2 + K + (1 if scenario == 2 and P > 0 else 0):
        raise ValueError("too few lines for K=%d" % K)
    prob = Problem(scenario, N, M, K, J)
    for k in range(K):
        toks = [int(t) for t in lines[2 + k].split()]
        if len(toks) != 4:
            raise ValueError("line %d must have 4 integers" % k)
        prob.lines.append((toks[0], toks[1], toks[2], toks[3]))
    if scenario == 2 and P > 0:
        toks = [int(t) for t in lines[2 + K].split()]
        if len(toks) != 2 * P:
            raise ValueError("popular-cell line must have exactly 2*P=%d integers" % (2 * P))
        prob.popular = [(toks[2 * i], toks[2 * i + 1]) for i in range(P)]
    return prob


def format_city(prob: Problem) -> str:
    out = [str(prob.scenario)]
    if prob.scenario == 1:
        out.append("%d %d %d %d" % (prob.N, prob.M, prob.K, prob.J))
    else:
        out.append("%d %d %d %d %d" % (prob.N, prob.M, prob.K, prob.J, prob.P))
    for sx, sy, ex, ey in prob.lines:
        out.append("%d %d %d %d" % (sx, sy, ex, ey))
    if prob.scenario == 2:
        out.append(" ".join("%d %d" % c for c in prob.popular))
    return "\n".join(out) + "\n"


def validate_problem(prob: Problem) -> List[str]:
    """Static sanity checks on the instance itself (not on any solution)."""
    errs: List[str] = []
    if prob.K != len(prob.lines):
        errs.append("K=%d but %d endpoint rows" % (prob.K, len(prob.lines)))
    seen: Dict[Cell, str] = {}
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):
        for label, c in (("start", (sx, sy)), ("end", (ex, ey))):
            if not prob.in_bounds(c):
                errs.append("line %d %s %r out of bounds" % (k, label, c))
            if c in seen:
                errs.append("line %d %s %r duplicates %s" % (k, label, c, seen[c]))
            seen[c] = "line %d %s" % (k, label)
    for c in prob.popular:
        if not prob.in_bounds(c):
            errs.append("popular cell %r out of bounds" % (c,))
    return errs


# ---------------------------------------------------------------- geometry

def route_cells(start: Cell, moves: Sequence[str]) -> List[Cell]:
    x, y = start
    cells = [(x, y)]
    for m in moves:
        dx, dy = MOVES[m]
        x, y = x + dx, y + dy
        cells.append((x, y))
    return cells


def count_turns(moves: Sequence[str]) -> int:
    return sum(1 for a, b in zip(moves, moves[1:]) if a != b)


def parse_moves(line: str) -> List[str]:
    """Parse one .metromap row: moves followed by a terminating 0."""
    toks = line.split()
    if not toks or toks[-1] != "0":
        raise ValueError("route row must end with 0: %r" % line)
    moves = toks[:-1]
    for m in moves:
        if m not in MOVES:
            raise ValueError("bad move %r in %r" % (m, line))
    return moves


def format_moves(moves: Sequence[str]) -> str:
    return " ".join(list(moves) + ["0"])


def check_solution(prob: Problem, routes: Sequence[Sequence[str]]) -> List[str]:
    """Independent check of a full witness. Returns a list of violations (empty = valid).

    Checks: one route per line, moves legal, in bounds, correct endpoints,
    simple (no repeated cell), turn limit, no cell shared between lines, and
    in scenario 2 every popular cell on some route.
    """
    errs: List[str] = []
    if len(routes) != prob.K:
        return ["expected %d routes, got %d" % (prob.K, len(routes))]
    owner: Dict[Cell, int] = {}
    for k, moves in enumerate(routes):
        sx, sy, ex, ey = prob.lines[k]
        for m in moves:
            if m not in MOVES:
                errs.append("line %d: illegal move %r" % (k, m))
                break
        else:
            cells = route_cells((sx, sy), moves)
            for c in cells:
                if not prob.in_bounds(c):
                    errs.append("line %d: cell %r out of bounds" % (k, c))
                    break
            if cells[-1] != (ex, ey):
                errs.append("line %d: ends at %r, expected %r" % (k, cells[-1], (ex, ey)))
            if len(set(cells)) != len(cells):
                errs.append("line %d: route revisits a cell (not simple)" % k)
            t = count_turns(moves)
            if t > prob.J:
                errs.append("line %d: %d turns exceeds J=%d" % (k, t, prob.J))
            for c in cells:
                if c in owner and owner[c] != k:
                    errs.append("cell %r shared by lines %d and %d" % (c, owner[c], k))
                owner[c] = k
    if prob.scenario == 2:
        for c in prob.popular:
            if c not in owner:
                errs.append("popular cell %r is on no route" % (c,))
    return errs


def render_grid(prob: Problem, routes: Optional[Sequence[Sequence[str]]] = None) -> str:
    """ASCII picture: digits = line index (1-based) on route cells, S/E marked, * popular.

    Cell text: e.g. 'S1', 'E1', '1', '1*' (route cell that is popular), '.', '*'.
    """
    cellw = 3
    txt: Dict[Cell, str] = {}
    if routes is not None:
        for k, moves in enumerate(routes):
            sx, sy, _, _ = prob.lines[k]
            for c in route_cells((sx, sy), moves):
                txt[c] = str(k + 1)
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):
        txt[(sx, sy)] = "S%d" % (k + 1)
        txt[(ex, ey)] = "E%d" % (k + 1)
    pop = set(prob.popular)
    rows = ["    " + "".join(("%d" % x).rjust(cellw) for x in range(prob.N))]
    for y in range(prob.M):
        row = []
        for x in range(prob.N):
            s = txt.get((x, y), ".")
            if (x, y) in pop:
                s = (s if s != "." else "") + "*"
            row.append(s.rjust(cellw))
        rows.append("%3d " % y + "".join(row))
    return "\n".join(rows)


# -------------------------------------------------------- exhaustive solver

def enumerate_routes(prob: Problem, k: int, blocked: FrozenSet[Cell] = frozenset(),
                     limit: int = 200000) -> List[str]:
    """All simple routes of line k with at most J turns avoiding `blocked` cells.

    Returns move strings (e.g. 'RRDD').  Raises RuntimeError if more than
    `limit` routes exist (instance too big for exhaustive treatment).
    """
    sx, sy, ex, ey = prob.lines[k]
    N, M, J = prob.N, prob.M, prob.J
    out: List[str] = []
    visited: Set[Cell] = {(sx, sy)}
    moves: List[str] = []

    def feasible(x: int, y: int, d: str, turns_left: int) -> bool:
        # Geometric pruning: with 0 turns left the end must lie straight ahead;
        # with 1 turn left it must not lie behind us.
        dx, dy = MOVES[d]
        if turns_left >= 2:
            return True
        ahead = (ex - x) * dx + (ey - y) * dy
        if turns_left == 1:
            return ahead >= 0
        return ahead >= 0 and ((dx != 0 and ey == y) or (dy != 0 and ex == x))

    def dfs(x: int, y: int, last: Optional[str], turns: int) -> None:
        if (x, y) == (ex, ey):
            out.append("".join(moves))
            if len(out) > limit:
                raise RuntimeError("route enumeration exceeded limit %d" % limit)
            return
        for d, (dx, dy) in MOVES.items():
            nx, ny = x + dx, y + dy
            if not (0 <= nx < N and 0 <= ny < M):
                continue
            if (nx, ny) in visited or (nx, ny) in blocked:
                continue
            nt = turns + (1 if last is not None and d != last else 0)
            if nt > J or not feasible(nx, ny, d, J - nt):
                continue
            visited.add((nx, ny))
            moves.append(d)
            dfs(nx, ny, d, nt)
            moves.pop()
            visited.discard((nx, ny))

    dfs(sx, sy, None, 0)
    return out


@dataclass
class BruteResult:
    status: str                      # 'SAT', 'UNSAT' or 'TOO_BIG'
    routes: Optional[List[str]]      # witness moves per line when SAT
    candidates: List[int]            # number of candidate routes per line
    nodes: int                       # search nodes explored
    note: str = ""


def brute_force(prob: Problem, node_budget: int = 2_000_000,
                route_limit: int = 200000) -> BruteResult:
    """Exhaustive reference solver for small instances.

    Enumerates every simple route with <= J turns per line (other lines'
    endpoints are blocked since cells cannot be shared), then searches for a
    pairwise cell-disjoint combination that, in scenario 2, covers all popular
    cells.  Independent of the CNF encoding.
    """
    ends = prob.endpoints()
    cand: List[List[Tuple[str, FrozenSet[Cell]]]] = []
    counts: List[int] = []
    try:
        for k in range(prob.K):
            sx, sy, ex, ey = prob.lines[k]
            blocked = frozenset(ends - {(sx, sy), (ex, ey)})
            rs = enumerate_routes(prob, k, blocked, limit=route_limit)
            cand.append([(r, frozenset(route_cells((sx, sy), r))) for r in rs])
            counts.append(len(rs))
    except RuntimeError as e:
        return BruteResult("TOO_BIG", None, counts, 0, str(e))
    for k, c in enumerate(cand):
        if not c:
            return BruteResult("UNSAT", None, counts, 0,
                               "line %d has no simple route with <= %d turns" % (k, prob.J))
    order = sorted(range(prob.K), key=lambda k: counts[k])
    popular = set(prob.popular)
    nodes = 0
    chosen: List[Optional[int]] = [None] * prob.K

    def rec(i: int, used: FrozenSet[Cell]) -> bool:
        nonlocal nodes
        if i == prob.K:
            return not popular or popular <= used
        k = order[i]
        for idx, (_, cells) in enumerate(cand[k]):
            nodes += 1
            if nodes > node_budget:
                raise RuntimeError("node budget exceeded")
            if used & cells:
                continue
            chosen[k] = idx
            if rec(i + 1, used | cells):
                return True
        chosen[k] = None
        return False

    try:
        ok = rec(0, frozenset())
    except RuntimeError as e:
        return BruteResult("TOO_BIG", None, counts, nodes, str(e))
    if ok:
        routes = [cand[k][chosen[k]][0] for k in range(prob.K)]  # type: ignore[index]
        return BruteResult("SAT", routes, counts, nodes)
    return BruteResult("UNSAT", None, counts, nodes,
                       "no cell-disjoint combination of candidate routes"
                       + (" covers all popular cells" if prob.scenario == 2 else ""))
