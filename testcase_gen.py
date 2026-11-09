#!/usr/bin/env python3
"""Reproducible test-case generator for the metro routing encoder.

Writes, into an output directory (default ./tests):

  <case>.city              instance in the SPEC.md format
  <case>.witness.metromap  a valid example answer (SAT cases only, move format)
  manifest.json            machine-readable expectations for every case
  CASES.txt                human-readable explanation of every case, with the
                           expected result, the reason / evidence and a picture

Two families of cases are produced:

  * hand-written small cases (fixed, independent of the seed) that can be
    checked by eye; they cover both scenarios, rectangular grids, several
    lines, popular cells and J = 0..3, with solvable and impossible variants;
  * seeded random "harder" cases: planted-solution SAT instances, UNSAT
    instances built from a structural argument (crossing, pigeonhole,
    unreachable popular cell), and unbiased random small instances whose
    answer is decided by the exhaustive reference solver.

Every expectation is backed by evidence that is independent of encoder.cpp:
SAT witnesses are validated by metro_common.check_solution, and every case
small enough is additionally decided by metro_common.brute_force. The
generator aborts if any of its own claims fails these checks.

Cases with J > 3 (tag "highJ") exercise the general-J encoding; a case can
still be flagged "future": true in the manifest to make TESTER.py skip it.

Usage:
  python3 testcase_gen.py [--out DIR] [--seed INT] [--brute-budget NODES] [--list]
"""
import argparse
import json
import os
import random
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

from metro_common import (Cell, Problem, brute_force, check_solution, format_city,
                          format_moves, render_grid, route_cells, validate_problem)

DEFAULT_SEED = 20240601


@dataclass
class Case:
    name: str
    prob: Problem
    expected: str                       # 'SAT' or 'UNSAT'
    reason: str
    witness: Optional[List[str]] = None  # move strings per line, SAT only
    tags: List[str] = field(default_factory=list)
    future: bool = False                 # needs J > 3 support (skipped by default)
    evidence: str = ""                   # filled in by self-check


def P(scenario: int, N: int, M: int, J: int, lines, popular=()) -> Problem:
    return Problem(scenario, N, M, len(lines), J, [tuple(l) for l in lines], [tuple(c) for c in popular])


# ===================================================================== hand cases

