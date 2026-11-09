#!/usr/bin/env python3
"""Standalone verifier for decoded metro routes.

    python3 format_checker.py <basename>                 # <basename>.city + <basename>.metromap
    python3 format_checker.py --city A.city --metromap B.metromap

Uses ONLY the .city instance and the .metromap answer (SPEC.md formats); it
never looks at the CNF, the solver output or the decoder. Checks:

  * exactly K route rows, each a sequence of L/R/U/D moves terminated by 0
  * every move stays inside the N x M grid
  * route k starts at line k's start cell (implicit in the move format) and
    ends exactly at line k's end cell
  * no route visits a cell twice
  * no cell is used by two different lines (including other lines' endpoints)
  * each route changes direction at most J times
  * scenario 2: every popular cell lies on some route

Result line and exit status:
  VALID        0   the answer is a correct witness
  INVALID      1   one or more violations, each listed with the .metromap line
  NO_WITNESS   3   the answer is the single "0" line (an UNSAT claim); there is
                   nothing to verify and this is NOT proof that the instance
                   is unsolvable
  MALFORMED    2   a file is missing or cannot be parsed (also usage errors)
"""
import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

from metro_common import Problem, parse_city, validate_problem

Cell = Tuple[int, int]
MOVES: Dict[str, Cell] = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}


class Malformed(Exception):
    pass


def read_metromap(path: str) -> Tuple[Optional[List[Tuple[int, List[str]]]], List[str]]:
    """Return (routes, problems). routes is None for the UNSAT-style single '0'.

    Each route is (metromap line number, list of move tokens) -- tokens are
    returned unvalidated so that bad moves are reported as violations, not as
    a parse failure of the whole file.
    """
    try:
        with open(path) as f:
            raw = f.read()
    except OSError as e:
        raise Malformed("cannot read %s: %s" % (path, e))
    rows: List[Tuple[int, List[str]]] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        toks = line.split()
        if toks:
            rows.append((lineno, toks))
    if not rows:
        raise Malformed("%s is empty" % path)
    if len(rows) == 1 and rows[0][1] == ["0"]:
        return None, []
    problems: List[str] = []
    routes: List[Tuple[int, List[str]]] = []
    for lineno, toks in rows:
        if toks[-1] != "0":
            problems.append("metromap line %d: row does not end with the terminating 0" % lineno)
            routes.append((lineno, toks))
        else:
            routes.append((lineno, toks[:-1]))
    return routes, problems


def verify(prob: Problem, routes: List[Tuple[int, List[str]]]) -> Tuple[List[str], List[int]]:
    """Return (problems, turns per route). Empty problems means VALID."""
    problems: List[str] = []
    K, N, M, J = prob.K, prob.N, prob.M, prob.J

    if len(routes) != K:
        problems.append("expected exactly K=%d route rows (one per metro line, in input order), found %d"
                        % (K, len(routes)))
    # Cells already claimed: every line's endpoints belong to that line.
    owner: Dict[Cell, Tuple[int, str]] = {}
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):
        owner[(sx, sy)] = (k, "start of metro line %d" % (k + 1))
        owner[(ex, ey)] = (k, "end of metro line %d" % (k + 1))

    turns_per_route: List[int] = []
    for idx, (lineno, toks) in enumerate(routes):
        tag = "metromap line %d (metro line %d)" % (lineno, idx + 1)
        if idx >= K:
            problems.append("%s: extra row beyond the K=%d metro lines" % (tag, K))
            continue
        sx, sy, ex, ey = prob.lines[idx]
        x, y = sx, sy
        cells: List[Cell] = [(x, y)]
        visited = {(x, y)}
        last: Optional[str] = None
        turns = 0
        broken = False
        for step, mv in enumerate(toks, 1):
            if mv not in MOVES:
                problems.append("%s: move %d is '%s', expected one of L R U D" % (tag, step, mv))
                broken = True
                break
            if last is not None and mv != last:
                turns += 1
            last = mv
            dx, dy = MOVES[mv]
            x, y = x + dx, y + dy
            if not (0 <= x < N and 0 <= y < M):
                problems.append("%s: move %d '%s' leaves the %dx%d grid at (%d,%d)"
                                % (tag, step, mv, N, M, x, y))
                broken = True
                break
            if (x, y) in visited:
                problems.append("%s: move %d '%s' revisits cell (%d,%d); routes must be simple paths"
                                % (tag, step, mv, x, y))
            visited.add((x, y))
            cells.append((x, y))
        turns_per_route.append(turns)
        if not toks:
            problems.append("%s: empty route; the start (%d,%d) and end (%d,%d) are different cells"
                            % (tag, sx, sy, ex, ey))
        if not broken and cells[-1] != (ex, ey):
            problems.append("%s: route from start (%d,%d) ends at (%d,%d) but the end cell is (%d,%d)"
                            % (tag, sx, sy, cells[-1][0], cells[-1][1], ex, ey))
        if turns > J:
            problems.append("%s: %d direction changes exceed the limit J=%d" % (tag, turns, J))
        for c in cells:
            if c in owner and owner[c][0] != idx:
                problems.append("%s: cell (%d,%d) is also used by metro line %d (%s); lines may not share cells"
                                % (tag, c[0], c[1], owner[c][0] + 1, owner[c][1]))
            elif c not in owner:
                owner[c] = (idx, "route of metro line %d" % (idx + 1))

    if prob.scenario == 2:
        for px, py in prob.popular:
            if (px, py) not in owner:
                problems.append("popular cell (%d,%d) is not on any route" % (px, py))
    return problems, turns_per_route


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("basename", nargs="?", help="use <basename>.city and <basename>.metromap")
    ap.add_argument("--city")
    ap.add_argument("--metromap")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only the result line")
    args = ap.parse_args(argv)
    if args.basename:
        city, metromap = args.basename + ".city", args.basename + ".metromap"
    elif args.city and args.metromap:
        city, metromap = args.city, args.metromap
    else:
        ap.error("give a basename or both --city and --metromap")

    try:
        if not os.path.exists(city):
            raise Malformed("%s does not exist" % city)
        with open(city) as f:
            try:
                prob = parse_city(f.read())
            except ValueError as e:
                raise Malformed("%s: %s" % (city, e))
        errs = validate_problem(prob)
        if errs:
            raise Malformed("%s: invalid instance: %s" % (city, "; ".join(errs)))
        routes, problems = read_metromap(metromap)
    except Malformed as e:
        print("MALFORMED: %s" % e)
        return 2

    if routes is None:
        print("NO_WITNESS: %s is the single '0' line (UNSAT claim); there are no routes to verify. "
              "This does not prove that %s is unsolvable." % (metromap, city))
        return 3

    more, turns = verify(prob, routes)
    problems += more
    if problems:
        print("INVALID: %d problem(s) in %s against %s" % (len(problems), metromap, city))
        if not args.quiet:
            for p in problems:
                print("  - " + p)
        return 1
    print("VALID: %d route(s) in %s satisfy %s (turns per line %s, J=%d%s)"
          % (prob.K, metromap, city, turns, prob.J,
             ", all %d popular cells covered" % prob.P if prob.scenario == 2 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
