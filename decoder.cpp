// decoder: <basename>.city + <basename>.satoutput  ->  <basename>.metromap
//
// Usage: ./decoder <basename>
//
// Reads the instance and a MiniSat-style result file, recovers one route per
// metro line from the solver's assignment and writes the move format of
// SPEC.md (K rows of L/R/U/D moves terminated by 0; a single "0" on UNSAT).
//
// Variable mapping (must match encoder.cpp): for external cell (x,y), x the
// column in 0..N-1 and y the row in 0..M-1, and zero-based line k,
//     occupancy variable = (y*N + x)*K + k + 1.
// encoder.cpp swaps the names N/M and x/y internally, but because it also
// swaps them when parsing, this formula in external coordinates is exact (the
// start/end unit clauses are used below as a runtime cross-check).
//
// How routes are recovered. The encoding guarantees that each line's coloured
// cells contain its start and end, that no cell carries two colours, and that
// at least one candidate path is selected whose cells are all coloured. It
// does NOT guarantee that the coloured cells are exactly one path: scenario 1
// lets several candidate paths be selected at once (plus degenerate, self-
// overlapping candidates), and in both scenarios cells that lie on no
// candidate path are unconstrained. So, per line, the decoder searches the
// coloured cells for a route with the fewest direction changes (0-1 BFS over
// (cell, heading) states). A minimum-turn walk never revisits a cell (cutting
// a loop out of a walk only lowers the turn count), so the result is a simple
// route; it is then checked against J. If no route exists inside the coloured
// cells, or the best one exceeds J, the decoder reports an error and writes
// nothing -- it never invents moves.
//
// Exit status: 0 = .metromap written (SAT routes or UNSAT "0");
//              3 = routes written, but the assignment violates a requirement
//                  that a route search cannot fix (popular cell on no route);
//              1 = input/solver-output/decoding error, no .metromap written.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace std;

struct Problem {
    int scenario = 0, N = 0, M = 0, K = 0, J = 0, P = 0;
    vector<int> sx, sy, ex, ey;     // external coordinates
    vector<pair<int, int>> popular; // (x, y)
};

static string g_base;

[[noreturn]] static void fail(const string& msg) {
    cerr << "decoder: " << msg << "\n";
    exit(1);
}

static vector<string> nonblank_lines(const string& path) {
    ifstream in(path);
    if (!in) fail("cannot open " + path);
    vector<string> out;
    string line;
    while (getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        bool blank = true;
        for (char c : line) if (!isspace((unsigned char)c)) { blank = false; break; }
        if (!blank) out.push_back(line);
    }
    return out;
}

static vector<long long> ints_of(const string& line, const string& what) {
    istringstream iss(line);
    vector<long long> v;
    string tok;
    while (iss >> tok) {
        char* end = nullptr;
        long long x = strtoll(tok.c_str(), &end, 10);
        if (*end != '\0') fail(what + ": not an integer: '" + tok + "'");
        v.push_back(x);
    }
    return v;
}