def hand_cases() -> List[Case]:
    c: List[Case] = []

    # ---------------------------------------------------------------- scenario 1
    c.append(Case("s1_j0_straight_row", P(1, 4, 1, 0, [(0, 0, 3, 0)]), "SAT",
                  "single row, J=0: the straight route R R R is the only route and it is fine.",
                  ["RRR"], ["hand", "s1", "j0", "one-row"]))
    c.append(Case("s1_j0_straight_col", P(1, 1, 4, 0, [(0, 0, 0, 3)]), "SAT",
                  "single column (N=1, M=4), J=0: D D D.",
                  ["DDD"], ["hand", "s1", "j0", "one-column"]))
    c.append(Case("s1_j0_unaligned", P(1, 3, 3, 0, [(0, 0, 2, 2)]), "UNSAT",
                  "J=0 allows only straight routes; (0,0) and (2,2) share neither a row nor a column.",
                  None, ["hand", "s1", "j0"]))
    c.append(Case("s1_j0_crossing", P(1, 3, 3, 0, [(0, 1, 2, 1), (1, 0, 1, 2)]), "UNSAT",
                  "with J=0 line 1 must use row 1 and line 2 must use column 1; both need cell (1,1).",
                  None, ["hand", "s1", "j0", "multi-line"]))
    c.append(Case("s1_j0_parallel", P(1, 6, 3, 0, [(0, 0, 5, 0), (1, 1, 3, 1), (5, 2, 0, 2)]), "SAT",
                  "three horizontal straight routes on three different rows (line 3 runs leftwards).",
                  ["RRRRR", "RR", "LLLLL"], ["hand", "s1", "j0", "multi-line", "rect"]))
    c.append(Case("s1_j1_bundled_input", P(1, 4, 3, 1, [(0, 0, 3, 2)]), "SAT",
                  "the bundled input.city: one L-shaped route, e.g. R R R D D (D D R R R also works).",
                  ["RRRDD"], ["hand", "s1", "j1", "rect"]))
    c.append(Case("s1_j1_two_lines", P(1, 4, 4, 1, [(0, 0, 3, 3), (0, 1, 2, 3)]), "SAT",
                  "line 1 goes along the top row then down the right column; line 2 goes down the "
                  "left column then right along the bottom row; the two L shapes do not touch.",
                  ["RRRDDD", "DDRR"], ["hand", "s1", "j1", "multi-line"]))
    c.append(Case("s1_j1_cross_unsat", P(1, 5, 4, 1, [(0, 1, 4, 1), (2, 0, 2, 2)]), "UNSAT",
                  "with J<=1 a route whose endpoints share a row (or column) can only be the straight "
                  "segment (an L shape would not end on that row); line 1 must occupy all of row 1 and "
                  "line 2 all of column 2 between rows 0 and 2, so both need (2,1).",
                  None, ["hand", "s1", "j1", "multi-line", "rect"]))
    c.append(Case("s1_j2_detour", P(1, 5, 4, 2, [(0, 1, 4, 1), (2, 0, 2, 2)]), "SAT",
                  "same instance with J=2: line 2 takes a U-shape R D D L around column 3 and line 1 "
                  "dips through row 3 (D D R R R R U U); each uses 2 turns.",
                  ["DDRRRRUU", "RDDL"], ["hand", "s1", "j2", "multi-line", "rect"]))
    c.append(Case("s1_j2_blocked_unsat", P(1, 4, 3, 2, [(0, 0, 2, 0), (2, 1, 1, 0)]), "UNSAT",
                  "line 1 (0,0)->(2,0): the straight route is blocked by line 2's end (1,0). Any route "
                  "with <=2 turns ending at (2,0) that is not straight must arrive vertically along "
                  "column 2, i.e. through (2,1), which is line 2's start. So line 1 needs 3 turns.",
                  None, ["hand", "s1", "j2", "multi-line", "rect"]))
    c.append(Case("s1_j3_detour", P(1, 4, 3, 3, [(0, 0, 2, 0), (2, 1, 1, 0)]), "SAT",
                  "same instance with J=3: line 1 goes D D R R R U U L around the outside (3 turns), "
                  "line 2 goes L U.",
                  ["DDRRRUUL", "LU"], ["hand", "s1", "j3", "multi-line", "rect"]))
    c.append(Case("s1_j3_pigeonhole", P(1, 5, 2, 3, [(0, 0, 4, 1), (0, 1, 4, 0)]), "UNSAT",
                  "any route from (0,0) to (4,1) uses at least 4+1+1 = 6 cells, likewise for "
                  "(0,1)->(4,0); 12 cells do not fit in a 5x2 grid of 10 cells, whatever J is.",
                  None, ["hand", "s1", "j3", "multi-line", "rect"]))
    c.append(Case("s1_j3_one_row_two_lines", P(1, 6, 1, 3, [(0, 0, 2, 0), (3, 0, 5, 0)]), "SAT",
                  "one row: R R and R R; J is irrelevant since no turn is possible.",
                  ["RR", "RR"], ["hand", "s1", "j3", "one-row", "multi-line"]))
    c.append(Case("s1_j3_one_row_overlap", P(1, 6, 1, 3, [(0, 0, 4, 0), (2, 0, 5, 0)]), "UNSAT",
                  "one row: line 1 must cover (0,0)..(4,0), which includes line 2's start (2,0).",
                  None, ["hand", "s1", "j3", "one-row", "multi-line"]))
    c.append(Case("s1_j2_three_lines_unsat", P(1, 5, 4, 2, [(2, 1, 0, 1), (3, 2, 1, 1), (4, 0, 1, 0)]),
                  "UNSAT",
                  "three interleaved lines on a 5x4 grid; with J<=2 no cell-disjoint combination "
                  "exists (exhaustive check; J=3 makes it solvable, see s1_j3_three_lines).",
                  None, ["hand", "s1", "j2", "multi-line", "rect"]))
    c.append(Case("s1_j3_three_lines", P(1, 5, 4, 3, [(2, 1, 0, 1), (3, 2, 1, 1), (4, 0, 1, 0)]), "SAT",
                  "line 1 loops R R D D L L L L U U (3 turns) below line 2 (L L U) while line 3 runs "
                  "along the top row.",
                  ["RRDDLLLLUU", "LLU", "LLL"], ["hand", "s1", "j3", "multi-line", "rect"]))

    # ---------------------------------------------------------------- scenario 2
    c.append(Case("s2_j0_popular_on_line", P(2, 3, 3, 0, [(0, 0, 2, 0)], [(1, 0)]), "SAT",
                  "the straight route R R passes through the popular cell (1,0).",
                  ["RR"], ["hand", "s2", "j0"]))
    c.append(Case("s2_j0_popular_off_line", P(2, 3, 3, 0, [(0, 0, 2, 0)], [(1, 1)]), "UNSAT",
                  "with J=0 the only route is the straight top row; popular cell (1,1) is not on it.",
                  None, ["hand", "s2", "j0", "unreachable-popular"]))
    c.append(Case("s2_j0_popular_is_endpoint", P(2, 4, 2, 0, [(0, 0, 3, 0), (0, 1, 3, 1)], [(0, 0), (3, 1)]),
                  "SAT", "popular cells coincide with a start and an end cell; two straight routes.",
                  ["RRR", "RRR"], ["hand", "s2", "j0", "multi-line", "rect"]))
    c.append(Case("s2_j1_one_of_two", P(2, 3, 2, 1, [(2, 0, 0, 1)], [(1, 0), (1, 1)]), "UNSAT",
                  "with J<=1 the only routes are L L D (covers (1,0) only) and D L L (covers (1,1) "
                  "only); each popular cell is reachable but not both at once.",
                  None, ["hand", "s2", "j1", "rect", "conflict"]))
    c.append(Case("s2_j2_one_of_two", P(2, 3, 2, 2, [(2, 0, 0, 1)], [(1, 0), (1, 1)]), "SAT",
                  "with J=2 the zig-zag L D L visits both (1,0) and (1,1).",
                  ["LDL"], ["hand", "s2", "j2", "rect"]))
    c.append(Case("s2_j1_unreachable", P(2, 5, 3, 1, [(0, 0, 4, 0)], [(2, 2)]), "UNSAT",
                  "endpoints share row 0, so with J<=1 the straight top row is the only route; "
                  "popular cell (2,2) is two rows below it.",
                  None, ["hand", "s2", "j1", "rect", "unreachable-popular"]))
    c.append(Case("s2_j2_dip", P(2, 5, 3, 2, [(0, 0, 4, 0)], [(2, 2)]), "SAT",
                  "with J=2 the route dips to row 2: D D R R R R U U.",
                  ["DDRRRRUU"], ["hand", "s2", "j2", "rect"]))
    c.append(Case("s2_j2_two_lines_share_duty", P(2, 4, 3, 2, [(0, 0, 3, 0), (0, 2, 3, 2)], [(1, 1), (2, 1)]),
                  "SAT", "line 1 dips through row 1 (D R R R U) and covers both popular cells; "
                  "line 2 stays straight on row 2.",
                  ["DRRRU", "RRR"], ["hand", "s2", "j2", "multi-line", "rect"]))
    c.append(Case("s2_j1_two_lines_unreachable", P(2, 4, 3, 1, [(0, 0, 3, 0), (0, 2, 3, 2)], [(1, 1), (2, 1)]),
                  "UNSAT", "same instance with J=1: both lines can only be straight (rows 0 and 2), "
                  "so the popular cells on row 1 are on no route.",
                  None, ["hand", "s2", "j1", "multi-line", "rect", "unreachable-popular"]))
    c.append(Case("s2_j2_conflict", P(2, 4, 2, 2, [(2, 0, 0, 0), (3, 1, 3, 0)], [(0, 1), (1, 0)]), "UNSAT",
                  "line 1 (2,0)->(0,0) with <=2 turns is either L L (covers (1,0), not (0,1)) or "
                  "D L L U (covers (0,1), not (1,0)); line 2 (3,1)->(3,0) cannot reach either popular "
                  "cell without passing through line 1's start (2,0) or its cells. Needs J=3.",
                  None, ["hand", "s2", "j2", "multi-line", "rect", "conflict"]))
    c.append(Case("s2_j3_conflict_resolved", P(2, 4, 2, 3, [(2, 0, 0, 0), (3, 1, 3, 0)], [(0, 1), (1, 0)]),
                  "SAT", "with J=3 line 1 zig-zags L D L U through both popular cells; line 2 is U.",
                  ["LDLU", "U"], ["hand", "s2", "j3", "multi-line", "rect"]))
    c.append(Case("s2_j2_needs_three_turns", P(2, 3, 3, 2, [(1, 1, 2, 1)], [(0, 1)]), "UNSAT",
                  "popular (0,1) is left of the start while the end (2,1) is to the right on the same "
                  "row: the route must go L, turn vertically, turn back R, and turn again to return "
                  "to row 1 at column 2 -- three turns.",
                  None, ["hand", "s2", "j2"]))
    c.append(Case("s2_j3_three_turns", P(2, 3, 3, 3, [(1, 1, 2, 1)], [(0, 1)]), "SAT",
                  "with J=3: L U R R D (or L D R R U).",
                  ["LURRD"], ["hand", "s2", "j3"]))
    c.append(Case("s2_j3_three_lines", P(2, 6, 4, 3,
                                         [(0, 0, 2, 3), (1, 0, 3, 2), (1, 1, 3, 1)],
                                         [(0, 2), (4, 1), (2, 2), (3, 1)]), "SAT",
                  "line 1: D D D R R; line 2: R R R D D L around the right; line 3: D R U R "
                  "(3 turns) in the middle. Popular cells: (0,2) on line 1, (4,1) on line 2, "
                  "(2,2) on line 3, (3,1) is line 3's end.",
                  ["DDDRR", "RRRDDL", "DRUR"], ["hand", "s2", "j3", "multi-line", "rect"]))
    c.append(Case("s2_j3_needs_four_turns", P(2, 4, 2, 3, [(0, 0, 2, 1), (3, 0, 3, 1)], [(1, 0), (0, 1)]),
                  "UNSAT", "line 1 must visit (1,0) and (0,1), which are on different sides of its "
                  "start (0,0); visiting both and still ending at (2,1) takes 4 turns "
                  "(D R U R D); line 2 (3,0)->(3,1) cannot help without crossing line 1. Exhaustive "
                  "check confirms no combination with <=3 turns.",
                  None, ["hand", "s2", "j3", "multi-line", "rect", "conflict"]))

    c.append(Case("s1_j3_needs_four_turns", P(1, 4, 4, 3, [(3, 2, 2, 1), (3, 3, 0, 1), (1, 3, 0, 2)]), "UNSAT",
                  "line 2 (3,3)->(0,1): its start's only free neighbour is (2,3) (since (3,2) is "
                  "line 1's start); from there (1,3) is line 3's start so it must go up to (2,2); "
                  "(2,1) is line 1's end so it goes left to (1,2); (0,2) is line 3's end so it goes "
                  "up to (1,1) and finally left to (0,1): the staircase L U L U L has 4 turns, and "
                  "every other continuation also needs more than 3 turns.",
                  None, ["hand", "s1", "j3", "multi-line", "conflict"]))

    # ------------------------------------------------------ J above three
    c.append(Case("s2_j4_zigzag", P(2, 4, 2, 4, [(0, 0, 2, 1), (3, 0, 3, 1)], [(1, 0), (0, 1)]),
                  "SAT", "same instance as s2_j3_needs_four_turns with J=4: line 1 D R U R D (4 turns), "
                  "line 2 D.",
                  ["DRURD", "D"], ["hand", "s2", "j4", "multi-line", "rect", "highJ"]))
    c.append(Case("s1_j4_staircase", P(1, 4, 4, 4, [(3, 2, 2, 1), (3, 3, 0, 1), (1, 3, 0, 2)]), "SAT",
                  "same instance as s1_j3_needs_four_turns with J=4: line 2 takes the staircase "
                  "L U L U L (4 turns); lines 1 and 3 are U L and L U.",
                  ["UL", "LULUL", "LU"], ["hand", "s1", "j4", "multi-line", "highJ"]))
    corridor = [(0, 0, 6, 0), (1, 0, 1, 1), (3, 1, 3, 2), (5, 0, 5, 1)]
    c.append(Case("s1_j5_corridor_unsat", P(1, 7, 3, 5, corridor), "UNSAT",
                  "lines 2-4 are two-cell walls: column 1 is blocked in rows 0-1, column 3 in rows "
                  "1-2, column 5 in rows 0-1. Line 1 (0,0)->(6,0) must pass column 1 on row 2, "
                  "column 3 on row 0 and column 5 on row 2, then climb back to row 0: seven "
                  "straight segments (D R U R D R U), i.e. six turns, so J=5 is impossible.",
                  None, ["hand", "s1", "j5", "multi-line", "rect", "highJ"]))
    c.append(Case("s1_j6_corridor", P(1, 7, 3, 6, corridor), "SAT",
                  "same walls with J=6: line 1 snakes D D R R U U R R D D R R U U (6 turns); the "
                  "walls are single D moves.",
                  ["DDRRUURRDDRRUU", "D", "D", "D"], ["hand", "s1", "j6", "multi-line", "rect", "highJ"]))
    c.append(Case("s2_j4_detour_unsat", P(2, 5, 4, 4, [(1, 2, 3, 2)], [(4, 1), (1, 2), (0, 3)]), "UNSAT",
                  "one line (1,2)->(3,2) must visit (0,3) (below-left of the start) and (4,1) "
                  "(above-right of the end): exhaustive check shows no simple route with <= 4 turns.",
                  None, ["hand", "s2", "j4", "rect", "highJ"]))
    c.append(Case("s2_j5_detour", P(2, 5, 4, 5, [(1, 2, 3, 2)], [(4, 1), (1, 2), (0, 3)]), "SAT",
                  "with J=5: L D R R R R U U L D (5 turns) visits (0,3), climbs column 4 through "
                  "(4,1) and comes back down to (3,2).",
                  ["LDRRRRUULD"], ["hand", "s2", "j5", "rect", "highJ"]))
    c.append(Case("s2_j5_loop_unsat", P(2, 5, 4, 5, [(1, 0, 0, 2)], [(0, 0), (3, 0)]), "UNSAT",
                  "one line (1,0)->(0,2) must visit (0,0) (left of the start) and (3,0) (right of it) "
                  "on the top row without revisiting (1,0): exhaustive check shows at least 6 turns.",
                  None, ["hand", "s2", "j5", "rect", "highJ"]))
    c.append(Case("s2_j6_loop", P(2, 5, 4, 6, [(1, 0, 0, 2)], [(0, 0), (3, 0)]), "SAT",
                  "with J=6: L D R R R U R D D L L L L (6 turns): step to (0,0), drop to row 1, run "
                  "right, climb to (3,0), and return along row 2/3 to (0,2).",
                  ["LDRRRURDDLLLL"], ["hand", "s2", "j6", "rect", "highJ"]))
    c.append(Case("s1_j9_one_row", P(1, 6, 1, 9, [(0, 0, 2, 0), (3, 0, 5, 0)]), "SAT",
                  "a large J on a single row changes nothing: R R and R R.",
                  ["RR", "RR"], ["hand", "s1", "j9", "one-row", "multi-line", "highJ"]))
    return c


