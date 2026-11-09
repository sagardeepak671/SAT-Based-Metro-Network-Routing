#!/usr/bin/env python3
"""Render a .city instance and its decoded .metromap as a self-contained HTML page.

    python3 visualize.py <basename> [-o out.html] [--open]
    python3 visualize.py --index tests/          # one page per case + index.html

Reads only <basename>.city and <basename>.metromap. The page shows the grid,
each metro line in its own colour (thick rounded path through cell centres),
start/end discs labelled S/E, popular cells (star; red ring when no route
covers it), cells used by two lines (red outline), the move string and turn
count per line, and the result of format_checker.py run on the same files.
Invalid routes are drawn as far as they can be (up to the first illegal move
or the first step outside the grid) so encoder/decoder mistakes can be seen.
A metromap consisting of the single "0" row is shown as "no witness".

No JavaScript framework; the output is plain HTML + inline SVG.
"""
import argparse
import html
import json
import os
import sys
import webbrowser
from typing import Dict, List, Optional, Tuple

from format_checker import MOVES, Malformed, read_metromap, verify
from metro_common import Problem, parse_city, validate_problem

PALETTE = ["#ff2a2a", "#1fa8ff", "#ffe600", "#8a3ffc", "#22dd55", "#ff3d9a",
           "#ff8c1a", "#00e5e5", "#c0ff33", "#ff9ad5", "#9aa0ff", "#a0522d"]

CELL = 52      # px per cell
PAD = 30       # margin for axis labels


def colour(k: int) -> str:
    return PALETTE[k % len(PALETTE)]


def trace(prob: Problem, k: int, moves: List[str]) -> Tuple[List[Tuple[int, int]], int, Optional[str]]:
    """Follow moves from line k's start. Returns (cells inside grid, turns, stop reason)."""
    x, y = prob.lines[k][0], prob.lines[k][1]
    cells = [(x, y)]
    turns, last, reason = 0, None, None
    for i, m in enumerate(moves, 1):
        if m not in MOVES:
            reason = "stopped at move %d: illegal token '%s'" % (i, m)
            break
        if last is not None and m != last:
            turns += 1
        last = m
        dx, dy = MOVES[m]
        x, y = x + dx, y + dy
        if not (0 <= x < prob.N and 0 <= y < prob.M):
            reason = "stopped at move %d: '%s' leaves the grid" % (i, m)
            break
        cells.append((x, y))
    return cells, turns, reason


def svg_grid(prob: Problem, routes: Optional[List[List[str]]], problems: List[str]) -> str:
    N, M = prob.N, prob.M
    W, H = PAD + N * CELL + 10, PAD + M * CELL + 10

    def cx(x: int) -> float:
        return PAD + x * CELL + CELL / 2

    def cy(y: int) -> float:
        return PAD + y * CELL + CELL / 2

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H)]
    out.append('<rect x="0" y="0" width="%d" height="%d" fill="#14161c"/>' % (W, H))
    # cells
    usage: Dict[Tuple[int, int], List[int]] = {}
    traced: List[Tuple[List[Tuple[int, int]], int, Optional[str]]] = []
    if routes is not None:
        for k, mv in enumerate(routes[:prob.K]):
            t = trace(prob, k, mv)
            traced.append(t)
            for c in t[0]:
                usage.setdefault(c, []).append(k)
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):   # endpoints always count as used
        for c in ((sx, sy), (ex, ey)):
            if k not in usage.setdefault(c, []):
                usage[c].append(k)
    popular = set(prob.popular)
    for y in range(M):
        for x in range(N):
            fill = "#1d2029"
            if (x, y) in popular:
                fill = "#3a3410"
            out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#3b3f4d" stroke-width="1"/>'
                       % (PAD + x * CELL, PAD + y * CELL, CELL, CELL, fill))
    # axis labels
    for x in range(N):
        out.append('<text x="%.1f" y="%d" fill="#8a8f9c" font-size="12" text-anchor="middle" font-family="monospace">%d</text>'
                   % (cx(x), PAD - 8, x))
    for y in range(M):
        out.append('<text x="%d" y="%.1f" fill="#8a8f9c" font-size="12" text-anchor="end" font-family="monospace">%d</text>'
                   % (PAD - 8, cy(y) + 4, y))
    # routes
    for k, (cells, turns, reason) in enumerate(traced):
        if len(cells) >= 2:
            pts = " ".join("%.1f,%.1f" % (cx(x), cy(y)) for x, y in cells)
            out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%d" stroke-linecap="round" '
                       'stroke-linejoin="round" opacity="0.92"><title>line %d: %d turns</title></polyline>'
                       % (pts, colour(k), CELL * 0.34, k + 1, turns))
        if reason:   # mark where an invalid route stops
            x, y = cells[-1]
            out.append('<text x="%.1f" y="%.1f" fill="#fff" font-size="22" text-anchor="middle" font-weight="bold">'
                       '&#x2717;<title>%s</title></text>' % (cx(x), cy(y) + 8, html.escape(reason)))
    # shared cells
    for (x, y), ks in usage.items():
        if len(ks) > 1:
            out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#ff1744" stroke-width="4">'
                       '<title>cell (%d,%d) used by lines %s</title></rect>'
                       % (PAD + x * CELL + 2, PAD + y * CELL + 2, CELL - 4, CELL - 4, x, y,
                          ", ".join(str(k + 1) for k in ks)))
    # endpoints
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):
        for (x, y), label in (((sx, sy), "S"), ((ex, ey), "E")):
            out.append('<circle cx="%.1f" cy="%.1f" r="%d" fill="%s" stroke="#0d0e12" stroke-width="2"/>'
                       % (cx(x), cy(y), CELL * 0.33, colour(k)))
            out.append('<text x="%.1f" y="%.1f" fill="#0d0e12" font-size="13" font-weight="bold" '
                       'text-anchor="middle" font-family="sans-serif">%s%d</text>'
                       % (cx(x), cy(y) + 5, label, k + 1))
    # popular cells
    endpoints = prob.endpoints()
    for (x, y) in prob.popular:
        covered = any(c == (x, y) for cells, _, _ in traced for c in cells) or (x, y) in endpoints
        if routes is None:
            covered = True  # nothing to judge
        if not covered:
            out.append('<circle cx="%.1f" cy="%.1f" r="%d" fill="none" stroke="#ff1744" stroke-width="3" '
                       'stroke-dasharray="4 3"/>' % (cx(x), cy(y), CELL * 0.4))
        # on an endpoint cell the star goes to the top-right corner so the S/E label stays readable
        ox, oy = (CELL * 0.3, -CELL * 0.22) if (x, y) in endpoints else (0, 6)
        out.append('<text x="%.1f" y="%.1f" fill="%s" font-size="18" text-anchor="middle" '
                   'style="paint-order:stroke" stroke="#0d0e12" stroke-width="3">&#9733;'
                   '<title>popular cell (%d,%d)%s</title></text>'
                   % (cx(x) + ox, cy(y) + oy, "#ffffff" if covered else "#ff1744", x, y,
                      "" if covered else " -- NOT on any route"))
    out.append("</svg>")
    return "\n".join(out)