static Problem read_city(const string& path) {
    vector<string> L = nonblank_lines(path);
    if (L.size() < 2) fail(path + ": needs a scenario line and a header line");
    Problem p;
    vector<long long> s = ints_of(L[0], "scenario line");
    if (s.size() != 1 || (s[0] != 1 && s[0] != 2)) fail(path + ": scenario must be 1 or 2");
    p.scenario = (int)s[0];
    vector<long long> h = ints_of(L[1], "header");
    if (p.scenario == 1 && h.size() != 4) fail(path + ": scenario 1 header must be 'N M K J'");
    if (p.scenario == 2 && h.size() != 5) fail(path + ": scenario 2 header must be 'N M K J P'");
    p.N = (int)h[0]; p.M = (int)h[1]; p.K = (int)h[2]; p.J = (int)h[3];
    p.P = p.scenario == 2 ? (int)h[4] : 0;
    if (p.N <= 0 || p.M <= 0 || p.K <= 0 || p.J < 0 || p.P < 0) fail(path + ": bad header values");
    if ((long long)p.N * p.M * p.K > 200000000LL) fail(path + ": grid too large");
    if ((int)L.size() < 2 + p.K + (p.P > 0 ? 1 : 0)) fail(path + ": too few lines for K and P");
    for (int k = 0; k < p.K; k++) {
        vector<long long> e = ints_of(L[2 + k], "endpoint row");
        if (e.size() != 4) fail(path + ": endpoint row " + to_string(k + 1) + " must be 'sx sy ex ey'");
        p.sx.push_back((int)e[0]); p.sy.push_back((int)e[1]);
        p.ex.push_back((int)e[2]); p.ey.push_back((int)e[3]);
        for (int i = 0; i < 4; i++) {
            int v = (int)e[i], lim = (i % 2 == 0) ? p.N : p.M;
            if (v < 0 || v >= lim) fail(path + ": endpoint row " + to_string(k + 1) + " out of bounds");
        }
    }
    if (p.P > 0) {
        vector<long long> q = ints_of(L[2 + p.K], "popular-cell line");
        if ((int)q.size() != 2 * p.P) fail(path + ": popular-cell line must hold exactly 2*P integers");
        for (int i = 0; i < p.P; i++) {
            int x = (int)q[2 * i], y = (int)q[2 * i + 1];
            if (x < 0 || x >= p.N || y < 0 || y >= p.M) fail(path + ": popular cell out of bounds");
            p.popular.push_back({x, y});
        }
    }
    return p;
}

// Returns true for SAT (assignment filled for vars 1..nvars, value +1/-1),
// false for UNSAT. Anything else is a fatal error.
static bool read_satoutput(const string& path, long long nvars, vector<signed char>& val) {
    ifstream in(path);
    if (!in) fail("cannot open " + path + " (no solver output; run the solver first)");
    string first;
    while (getline(in, first)) {
        if (!first.empty() && first.back() == '\r') first.pop_back();
        size_t a = first.find_first_not_of(" \t");
        if (a == string::npos) continue;
        first = first.substr(a, first.find_last_not_of(" \t") - a + 1);
        break;
    }
    if (first.empty()) fail(path + ": empty solver output (solver crashed or was interrupted?)");
    if (first == "UNSAT") return false;
    if (first == "INDET" || first == "INDETERMINATE")
        fail(path + ": solver reported INDETERMINATE (timeout/interrupt), not a verdict");
    if (first.size() >= 2 && (first[0] == 's' || first[0] == 'v') && first[1] == ' ')
        fail(path + ": 's'/'v' DIMACS-style output is not supported; expected MiniSat 'SAT'/'UNSAT' format");
    if (first != "SAT") fail(path + ": unrecognised first line '" + first + "' (expected SAT or UNSAT)");

    val.assign((size_t)nvars + 1, 0);
    string tok;
    bool terminated = false;
    long long count = 0;
    while (in >> tok) {
        char* end = nullptr;
        long long lit = strtoll(tok.c_str(), &end, 10);
        if (*end != '\0') fail(path + ": non-integer token '" + tok + "' in assignment");
        if (lit == 0) { terminated = true; break; }
        long long v = lit < 0 ? -lit : lit;
        count++;
        if (v > nvars) continue;  // auxiliary variable: not needed for decoding
        signed char s = lit < 0 ? -1 : 1;
        if (val[v] != 0 && val[v] != s)
            fail(path + ": variable " + to_string(v) + " appears with both signs");
        val[v] = s;
    }
    if (!terminated) fail(path + ": assignment not terminated by 0 (truncated solver output?)");
    if (count == 0) fail(path + ": SAT with an empty assignment");
    for (long long v = 1; v <= nvars; v++) {
        if (val[v] == 0) {
            fail(path + ": incomplete assignment, occupancy variable " + to_string(v) +
                 " is missing (need all 1.." + to_string(nvars) + ")");
        }
    }
    return true;
}

static const int DX[4] = {-1, 1, 0, 0};
static const int DY[4] = {0, 0, -1, 1};
static const char DCH[4] = {'L', 'R', 'U', 'D'};