# ================================================================== random cases

PERP = {"L": "UD", "R": "UD", "U": "LR", "D": "LR"}


def plant_routes(rng: random.Random, N: int, M: int, K: int, J: int,
                 reserved: Set[Cell], min_len: int = 3, tries: int = 400
                 ) -> Tuple[List[Tuple[int, int, int, int]], List[str]]:
    """Plant up to K pairwise disjoint simple routes with <= J turns.

    Returns (lines, witness moves). May return fewer than K lines if the grid
    fills up; callers must use len(lines).
    """
    used: Set[Cell] = set(reserved)
    lines: List[Tuple[int, int, int, int]] = []
    routes: List[str] = []
    for _ in range(K):
        for _attempt in range(tries):
            sx, sy = rng.randrange(N), rng.randrange(M)
            if (sx, sy) in used:
                continue
            turns_target = rng.randint(0, J)
            d = rng.choice("LRUD")
            cells = [(sx, sy)]
            moves: List[str] = []
            for seg in range(turns_target + 1):
                if seg > 0:
                    d = rng.choice(PERP[d])
                seg_len = rng.randint(1, max(N, M))
                for _ in range(seg_len):
                    x, y = cells[-1]
                    dx, dy = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[d]
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < N and 0 <= ny < M) or (nx, ny) in used or (nx, ny) in cells:
                        break
                    cells.append((nx, ny))
                    moves.append(d)
            if len(cells) < min_len:
                continue
            ex, ey = cells[-1]
            lines.append((sx, sy, ex, ey))
            routes.append("".join(moves))
            used.update(cells)
            break
    return lines, routes