def render_page(title: str, prob: Problem, routes: Optional[List[List[str]]], problems: List[str],
                verdict: str, city_text: str, metromap_text: str) -> str:
    svg = svg_grid(prob, routes, problems)
    badge = {"VALID": ("#1b5e20", "VALID"), "INVALID": ("#b71c1c", "INVALID"),
             "NO_WITNESS": ("#455a64", "NO WITNESS"), "MALFORMED": ("#e65100", "MALFORMED")}[verdict]
    rows = []
    for k, (sx, sy, ex, ey) in enumerate(prob.lines):
        if routes is None or k >= len(routes):
            mv, turns, reason, ncells = "&mdash;", "&mdash;", "no route row", "&mdash;"
        else:
            cells, t, r = trace(prob, k, routes[k])
            mv = html.escape(" ".join(routes[k])) or "(empty)"
            turns = '<b style="color:%s">%d</b>' % ("#ff5252" if t > prob.J else "#9ccc65", t)
            reason, ncells = html.escape(r or ""), str(len(cells))
        rows.append('<tr><td><span class="sw" style="background:%s"></span>%d</td><td>(%d,%d) &rarr; (%d,%d)</td>'
                    '<td class="mono">%s</td><td>%s / %d</td><td>%s</td><td class="warn">%s</td></tr>'
                    % (colour(k), k + 1, sx, sy, ex, ey, mv, turns, prob.J, ncells, reason))
    pop = ", ".join("(%d,%d)" % c for c in prob.popular) or "none"
    plist = "".join("<li>%s</li>" % html.escape(p) for p in problems)
    msg = {"VALID": "all checks passed", "INVALID": "%d problem(s):" % len(problems),
           "NO_WITNESS": "the .metromap is the single '0' row (UNSAT claim): no routes to verify; "
                         "this is not proof that the instance is unsolvable",
           "MALFORMED": "; ".join(problems)}[verdict]
    return """<!doctype html><html><head><meta charset="utf-8"><title>%(title)s</title>
<style>
 body{background:#0d0e12;color:#e6e6e6;font-family:sans-serif;margin:20px}
 h1{font-size:20px;margin:0 0 6px} .sub{color:#9aa0ad;font-size:13px;margin-bottom:14px}
 .wrap{display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start}
 table{border-collapse:collapse;font-size:14px} td,th{padding:5px 10px;border-bottom:1px solid #2b2f3a;text-align:left}
 .mono{font-family:monospace} .sw{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:6px;vertical-align:-2px}
 .badge{display:inline-block;padding:4px 10px;border-radius:4px;font-weight:bold;background:%(bcol)s;color:#fff}
 .warn{color:#ff8a80} ul{margin:6px 0 0 18px} li{margin:3px 0;color:#ffab91}
 pre{background:#1a1d25;padding:10px;border-radius:4px;font-size:12px;overflow:auto;max-width:420px}
 .leg{font-size:13px;color:#9aa0ad;margin-top:8px}
</style></head><body>
<h1>%(title)s</h1>
<div class="sub">scenario %(sc)d &middot; grid %(N)d&times;%(M)d (x right, y down, (0,0) top-left) &middot; K=%(K)d lines &middot; J=%(J)d turns max &middot; popular cells: %(pop)s</div>
<div class="wrap">
 <div>%(svg)s
  <div class="leg">&#9679; S/E = start/end &middot; &#9733; popular cell (red dashed ring = not on any route) &middot; red box = cell used by two lines &middot; &#x2717; = route stops here (invalid move)</div>
 </div>
 <div>
  <p><span class="badge">verifier: %(badge)s</span> &nbsp; %(msg)s</p>
  <ul>%(plist)s</ul>
  <table><tr><th>line</th><th>start &rarr; end</th><th>decoded moves</th><th>turns / J</th><th>cells</th><th></th></tr>%(rows)s</table>
  <div class="wrap" style="margin-top:14px"><div><b>.city</b><pre>%(city)s</pre></div><div><b>.metromap</b><pre>%(mm)s</pre></div></div>
 </div>
</div></body></html>
""" % dict(title=html.escape(title), bcol=badge[0], badge=badge[1], msg=html.escape(msg) if verdict != "INVALID" else msg,
           sc=prob.scenario, N=prob.N, M=prob.M, K=prob.K, J=prob.J, pop=pop, svg=svg, plist=plist,
           rows="".join(rows), city=html.escape(city_text), mm=html.escape(metromap_text))