// Route search inside the cells coloured k.
//
// Enumerates simple routes from start to end that use only cells coloured k
// and change direction at most J times (DFS with geometric pruning: with no
// turns left the end must be straight ahead, with one turn left it must not
// be behind). Among them it prefers the route covering the most popular cells
// and then the most coloured cells, so in scenario 2 the selected candidate
// path (whose cells are exactly the coloured ones) is recovered rather than a
// shortcut through them. In scenario 1 there are no popular cells and any
// valid route is acceptable, so the first one found is returned.
// Returns "" if no route exists (turns_needed then stays -1) or the search
// budget is exhausted before a route is found.
struct Search {
    const Problem& p; const vector<int>& colour; int k;
    vector<char> visited, popular_mask;
    string moves, best; int best_pop = -1, best_cells = -1;
    long long steps = 0; const long long budget = 20000000LL;
    int ex, ey, total_coloured = 0, total_pop = 0; bool stop = false;
    Search(const Problem& p_, const vector<int>& c_, int k_) : p(p_), colour(c_), k(k_) {
        visited.assign((size_t)p.N * p.M, 0);
        popular_mask.assign((size_t)p.N * p.M, 0);
        for (auto& c : p.popular) popular_mask[c.second * p.N + c.first] = 1;
        ex = p.ex[k]; ey = p.ey[k];
        for (int i = 0; i < p.N * p.M; i++) if (colour[i] == k) { total_coloured++; if (popular_mask[i]) total_pop++; }
    }
    bool feasible(int x, int y, int d, int turns_left) const {
        if (turns_left >= 2) return true;
        int ahead = (ex - x) * DX[d] + (ey - y) * DY[d];
        if (turns_left == 1) return ahead >= 0;
        return ahead >= 0 && ((DX[d] != 0 && ey == y) || (DY[d] != 0 && ex == x));
    }
    void dfs(int x, int y, int last, int turns, int pop, int cells) {
        if (stop) return;
        if (x == ex && y == ey) {
            if (pop > best_pop || (pop == best_pop && cells > best_cells)) {
                best_pop = pop; best_cells = cells; best = moves;
                if (p.scenario == 1 || (pop == total_pop && cells == total_coloured)) stop = true;
            }
            return;
        }
        for (int d = 0; d < 4 && !stop; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < 0 || nx >= p.N || ny < 0 || ny >= p.M) continue;
            int id = ny * p.N + nx;
            if (colour[id] != k || visited[id]) continue;
            int nt = turns + ((last >= 0 && d != last) ? 1 : 0);
            if (nt > p.J || !feasible(nx, ny, d, p.J - nt)) continue;
            if (++steps > budget) { stop = true; return; }
            visited[id] = 1; moves.push_back(DCH[d]);
            dfs(nx, ny, d, nt, pop + popular_mask[id], cells + 1);
            moves.pop_back(); visited[id] = 0;
        }
    }
    string run() {
        int sid = p.sy[k] * p.N + p.sx[k];
        visited[sid] = 1;
        dfs(p.sx[k], p.sy[k], -1, 0, popular_mask[sid], 1);
        return best;
    }
};

static void dump_line(const Problem& p, const vector<int>& colour, int k) {
    cerr << "  coloured cells of line " << k + 1 << " (x rightwards, y downwards; S/E = endpoints):\n";
    for (int y = 0; y < p.M; y++) {
        cerr << "    ";
        for (int x = 0; x < p.N; x++) {
            char c = colour[y * p.N + x] == k ? '#' : '.';
            if (x == p.sx[k] && y == p.sy[k]) c = 'S';
            if (x == p.ex[k] && y == p.ey[k]) c = 'E';
            cerr << c;
        }
        cerr << "\n";
    }
}