def pick_popular(rng: random.Random, routes_cells: List[List[Cell]], count: int) -> List[Cell]:
    pool = sorted({c for cells in routes_cells for c in cells})
    return rng.sample(pool, min(count, len(pool)))


def random_cases(rng: random.Random) -> List[Case]:
    c: List[Case] = []
    sizes = [(8, 5), (9, 7), (10, 6), (12, 8), (7, 9), (11, 11), (14, 9)]

    # --- planted SAT instances: both scenarios, every J -------------------
    idx = 0
    for scenario in (1, 2):
        for J in range(4):
            N, M = sizes[idx % len(sizes)]
            idx += 1
            K = rng.randint(3, 6)
            lines, routes = plant_routes(rng, N, M, K, J, set())
            cells = [route_cells((l[0], l[1]), r) for l, r in zip(lines, routes)]
            pop = pick_popular(rng, cells, rng.randint(2, 5)) if scenario == 2 else []
            prob = P(scenario, N, M, J, lines, pop)
            c.append(Case("rnd_s%d_j%d_planted" % (scenario, J), prob, "SAT",
                          "routes were planted first (pairwise disjoint, <= J turns) and the endpoints"
                          + (" and popular cells" if scenario == 2 else "")
                          + " were derived from them; the witness is the planted solution.",
                          routes, ["random", "planted", "s%d" % scenario, "j%d" % J, "multi-line"]))

    # --- UNSAT by crossing: a left-to-right line and a top-to-bottom line ---
    for scenario in (1, 2):
        for J in range(4):
            N, M = sizes[(idx + 2) % len(sizes)]
            idx += 1
            ya, yb = rng.randrange(M), rng.randrange(M)
            xa, xb = rng.randrange(N), rng.randrange(N)
            if J == 0:  # keep the straight routes possible, so crossing is the only obstacle
                yb, xb = ya, xa
            cross = [(0, ya, N - 1, yb), (xa, 0, xb, M - 1)]
            reserved = {(0, ya), (N - 1, yb), (xa, 0), (xb, M - 1)}
            if len(reserved) < 4:
                # corner collision; shift
                ya = (ya + 1) % M
                cross = [(0, ya, N - 1, yb), (xa, 0, xb, M - 1)]
                reserved = {(0, ya), (N - 1, yb), (xa, 0), (xb, M - 1)}
            extra, extra_routes = plant_routes(rng, N, M, rng.randint(1, 3), J, reserved)
            lines = cross + extra
            cells = [route_cells((l[0], l[1]), r) for l, r in zip(extra, extra_routes)]
            pop = pick_popular(rng, cells, rng.randint(1, 3)) if scenario == 2 else []
            prob = P(scenario, N, M, J, lines, pop)
            c.append(Case("rnd_s%d_j%d_crossing" % (scenario, J), prob, "UNSAT",
                          "line 1 joins the left edge (x=0) to the right edge (x=N-1) and line 2 joins "
                          "the top edge (y=0) to the bottom edge (y=M-1). Two cell-disjoint orthogonal "
                          "paths cannot do both in a rectangular grid (the left-right path separates "
                          "the top edge from the bottom edge), so the instance is impossible for any J. "
                          "The remaining lines are routable on their own.",
                          None, ["random", "crossing", "s%d" % scenario, "j%d" % J, "multi-line"]))

    # --- UNSAT by pigeonhole: minimal route lengths exceed the grid ---------
    for i, (scenario, J) in enumerate([(1, 3), (2, 2)]):
        N, M = rng.choice([(6, 2), (7, 3), (5, 3)])
        lines = []
        total = 0
        corners = [(0, 0, N - 1, M - 1), (0, M - 1, N - 1, 0)]
        for l in corners:
            lines.append(l)
            total += abs(l[2] - l[0]) + abs(l[3] - l[1]) + 1
        # add lines until the bound is exceeded
        free = [(x, y) for x in range(N) for y in range(M) if (x, y) not in Problem(1, N, M, 2, J, lines).endpoints()]
        while total <= N * M and len(free) >= 2:
            a = rng.choice(free); free.remove(a)
            b = max(free, key=lambda q: abs(q[0] - a[0]) + abs(q[1] - a[1])); free.remove(b)
            lines.append((a[0], a[1], b[0], b[1]))
            total += abs(b[0] - a[0]) + abs(b[1] - a[1]) + 1
        pop = [rng.choice(free)] if (scenario == 2 and free) else []
        prob = P(scenario, N, M, J, lines, pop)
        c.append(Case("rnd_s%d_j%d_pigeonhole" % (scenario, J), prob, "UNSAT",
                      "every route from (sx,sy) to (ex,ey) uses at least |ex-sx|+|ey-sy|+1 cells; the "
                      "sum over all lines is %d, more than the %d cells of the grid, so the routes "
                      "cannot be cell-disjoint for any J." % (total, N * M),
                      None, ["random", "pigeonhole", "s%d" % scenario, "j%d" % J, "multi-line"]))

    # --- UNSAT scenario 2: popular cell no route with <= J turns can reach --
    for J in (0, 1, 2):
        N, M = (9, 6) if J != 0 else (7, 5)
        lines, routes = plant_routes(rng, N, M, rng.randint(2, 3), J, set())
        # keep a corner-ish region free of all bounding boxes
        boxes = [(min(l[0], l[2]), max(l[0], l[2]), min(l[1], l[3]), max(l[1], l[3])) for l in lines]
        cand = []
        for x in range(N):
            for y in range(M):
                if all(not (x0 <= x <= x1) and not (y0 <= y <= y1) for x0, x1, y0, y1 in boxes):
                    cand.append((x, y))
        if not cand:
            # shrink: drop lines until a diagonal-outside cell exists
            while lines and not cand:
                lines.pop(); routes.pop()
                boxes.pop()
                cand = [(x, y) for x in range(N) for y in range(M)
                        if all(not (x0 <= x <= x1) and not (y0 <= y <= y1) for x0, x1, y0, y1 in boxes)]
        bad = rng.choice(cand)
        cells = [route_cells((l[0], l[1]), r) for l, r in zip(lines, routes)]
        pop = pick_popular(rng, cells, 2) + [bad]
        prob = P(2, N, M, J, lines, pop)
        if J == 0:
            why = "with J=0 every route is a straight segment between its endpoints"
        elif J == 1:
            why = "with J<=1 every route stays inside the bounding box of its endpoints"
        else:
            why = ("with J<=2 a route lies on the two rows of its endpoints plus one column between "
                   "them (H-V-H), or on the two columns plus one row between them (V-H-V); a cell "
                   "whose row and column are both outside the endpoint ranges is never visited")
        c.append(Case("rnd_s2_j%d_popular_unreachable" % J, prob, "UNSAT",
                      "popular cell %r is in row and column ranges outside every line's endpoint box; "
                      "%s. The other popular cells lie on planted routes." % (bad, why),
                      None, ["random", "unreachable-popular", "s2", "j%d" % J, "multi-line"]))

    # --- J above three: planted SAT and argument-based UNSAT ----------------
    for scenario, J in ((1, 5), (2, 5), (1, 7), (2, 7)):
        N, M = sizes[idx % len(sizes)]
        idx += 1
        lines, routes = plant_routes(rng, N, M, rng.randint(3, 5), J, set())
        cells = [route_cells((l[0], l[1]), r) for l, r in zip(lines, routes)]
        pop = pick_popular(rng, cells, rng.randint(2, 5)) if scenario == 2 else []
        c.append(Case("rnd_s%d_j%d_planted" % (scenario, J), P(scenario, N, M, J, lines, pop), "SAT",
                      "routes with up to %d turns were planted first (pairwise disjoint) and the "
                      "endpoints%s were derived from them." % (J, " and popular cells" if scenario == 2 else ""),
                      routes, ["random", "planted", "s%d" % scenario, "j%d" % J, "multi-line", "highJ"]))
    for scenario, J in ((1, 6), (2, 6)):
        N, M = sizes[idx % len(sizes)]
        idx += 1
        ya, yb, xa, xb = rng.randrange(M), rng.randrange(M), rng.randrange(N), rng.randrange(N)
        cross = [(0, ya, N - 1, yb), (xa, 0, xb, M - 1)]
        reserved = {(0, ya), (N - 1, yb), (xa, 0), (xb, M - 1)}
        if len(reserved) < 4:
            ya = (ya + 1) % M
            cross = [(0, ya, N - 1, yb), (xa, 0, xb, M - 1)]
            reserved = {(0, ya), (N - 1, yb), (xa, 0), (xb, M - 1)}
        extra, extra_routes = plant_routes(rng, N, M, rng.randint(1, 3), J, reserved)
        cells = [route_cells((l[0], l[1]), r) for l, r in zip(extra, extra_routes)]
        pop = pick_popular(rng, cells, rng.randint(1, 3)) if scenario == 2 else []
        c.append(Case("rnd_s%d_j%d_crossing" % (scenario, J), P(scenario, N, M, J, cross + extra, pop), "UNSAT",
                      "line 1 joins the left and right edges, line 2 the top and bottom edges; two "
                      "cell-disjoint orthogonal paths cannot do both, whatever J is.",
                      None, ["random", "crossing", "s%d" % scenario, "j%d" % J, "multi-line", "highJ"]))
    c.append(Case("rnd_s1_j10_pigeonhole", P(1, 6, 2, 10, [(0, 0, 5, 1), (0, 1, 5, 0)]), "UNSAT",
                  "each route needs at least 7 cells, 14 > 12 cells in the grid, for any J.",
                  None, ["random", "pigeonhole", "s1", "j10", "multi-line", "highJ"]))

    # --- unbiased random small instances decided by the exhaustive solver --
    want = {(s, J, e): 1 for s in (1, 2) for J in (1, 2, 3) for e in ("SAT", "UNSAT")}
    got = {k: 0 for k in want}
    attempts = 0
    while any(got[k] < want[k] for k in want) and attempts < 20000:
        attempts += 1
        scenario = rng.choice((1, 2))
        N, M = rng.choice([(5, 4), (6, 4), (6, 5), (4, 6), (7, 4)])
        K = rng.randint(2, 4)
        J = rng.randint(1, 3)
        cells = [(x, y) for x in range(N) for y in range(M)]
        pts = rng.sample(cells, 2 * K)
        lines = [(pts[2 * k][0], pts[2 * k][1], pts[2 * k + 1][0], pts[2 * k + 1][1]) for k in range(K)]
        pop = rng.sample(cells, rng.randint(1, 3)) if scenario == 2 else []
        prob = P(scenario, N, M, J, lines, pop)
        res = brute_force(prob, node_budget=300000)
        key = (scenario, J, res.status)
        if res.status == "TOO_BIG" or got[key] >= want[key]:
            continue
        got[key] += 1
        c.append(Case("rnd_s%d_j%d_exhaustive_%s" % (scenario, J, res.status.lower()),
                      prob, res.status,
                      "random endpoints%s; the answer was decided by the exhaustive reference solver "
                      "(all simple routes with <= J turns per line, all disjoint combinations)."
                      % (" and popular cells" if scenario == 2 else ""),
                      res.routes, ["random", "exhaustive", "s%d" % scenario, "j%d" % J, "multi-line"]))
    return c