def build(basename: str) -> Tuple[str, str]:
    """Return (html, verdict) for <basename>.city + <basename>.metromap."""
    city_path, mm_path = basename + ".city", basename + ".metromap"
    with open(city_path) as f:
        city_text = f.read()
    prob = parse_city(city_text)
    errs = validate_problem(prob)
    if errs:
        raise Malformed("%s: %s" % (city_path, "; ".join(errs)))
    try:
        with open(mm_path) as f:
            mm_text = f.read()
    except OSError:
        mm_text = ""
    routes: Optional[List[List[str]]] = None
    problems: List[str] = []
    if not mm_text.strip():
        verdict = "MALFORMED"
        problems = ["%s is missing or empty (run the decoder first)" % mm_path]
    else:
        rows, problems = read_metromap(mm_path)
        if rows is None:
            verdict = "NO_WITNESS"
        else:
            routes = [toks for _, toks in rows]
            more, _ = verify(prob, rows)
            problems += more
            verdict = "INVALID" if problems else "VALID"
    title = "%s  [%s]" % (os.path.basename(basename), verdict)
    return render_page(title, prob, routes, problems, verdict, city_text, mm_text), verdict


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("basename", nargs="?")
    ap.add_argument("-o", "--output", help="output HTML file (default <basename>.html)")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    ap.add_argument("--index", metavar="DIR", help="render every <case>.city in DIR and write DIR/index.html")
    args = ap.parse_args(argv)

    if args.index:
        names = sorted(f[:-5] for f in os.listdir(args.index) if f.endswith(".city"))
        expected = {}
        mpath = os.path.join(args.index, "manifest.json")
        if os.path.exists(mpath):
            with open(mpath) as f:
                expected = {c["name"]: c["expected"] for c in json.load(f)["cases"]}
        items = []
        for n in names:
            base = os.path.join(args.index, n)
            try:
                page, verdict = build(base)
            except (Malformed, ValueError, OSError) as e:
                items.append('<li>%s &mdash; <span style="color:#ff8a80">not rendered: %s</span></li>'
                             % (html.escape(n), html.escape(str(e))))
                continue
            with open(base + ".html", "w") as f:
                f.write(page)
            col = {"VALID": "#9ccc65", "INVALID": "#ff5252", "NO_WITNESS": "#90a4ae", "MALFORMED": "#ffb74d"}[verdict]
            items.append('<li><a href="%s.html" style="color:#8ab4f8">%s</a> &mdash; <span style="color:%s">%s</span>'
                         '%s</li>' % (html.escape(n), html.escape(n), col, verdict,
                                      " (expected %s)" % expected[n] if n in expected else ""))
        idx = os.path.join(args.index, "index.html")
        with open(idx, "w") as f:
            f.write("<!doctype html><html><head><meta charset='utf-8'><title>metro cases</title>"
                    "<style>body{background:#0d0e12;color:#e6e6e6;font-family:sans-serif;margin:20px}li{margin:3px 0}</style>"
                    "</head><body><h1>metro routing cases</h1><ul>%s</ul></body></html>" % "".join(items))
        print("wrote %s (%d cases)" % (idx, len(items)))
        if args.open:
            webbrowser.open("file://" + os.path.abspath(idx))
        return 0

    if not args.basename:
        ap.error("give a basename or --index DIR")
    try:
        page, verdict = build(args.basename)
    except (Malformed, ValueError, OSError) as e:
        print("visualize: %s" % e, file=sys.stderr)
        return 2
    out = args.output or args.basename + ".html"
    with open(out, "w") as f:
        f.write(page)
    print("wrote %s (verifier: %s)" % (out, verdict))
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
