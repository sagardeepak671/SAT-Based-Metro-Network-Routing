#!/usr/bin/env python3
"""Regression driver: encode every generated case, run the SAT solver, compare
the SAT/UNSAT verdict with the expectation recorded in tests/manifest.json,
then run the decoder on the solver output and the independent verifier
(format_checker.py) on the decoded .metromap.

    python3 TESTER.py [--tests DIR] [--case NAME ...] [--include-future]
                      [--solver auto|minisat|pysat] [--timeout SEC] [-v]

Per-case outcome:
  PASS          solver verdict equals the expected SAT/UNSAT
  MISMATCH      solver decided the instance, but differently from expected
  ENCODE_ERROR  encoder crashed, timed out, or wrote no/invalid DIMACS file
  SOLVER_ERROR  solver did not decide (bad exit status, timeout, malformed
                result file) -- reported separately, never counted as UNSAT
  DECODE_ERROR  verdict was right but the decoder failed to write .metromap
  VERIFY_FAIL   verdict was right and .metromap was written, but
                format_checker.py rejects it (or finds a witness for UNSAT)
  SKIPPED       case flagged "future" in the manifest (use --include-future)

Exit status 0 only when every executed case passes.

Stages are reported separately: a solver failure is never UNSAT, a decoder
failure is never a verifier failure, and a MISMATCH (wrong verdict) is still
decoded and verified so the details show what the solver's model looks like.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def read_header(path):
    """Return (vars, clauses_declared, clauses_counted) or raise ValueError."""
    with open(path) as f:
        first = f.readline().split()
        if len(first) != 4 or first[0] != "p" or first[1] != "cnf":
            raise ValueError("bad DIMACS header %r" % " ".join(first))
        nv, nc = int(first[2]), int(first[3])
        counted = sum(line.split().count("0") for line in f)
    return nv, nc, counted


def run(cmd, timeout, cwd=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, text=True)
    except subprocess.TimeoutExpired:
        return None, "", "timeout after %gs" % timeout, time.time() - t0
    except OSError as e:
        return None, "", str(e), time.time() - t0
    return p.returncode, p.stdout, p.stderr, time.time() - t0


def pick_solver(choice):
    if choice in ("auto", "minisat"):
        exe = shutil.which("minisat")
        if exe:
            return "minisat", lambda i, o: [exe, "-verb=0", i, o]
        if choice == "minisat":
            raise SystemExit("minisat binary not found in PATH")
    try:
        import pysat  # noqa: F401
    except ImportError:
        raise SystemExit("neither a minisat binary nor python-sat is available "
                         "(pip install python-sat)")
    return "pysat:minisat22", lambda i, o: [sys.executable, os.path.join(HERE, "solve_cnf.py"), i, o]


def classify_solver(rc, err, out_path):
    """Map solver exit status + result file to SAT / UNSAT / SOLVER_ERROR."""
    if rc is None:
        return "SOLVER_ERROR", err
    if rc not in (10, 20):
        return "SOLVER_ERROR", "exit status %d: %s" % (rc, err.strip()[-300:])
    try:
        with open(out_path) as f:
            first = f.readline().strip()
            rest = f.read().split()
    except OSError as e:
        return "SOLVER_ERROR", "no result file: %s" % e
    if rc == 10 and first == "SAT" and rest and rest[-1] == "0":
        return "SAT", ""
    if rc == 20 and first == "UNSAT":
        return "UNSAT", ""
    return "SOLVER_ERROR", "exit %d but result file starts with %r" % (rc, first)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests", default=os.path.join(HERE, "tests"))
    ap.add_argument("--case", action="append", help="run only these case names (repeatable)")
    ap.add_argument("--include-future", action="store_true", help="also run cases flagged future in the manifest")
    ap.add_argument("--solver", default="auto", choices=["auto", "minisat", "pysat"])
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per encoder/solver call")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    encoder = os.path.join(HERE, "encoder")
    decoder = os.path.join(HERE, "decoder")
    for exe in (encoder, decoder):
        if not os.access(exe, os.X_OK):
            raise SystemExit("%s missing; run ./compile.sh first" % exe)
    manifest_path = os.path.join(args.tests, "manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit("%s missing; run python3 testcase_gen.py --out %s first" % (manifest_path, args.tests))
    with open(manifest_path) as f:
        manifest = json.load(f)
    solver_name, solver_cmd = pick_solver(args.solver)
    print("solver: %s    tests: %s (seed %s)" % (solver_name, args.tests, manifest.get("seed")))

    counts = {}
    rows = []
    for case in manifest["cases"]:
        name = case["name"]
        if args.case and name not in args.case:
            continue
        base = os.path.join(args.tests, name)
        detail = ""
        cnf_info = ""
        t_enc = t_sol = 0.0
        if case.get("future") and not args.include_future:
            outcome, verdict = "SKIPPED", "-"
        else:
            for ext in (".satinput", ".satoutput", ".metromap"):
                if os.path.exists(base + ext):
                    os.remove(base + ext)
            rc, out, err, t_enc = run([encoder, base], args.timeout)
            verdict = "-"
            if rc != 0:
                outcome, detail = "ENCODE_ERROR", ("exit %s: %s" % (rc, (err or out).strip()[-300:]))
            else:
                try:
                    nv, nc, counted = read_header(base + ".satinput")
                    cnf_info = "%dv/%dc" % (nv, nc)
                    if nc != counted:
                        raise ValueError("header says %d clauses, file has %d" % (nc, counted))
                except (OSError, ValueError) as e:
                    outcome, detail = "ENCODE_ERROR", str(e)
                else:
                    rc, out, err, t_sol = run(solver_cmd(base + ".satinput", base + ".satoutput"), args.timeout)
                    verdict, detail = classify_solver(rc, err, base + ".satoutput")
                    if verdict == "SOLVER_ERROR":
                        outcome = "SOLVER_ERROR"
                    elif verdict != case["expected"]:
                        outcome = "MISMATCH"
                        detail = "expected %s, solver says %s" % (case["expected"], verdict)
                    else:
                        outcome = "PASS"
                    if verdict in ("SAT", "UNSAT"):
                        # decode stage
                        rc, out, err, t_dec = run([decoder, base], args.timeout)
                        msgs = " | ".join(l for l in err.strip().splitlines() if "wrote" not in l)[-300:]
                        if not os.path.exists(base + ".metromap"):
                            if outcome == "PASS":
                                outcome = "DECODE_ERROR"
                            detail = (detail + "; " if detail else "") + "decoder exit %s: %s" % (rc, msgs)
                        else:
                            if rc != 0 or (msgs and args.verbose):
                                detail = (detail + "; " if detail else "") + "decoder exit %s: %s" % (rc, msgs)
                            # verify stage (independent of solver output and decoder)
                            rc, out, err, t_ver = run([sys.executable, os.path.join(HERE, "format_checker.py"),
                                                       base], args.timeout)
                            vres = {0: "VALID", 1: "INVALID", 2: "MALFORMED", 3: "NO_WITNESS"}.get(rc, "ERROR(%s)" % rc)
                            want = "VALID" if verdict == "SAT" else "NO_WITNESS"
                            if vres != want:
                                if outcome == "PASS":
                                    outcome = "VERIFY_FAIL"
                                lines = [l.strip() for l in out.strip().splitlines()]
                                detail = (detail + "; " if detail else "") + "verifier %s: %s" % (
                                    vres, " | ".join(lines[1:4] or lines[:1])[-300:])
                            elif args.verbose:
                                detail = (detail + "; " if detail else "") + "verifier " + out.strip().splitlines()[0][:120]
        counts[outcome] = counts.get(outcome, 0) + 1
        rows.append((name, case, outcome, verdict, cnf_info, t_enc, t_sol, detail))
        line = "%-12s %-34s s%d %3dx%-3d K=%d J=%d P=%-2d expect %-5s got %-5s %12s %5.2fs+%5.2fs" % (
            outcome, name, case["scenario"], case["N"], case["M"], case["K"], case["J"], case["P"],
            case["expected"], verdict, cnf_info, t_enc, t_sol)
        if detail and (args.verbose or outcome != "PASS"):
            line += "\n             -> " + detail
        print(line, flush=True)

    print("\nsummary: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    bad = [r for r in rows if r[2] in ("MISMATCH", "ENCODE_ERROR", "SOLVER_ERROR", "DECODE_ERROR", "VERIFY_FAIL")]
    if bad:
        print("\nnot passing:")
        for name, case, outcome, verdict, *_rest in bad:
            print("  %-12s %-34s expected %-5s reason: %s" % (outcome, name, case["expected"], case["reason"][:110]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