# ===================================================================== self-check

def self_check(case: Case, brute_budget: int) -> None:
    """Validate the case's own claims with encoder-independent tools; raise on failure."""
    prob = case.prob
    errs = validate_problem(prob)
    if errs:
        raise SystemExit("case %s: invalid instance: %s" % (case.name, errs))
    if case.expected == "SAT" and case.witness is not None:
        errs = check_solution(prob, [list(r) for r in case.witness])
        if errs:
            raise SystemExit("case %s: witness invalid: %s" % (case.name, errs))
    ev = []
    if case.witness is not None:
        ev.append("witness verified by check_solution")
    if brute_budget > 0:
        res = brute_force(prob, node_budget=brute_budget)
        if res.status == "TOO_BIG":
            ev.append("exhaustive check skipped (too big: %s)" % res.note)
        else:
            if res.status != case.expected:
                raise SystemExit("case %s: expected %s but exhaustive solver says %s (%s)"
                                 % (case.name, case.expected, res.status, res.note))
            ev.append("exhaustive check agrees (candidate routes per line %s, %d search nodes)"
                      % (res.candidates, res.nodes))
            if case.expected == "SAT" and case.witness is None:
                case.witness = res.routes
                ev.append("witness taken from exhaustive solver")
    if case.expected == "SAT" and case.witness is None:
        raise SystemExit("case %s: SAT case without witness" % case.name)
    case.evidence = "; ".join(ev) if ev else "argument only"