int main(int argc, char* argv[]) {
    if (argc != 2) { cerr << "Usage: " << argv[0] << " <basename>\n"; return 2; }
    g_base = argv[1];
    const string city = g_base + ".city", sato = g_base + ".satoutput", out = g_base + ".metromap";
    remove(out.c_str());  // never leave a stale result behind

    Problem p = read_city(city);
    const long long nvars = (long long)p.N * p.M * p.K;
    vector<signed char> val;
    bool sat = read_satoutput(sato, nvars, val);

    if (!sat) {
        ofstream o(out);
        if (!o) fail("cannot write " + out);
        o << "0\n";
        cerr << "decoder: UNSAT -> wrote " << out << "\n";
        return 0;
    }

    // colour[y*N+x] = k of the single positive occupancy variable, or -1.
    auto var = [&](int x, int y, int k) { return (long long)(y * p.N + x) * p.K + k + 1; };
    vector<int> colour((size_t)p.N * p.M, -1);
    for (int y = 0; y < p.M; y++)
        for (int x = 0; x < p.N; x++)
            for (int k = 0; k < p.K; k++)
                if (val[var(x, y, k)] > 0) {
                    if (colour[y * p.N + x] != -1)
                        fail("cell (" + to_string(x) + "," + to_string(y) + ") is coloured by lines " +
                             to_string(colour[y * p.N + x] + 1) + " and " + to_string(k + 1) +
                             "; the assignment does not satisfy the encoder's exclusivity clauses");
                    colour[y * p.N + x] = k;
                }
    // Cross-check the variable mapping: the encoder forces every start/end cell.
    for (int k = 0; k < p.K; k++) {
        if (colour[p.sy[k] * p.N + p.sx[k]] != k || colour[p.ey[k] * p.N + p.ex[k]] != k)
            fail("line " + to_string(k + 1) + ": its start/end cell is not coloured with its own line; " +
                 "the solver output does not match this .city (variable mapping mismatch?)");
    }

    vector<string> routes(p.K);
    vector<int> extra(p.K, 0);
    for (int k = 0; k < p.K; k++) {
        Search srch(p, colour, k);
        routes[k] = srch.run();
        if (routes[k].empty()) {
            if (srch.steps > srch.budget)
                cerr << "decoder: line " << k + 1 << ": route search budget exhausted before any route with <= J="
                     << p.J << " turns was found inside its coloured cells; refusing to invent a route\n";
            else
                cerr << "decoder: line " << k + 1 << ": no simple route with <= J=" << p.J
                     << " turns connects its start (" << p.sx[k] << "," << p.sy[k] << ") to its end ("
                     << p.ex[k] << "," << p.ey[k] << ") inside the cells coloured with this line; "
                     << "refusing to invent a route\n";
            dump_line(p, colour, k);
            return 1;
        }
        if (srch.steps > srch.budget)
            cerr << "decoder: note: line " << k + 1 << ": search budget exhausted, using best route found so far\n";
        extra[k] = srch.total_coloured - ((int)routes[k].size() + 1);
    }

    ofstream o(out);
    if (!o) fail("cannot write " + out);
    for (int k = 0; k < p.K; k++) {
        for (char m : routes[k]) o << m << ' ';
        o << "0\n";
    }
    o.close();

    int status = 0;
    for (int k = 0; k < p.K; k++)
        if (extra[k] > 0)
            cerr << "decoder: note: line " << k + 1 << " has " << extra[k]
                 << " coloured cell(s) beyond the decoded route (ignored)\n";
    if (p.scenario == 2) {
        vector<char> on((size_t)p.N * p.M, 0);
        for (int k = 0; k < p.K; k++) {
            int x = p.sx[k], y = p.sy[k];
            on[y * p.N + x] = 1;
            for (char m : routes[k]) {
                int d = m == 'L' ? 0 : m == 'R' ? 1 : m == 'U' ? 2 : 3;
                x += DX[d]; y += DY[d];
                on[y * p.N + x] = 1;
            }
        }
        for (auto& c : p.popular)
            if (!on[c.second * p.N + c.first]) {
                cerr << "decoder: WARNING: popular cell (" << c.first << "," << c.second
                     << ") is on no decoded route (coloured with line "
                     << (colour[c.second * p.N + c.first] + 1) << " but not on its path)\n";
                status = 3;
            }
    }
    cerr << "decoder: SAT -> wrote " << out << (status ? " (with violations, exit 3)" : "") << "\n";
    return status;
}
