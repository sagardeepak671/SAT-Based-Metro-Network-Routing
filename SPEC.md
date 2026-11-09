# Metro routing: rules and file formats

Technical requirements transcribed from the original project's A3.pdf (the
original document is preserved in the external backup). This file is the
contract that the encoder, decoder, verifier and tests follow.

## 1. Routing rules

- The city is a grid of N columns and M rows. Coordinates are (x,y): x is the
  column, increasing rightward; y is the row, increasing downward; (0,0) is
  the upper-left cell.
- There are K metro lines. Every line has a start cell and an end cell; all
  2K endpoint cells are distinct.
- A route is a simple orthogonal path (unit steps, no cell visited twice) from
  its start to its end.
- Cells cannot be shared: no cell lies on two routes (endpoints included).
- Each route changes direction at most J times, for any J >= 0.
- Scenario 2 adds P popular cells; every popular cell must lie on at least one
  route. Popular cells are requirements, not obstacles. There is no
  blocked-cell field in the input.

## 2. Input: `<basename>.city`

Scenario 1:

```text
1
N M K J
sx sy ex ey
... (K endpoint rows, one per line, in line order)
```

Scenario 2:

```text
2
N M K J P
sx sy ex ey
... (K endpoint rows)
px py px py ...   (P coordinate pairs on one final line)
```

All numbers are non-negative integers separated by spaces.

## 3. CNF: `<basename>.satinput`

DIMACS format: a header `p cnf <variables> <clauses>` followed by clauses of
integer literals, each clause terminated by `0`. An empty clause (`0` alone)
makes the formula UNSAT.

The occupancy variable for external cell (x,y) and zero-based metro line k is

```text
((y * N + x) * K) + k + 1
```

with N the external width (number of columns). The C++ code swaps the names
N/M and x/y internally, but the formula above in external coordinates is
exact. Variables above N*M*K are auxiliary: the per-line edge/segment
variables of the general-J encoding and at-most-one helpers. With this
encoding the positive occupancy literals of a line are exactly the cells of
one simple route; the decoder nevertheless searches the coloured cells for a
valid route instead of trusting that (the legacy enumeration encoding allowed
extra coloured cells).

## 4. Solver output: `<basename>.satoutput`

MiniSat result-file convention:

```text
SAT
<signed literals> 0
```

or a single line `UNSAT`. MiniSat exits with status 10 for SAT and 20 for
UNSAT; `solve_cnf.py` does the same. The `s`/`v` DIMACS-style output format is
not supported. Solver errors, missing results and incomplete assignments must
never be reported as UNSAT.

## 5. Decoded output: `<basename>.metromap`

On SAT: exactly K rows in input-line order, each the unit moves `L`, `R`, `U`,
`D` of that line's route followed by `0`. There is no leading SAT marker. The
route implicitly starts at the line's start cell. Example for the bundled
`input.city`:

```text
R R R D D 0
```

On UNSAT: a single `0` line. A route checker can validate a SAT witness; it
cannot prove an UNSAT claim from this file. Exhaustive checks on small
instances or structural arguments are separate means of checking an UNSAT
expectation.

(The old README's coordinate-list output was inconsistent with the
assignment; the project uses the move format above.)

## 6. Pipeline boundaries

- `./compile.sh` builds the encoder and the decoder.
- `./run1.sh <basename>` only encodes (`.city` -> `.satinput`).
- The solver is called separately (`minisat` or `solve_cnf.py`).
- `./run2.sh <basename>` only decodes (`.city` + `.satoutput` -> `.metromap`).
- `format_checker.py` and `visualize.py` read only `.city` and `.metromap`.

Neither wrapper calls the SAT solver. The general-J encoding does not
enumerate paths; see README.md section 5 for its size and runtime figures.