# ========================================================================= output

def write_cases(cases: List[Case], out_dir: str, seed: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    # remove outputs of cases that no longer exist (e.g. renamed cases)
    keep = {c.name for c in cases}
    for fn in os.listdir(out_dir):
        stem = fn.split(".", 1)[0]
        if "." in fn and stem not in keep and stem not in ("manifest", "CASES", "index"):
            os.remove(os.path.join(out_dir, fn))
    manifest = {"seed": seed, "cases": []}
    doc = ["Metro routing test cases (generated by testcase_gen.py, seed %d)" % seed,
           "Coordinates are (x,y): x = column from the left, y = row from the top.",
           "Pictures: S#/E# = start/end of line #, digits = witness route cells, * = popular cell.",
           ""]
    for case in cases:
        prob = case.prob
        city = format_city(prob)
        with open(os.path.join(out_dir, case.name + ".city"), "w") as f:
            f.write(city)
        witness_rows = None
        if case.witness is not None:
            witness_rows = [format_moves(r) for r in case.witness]
            with open(os.path.join(out_dir, case.name + ".witness.metromap"), "w") as f:
                f.write("\n".join(witness_rows) + "\n")
        manifest["cases"].append({
            "name": case.name, "scenario": prob.scenario, "N": prob.N, "M": prob.M,
            "K": prob.K, "J": prob.J, "P": prob.P, "expected": case.expected,
            "witness": witness_rows, "reason": case.reason, "evidence": case.evidence,
            "tags": case.tags, "future": case.future,
        })
        doc.append("=" * 78)
        doc.append("%s%s" % (case.name, "   [FUTURE: needs J>3 support]" if case.future else ""))
        doc.append("-" * 78)
        doc.append("%s.city:" % case.name)
        doc.extend("    " + ln for ln in city.rstrip("\n").split("\n"))
        doc.append("expected: %s" % case.expected)
        doc.append("reason:   %s" % case.reason)
        doc.append("evidence: %s" % case.evidence)
        if witness_rows:
            doc.append("witness (%s.witness.metromap):" % case.name)
            doc.extend("    " + r for r in witness_rows)
        doc.append("picture:")
        doc.extend("    " + ln for ln in render_grid(prob, case.witness).split("\n"))
        doc.append("")
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(out_dir, "CASES.txt"), "w") as f:
        f.write("\n".join(doc) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="tests", help="output directory (default: tests)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default %d)" % DEFAULT_SEED)
    ap.add_argument("--brute-budget", type=int, default=400000,
                    help="search-node budget for the exhaustive self-check, 0 disables it")
    ap.add_argument("--list", action="store_true", help="only list the cases, write nothing")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    cases = hand_cases() + random_cases(rng)
    names = [c.name for c in cases]
    if len(set(names)) != len(names):
        raise SystemExit("duplicate case names")
    for case in cases:
        self_check(case, args.brute_budget)

    # coverage check: every (scenario, J, expected) combination at least once
    combos = {(c.prob.scenario, c.prob.J, c.expected) for c in cases if not c.future}
    missing = [(s, j, e) for s in (1, 2) for j in range(4) for e in ("SAT", "UNSAT") if (s, j, e) not in combos]
    high = {(c.prob.scenario, c.expected) for c in cases if c.prob.J > 3}
    missing += [(s, ">3", e) for s in (1, 2) for e in ("SAT", "UNSAT") if (s, e) not in high]
    if missing:
        raise SystemExit("coverage gap: %s" % missing)

    if args.list:
        for case in cases:
            p = case.prob
            print("%-36s s%d %2dx%-2d K=%d J=%d P=%d  %-5s  %s" % (
                case.name, p.scenario, p.N, p.M, p.K, p.J, p.P, case.expected, case.evidence))
        return 0
    write_cases(cases, args.out, args.seed)
    print("wrote %d cases to %s/ (manifest.json, CASES.txt, *.city, *.witness.metromap)"
          % (len(cases), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
