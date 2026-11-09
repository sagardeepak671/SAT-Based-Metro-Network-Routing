# SAT-based metro routing

Routes K metro lines through an N x M grid with a SAT solver. Each line is a
simple orthogonal path between its two given cells, lines never share a cell,
each line changes direction at most J times, and in scenario 2 every popular
cell must lie on some line. Any J >= 0 is supported.

The pipeline is **encode -> solve -> decode -> verify**, with a test-case
generator, a regression driver and a browser view. File formats and rules are
in [SPEC.md](SPEC.md). (The source originally described itself as a COL226
assignment project; this does not establish authorship or a license.)

## 1. Requirements

| Need | Used by |
|------|---------|
| C++11 compiler, Make, Bash | encoder, decoder |
| Python 3 (standard library only) | generator, tester, verifier, visualizer |
| A SAT solver: a `minisat` binary on PATH, **or** `pip install python-sat` | solving |

`solve_cnf.py` drives python-sat's bundled MiniSat 2.2 core with the same
command line, result-file format and exit statuses as the `minisat` binary
(10 = SAT, 20 = UNSAT). `TESTER.py` uses `minisat` when it is on PATH and
falls back to `solve_cnf.py`. On a managed system Python install python-sat
inside a venv or with `pip install --user python-sat`.

## 2. Quick start

```bash
./compile.sh                 # builds ./encoder and ./decoder
pip install python-sat       # only if no minisat binary is available
make test                    # generates tests/ and runs the whole suite (81 cases, ~1 min)
```

## 3. Full flow for one instance

Every stage works on `<basename>` and reads/writes `<basename>.<ext>`:

| Stage | Command | Reads | Writes |
|-------|---------|-------|--------|
| encode | `./run1.sh C` | `C.city` | `C.satinput` (DIMACS CNF) |
| solve | `python3 solve_cnf.py C.satinput C.satoutput` (or `minisat C.satinput C.satoutput`) | `C.satinput` | `C.satoutput` |
| decode | `./run2.sh C` | `C.city`, `C.satoutput` | `C.metromap` (moves per line, or `0`) |
| verify | `python3 format_checker.py C` | `C.city`, `C.metromap` | result line on stdout |
| view | `python3 visualize.py C --open` | `C.city`, `C.metromap` | `C.html`, opened in the browser |

Example (a scenario-1 instance whose first line needs six turns):

```bash
C=tests/s1_j6_corridor
./run1.sh $C
python3 solve_cnf.py $C.satinput $C.satoutput
./run2.sh $C && cat $C.metromap
python3 format_checker.py $C
python3 visualize.py $C --open
```

Other build commands: `make run` encodes the bundled `input.city`;
`CXX=clang++ ./compile.sh` chooses a compiler; `DEBUG=1 ./compile.sh` makes a
sanitizer build; `CLEAN=1 ./compile.sh` rebuilds from scratch; `make clean`
removes binaries and generated outputs.

## 4. Files

| File | Purpose |
|------|---------|
| `encoder.cpp`, `run1.sh` | CNF encoder for any J (see section 5). `./encoder C --legacy` selects the original path-enumeration encoding (J <= 3), kept for cross-checking only. |
| `decoder.cpp`, `run2.sh` | `.city` + `.satoutput` -> `.metromap` (section 6). |
| `solve_cnf.py` | `minisat`-compatible stand-in using python-sat. |
| `format_checker.py` | Standalone verifier of a `.metromap` against its `.city` (section 7). |
| `visualize.py` | Self-contained HTML/SVG view of a `.city` + `.metromap` pair (section 8). |
| `testcase_gen.py` | Reproducible test-case generator with evidence for every expectation (section 9). |
| `TESTER.py` | Regression driver: encode -> solve -> compare -> decode -> verify. |
| `metro_common.py` | Shared helpers: `.city` parsing, route checking, ASCII rendering, small exhaustive reference solver. |
| `input.city` | One small example. |
| `SPEC.md` | Formats, coordinate conventions and routing rules. |

## 5. Encoding

Occupancy variables follow the formula in SPEC.md: cell (x,y) coloured by
line k. At most one colour per cell; in scenario 2 each popular cell needs a
colour.

Routes are encoded as a **segment automaton**. For every line k, cell c,
direction d and segment index t in 0..J there is an edge variable "line k
leaves c in direction d on segment t (after t turns)". All constraints are
local:

- the start emits exactly one edge, on segment 0, and receives none;
- the end receives exactly one edge and emits none;
- any other cell is coloured k iff one edge of k arrives, and then exactly one
  edge leaves (in-degree and out-degree at most 1);
- an edge leaving on (d,t) must be fed by an arrival on (d,t) (going
  straight) or on a perpendicular direction with t-1 (a turn), and vice
  versa; U-turns are impossible.

