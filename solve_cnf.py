#!/usr/bin/env python3
"""Stand-in for the `minisat` binary using the MiniSat 2.2 core bundled in python-sat.

    python3 solve_cnf.py <input.satinput> <output.satoutput> [--engine NAME]

Mimics MiniSat's command-line conventions so the rest of the pipeline does not
care which one is used:
  * result file: "SAT" followed by a line of signed literals ending in 0,
    or "UNSAT";
  * exit status 10 for SAT, 20 for UNSAT;
  * any other exit status (1 here) means the solver did NOT decide the
    instance (missing file, DIMACS parse error, missing pysat, ...). Callers
    must never treat that as UNSAT.

Requires: pip install python-sat
"""
import argparse
import sys


def parse_dimacs(path):
    """Return (num_vars, num_clauses_declared, clauses). Strict about the header."""
    header = None
    clauses = []
    cur = []
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                if header is not None:
                    raise ValueError("line %d: duplicate header" % lineno)
                toks = line.split()
                if len(toks) != 4 or toks[1] != "cnf":
                    raise ValueError("line %d: bad header %r" % (lineno, line))
                header = (int(toks[2]), int(toks[3]))
                continue
            if header is None:
                raise ValueError("line %d: clause before header" % lineno)
            for tok in line.split():
                lit = int(tok)
                if lit == 0:
                    clauses.append(cur)
                    cur = []
                else:
                    if abs(lit) > header[0]:
                        raise ValueError("line %d: literal %d exceeds declared %d variables"
                                         % (lineno, lit, header[0]))
                    cur.append(lit)
    if cur:
        raise ValueError("last clause not terminated by 0")
    if header is None:
        raise ValueError("no 'p cnf' header")
    return header[0], header[1], clauses


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--engine", default="minisat22",
                    help="pysat solver name (default minisat22; e.g. glucose3, cadical153)")
    args = ap.parse_args(argv)

    try:
        from pysat.solvers import Solver
    except ImportError:
        print("solve_cnf.py: python-sat is not installed (pip install python-sat)", file=sys.stderr)
        return 1
    try:
        nvars, ndecl, clauses = parse_dimacs(args.input)
    except (OSError, ValueError) as e:
        print("solve_cnf.py: cannot read %s: %s" % (args.input, e), file=sys.stderr)
        return 1
    if ndecl != len(clauses):
        # MiniSat itself only warns here; we do the same but make it visible.
        print("solve_cnf.py: WARNING header declares %d clauses, file has %d" % (ndecl, len(clauses)),
              file=sys.stderr)

    with Solver(name=args.engine, bootstrap_with=clauses) as s:
        sat = s.solve()
        model = s.get_model() if sat else None

    try:
        with open(args.output, "w") as f:
            if sat:
                lits = list(model) if model else []
                # pysat may omit unconstrained trailing variables; pad so every
                # declared variable is assigned, as MiniSat does.
                have = {abs(l) for l in lits}
                lits.extend(-v for v in range(1, nvars + 1) if v not in have)
                lits.sort(key=abs)
                f.write("SAT\n" + " ".join(str(l) for l in lits) + " 0\n")
            else:
                f.write("UNSAT\n")
    except OSError as e:
        print("solve_cnf.py: cannot write %s: %s" % (args.output, e), file=sys.stderr)
        return 1
    return 10 if sat else 20


if __name__ == "__main__":
    sys.exit(main())