Degree <= 1 rules out branching, and a closed loop is impossible because it
has >= 4 turns while the segment index cannot grow around the loop and return
to its first value. So the cells coloured k are exactly one simple route with
<= J turns, in both scenarios.

Size: about 4·N·M·K·(J+1) variables and 40·N·M·K·(J+1) short clauses --
linear in J and in the grid, independent of the number of paths. Measured:
25x25, K=8, J=12 gives 2.5M clauses in 2 s; MiniSat solves planted instances
of that size in about a minute. Instances that are unsolvable for topological
reasons (a line that must cross another) are much harder for the solver:
12x12 with J=6 took ~90 s and 15x15 did not finish in 5 minutes.

History: the legacy enumeration encoding had a scenario-2 defect (a popular
cell on no candidate path had an unconstrained colour variable, so impossible
instances came out SAT). It is fixed there as well, and the cases that
exposed it stay in the suite (e.g. `s2_j0_popular_off_line`).

## 6. Decoding

The decoder reads the `.city` and the MiniSat-style `.satoutput`, rebuilds
each cell's colour from the occupancy variables, and recovers per line a
simple route with at most J turns inside that line's coloured cells,
preferring the route that covers most popular cells and then most cells (it
does not rely on the coloured cells being exactly one path).

| Exit | Meaning |
|------|---------|
| 0 | wrote `.metromap`: K move rows, or the single `0` row on UNSAT |
| 3 | routes written, but a popular cell is on no route (diagnostic on stderr) |
| 1 | solver output missing / malformed / incomplete, or no valid route exists in the coloured cells; nothing written, no route invented |

Solver failures are never reported as UNSAT.

## 7. Verifying

```bash
python3 format_checker.py tests/s2_j3_three_lines             # C.city + C.metromap
python3 format_checker.py --city a.city --metromap b.metromap
```

Reads only the two files. Checks the row count, move alphabet, grid bounds,
endpoints, simplicity, cell sharing between lines, the turn limit and
(scenario 2) popular-cell coverage, and lists every violation with its
`.metromap` line number.

| Exit | Result |
|------|--------|
| 0 | `VALID` |
| 1 | `INVALID` (violations listed) |
| 2 | `MALFORMED` (missing or unparsable file) |
| 3 | `NO_WITNESS`: the single `0` row; nothing to check, and not evidence that the instance is unsolvable |

## 8. Viewing routes

```bash
python3 visualize.py tests/s2_j3_three_lines --open   # writes tests/s2_j3_three_lines.html and opens it
python3 visualize.py --index tests --open             # one page per case + tests/index.html
```

The page shows the grid with one colour per metro line, S/E discs at the
endpoints, a star on every popular cell (red dashed ring when no route covers
it), a red box on any cell used by two lines, the decoded move string and
turn count per line, and the verifier's result with its messages. Invalid
routes are drawn as far as they go, so a bad answer can be inspected
visually. Only the `.city` and `.metromap` files are read.

## 9. Testing

```bash
python3 testcase_gen.py --out tests   # tests/*.city, *.witness.metromap, manifest.json, CASES.txt
python3 TESTER.py --tests tests       # -v prints verifier/decoder details for passing cases too
```

81 cases: hand-written small ones (both scenarios, rectangular and one-row
grids, several lines, popular cells, J = 0..9, solvable and impossible
variants) and seeded random ones (planted solutions, crossing / pigeonhole /
unreachable-popular-cell UNSAT constructions, random instances decided by
the exhaustive solver), with J up to 10. `tests/CASES.txt` explains every
case: instance, expected verdict, reason, evidence (witness checked by
`metro_common.check_solution` and/or an exhaustive check) and a picture.
Generation is deterministic for a given `--seed` (default 20240601); the
hand-written cases do not depend on it.

TESTER outcomes: `PASS`, `MISMATCH` (wrong verdict), `ENCODE_ERROR`,
`SOLVER_ERROR` (never counted as UNSAT), `DECODE_ERROR`, `VERIFY_FAIL`,
`SKIPPED` (cases flagged `future` in the manifest -- none at present).

## 10. Limitations

- Solver time grows quickly on large grids and on topologically impossible
  instances (section 5); the encoding has no planarity reasoning.
- `solve_cnf.py` parses DIMACS in Python (~3 s per million clauses); a real
  `minisat` binary avoids that overhead.
- The decoder's route search inside a line's cells has a step budget; on
  pathological inputs it returns the best route found so far (still verified).
- The exhaustive reference solver certifies only small instances; larger
  UNSAT cases rest on the documented structural arguments.
- The encoder's parser validates little; malformed `.city` files may crash it
  (the Python tools validate properly).
