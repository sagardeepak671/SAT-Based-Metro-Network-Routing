#include <iostream>
#include <vector>
#include <set>
#include <utility>
#include <iomanip>
#include <fstream>
#include <map>
#include <algorithm> 
#include <sstream>
#include <string>
#include <array>
#include <chrono>
#define endl '\n'

using namespace std;
using namespace std::chrono;

struct PROBLEM{
    int senario;
    int N, M, K, J, P=0;
    vector<vector<int>> metro_lines; // (x1,y1,x2,y2)
    vector<vector<int>> popular_cells; // (x,y)
};

PROBLEM prob;
int N,M,K,J,P=0;
vector<vector<int>> GRID;

/* each cell will have x,y information and a color k information -> n*m*k */

//  buffered clause writing system
int BUFFER_SIZE = 10000; 
vector<vector<int>> CLAUSE_BUFFER;
ofstream cnf_file;
int total_clauses_written = 0;
stringstream write_buffer; // String buffer for batch writing

void flush_clauses() {
    if(CLAUSE_BUFFER.empty()) return;
    
    write_buffer.str(""); // Clear the string buffer
    write_buffer.clear();
    
    for(const vector<int>& clause : CLAUSE_BUFFER) { 
        if(clause.empty()) {
            write_buffer << "0\n";
            total_clauses_written++;
            continue;
        }
         
        if(clause.size() <= 2) { 
            for(int lit : clause) {
                write_buffer << lit << ' ';
            }
            write_buffer << "0\n";
            total_clauses_written++;
        } else { 
            set<int> unique_lits(clause.begin(), clause.end());
            for(int lit : unique_lits) {
                write_buffer << lit << ' ';
            }
            write_buffer << "0\n";
            total_clauses_written++;
        }
    } 
    cnf_file << write_buffer.str();
    CLAUSE_BUFFER.clear();
}

void add_clause(const vector<int>& clause) {
    CLAUSE_BUFFER.push_back(clause); 
    if((int)CLAUSE_BUFFER.size() >= BUFFER_SIZE) {
        flush_clauses();
    }
}

void open_cnf_file(string filename) {
    filename += ".satinput";
    cnf_file.open(filename);
    if(!cnf_file.is_open()) {
        cerr << "Error opening output file: " << filename << endl;
        exit(1);
    } 
    cnf_file << "p cnf                                                  \n";
    CLAUSE_BUFFER.clear();
    CLAUSE_BUFFER.reserve(BUFFER_SIZE);
    total_clauses_written = 0;
    write_buffer.str("");
    write_buffer.clear();
}

void close_cnf_file(string filename, int total_vars) {
    // Flush any remaining clauses
    flush_clauses();
    cnf_file.close();
    
    // Update header with actual counts
    filename += ".satinput";
    ifstream in(filename);
    stringstream buffer;
    string line;
    getline(in, line); // Skip old header
    buffer << "p cnf " << total_vars << " " << total_clauses_written << "\n";
    
    // Copy rest of file
    while(getline(in, line)) {
        buffer << line << "\n";
    }
    in.close();
    
    // Write back
    ofstream out(filename);
    out << buffer.str();
    out.close();
    
    // cout << "CNF file written: " << filename << endl;
    // cout << "Total variables: " << total_vars << endl;
    // cout << "Total clauses: " << total_clauses_written << endl;
}

vector<vector<vector<int>>> var_map; // var_map[x][y][k] = variable number

int next_aux_var;
int get_new_aux_var(){
    return next_aux_var++;
}

void read_PROBLEM(string filename){
    filename+=".city";
    ifstream file(filename);
    if(!file.is_open()){cerr << "Error opening file: " << filename << endl; exit(1);}
    string line;
    getline(file, line);
    prob.senario = stoi(line);
    getline(file, line);
    istringstream iss(line);
    iss>>prob.M>>prob.N>>prob.K>>prob.J;
    M=prob.M; N=prob.N; K=prob.K; J=prob.J;  
    if(prob.senario==2){
        iss>>prob.P;
        P=prob.P;
    }
    // OPTIMIZATION: Reserve capacity to avoid reallocations
    prob.metro_lines.reserve(prob.K);
    for(int i=0;i<prob.K;i++){
        getline(file,line);
        istringstream iss(line);
        int x1,y1,x2,y2;
        iss>>y1>>x1>>y2>>x2;
        prob.metro_lines.push_back({x1,y1,x2,y2});  
    }
    if(prob.senario==2){
        prob.popular_cells.reserve(prob.P);
        getline(file,line);
        istringstream iss_pop(line);
        for(int i=0;i<prob.P;i++){
            int x,y;
            iss_pop>>y>>x;
            prob.popular_cells.push_back({x,y});
        }
    }
    file.close();
}

void add_at_most_one_sequential(const vector<int>& xs) {
  int n = (int)xs.size();
  if (n <= 1) return;
  vector<int> s(n-1);
  for (int i = 0; i < n-1; ++i) s[i] = get_new_aux_var();

  // (¬x1 ∨ s1)
  add_clause({-xs[0], s[0]});
  for (int i = 1; i < n-1; ++i) {
    // (¬xi ∨ si)
    add_clause({-xs[i], s[i]});
    // (¬s(i-1) ∨ si)
    add_clause({-s[i-1], s[i]});
    // (¬xi ∨ ¬s(i-1))
    add_clause({-xs[i], -s[i-1]});
  }
  // (¬xn ∨ ¬s(n-1))
  add_clause({-xs[n-1], -s[n-2]});
}

 

void add_at_most_one(const vector<int>& xs){
    if(xs.size() <= 6){
        for(size_t i = 0; i < xs.size(); i++)
            for(size_t j = i + 1; j < xs.size(); j++)
                add_clause({-xs[i], -xs[j]});
    } else {
        add_at_most_one_sequential(xs);
    }
}

void G0(){
    // G0: each cell can be colored by at most one metro line (allows empty cells)
    for(int x=0;x<N;x++){
        for(int y=0;y<M;y++){ 
            // For this cell, at most one color can be chosen
            // Add pairwise exclusion clauses: (-vi OR -vj) for all i<j
            // if(GRID[x][y]>0)continue; // already colored in solution
            vector<int> color_vars;
            for(int k = 0; k < K; k++) {
                color_vars.push_back(var_map[x][y][k]);
            }
            add_at_most_one_sequential(color_vars);
            // for(int k1=0; k1<K; k1++){
            //     for(int k2=k1+1; k2<K; k2++){
            //         add_clause({-var_map[x][y][k1], -var_map[x][y][k2]});
            //     }
            // }
        }
    }
}

vector<vector<int>> PATH_GENERATOR(int x1, int y1, int x2, int y2, int k, int max_turns){
    vector<vector<int>> result;
    if((max_turns>=0&&prob.senario==2)||(max_turns==0&&prob.senario==1)){
        // straight line only
        if(x1 == x2){
           // horizontal
            vector<int> path;
            int path_len = abs(y2 - y1) + 1;
            path.reserve(path_len);
            for(int y = min(y1,y2); y <= max(y1,y2); y++){
                path.push_back(var_map[x1][y][k]);
            }
            result.push_back(path);
        } else if(y1 == y2){
            // vertical
            vector<int> path;
            int path_len = abs(x2 - x1) + 1;
            path.reserve(path_len);
            for(int x = min(x1,x2); x <= max(x1,x2); x++){
                path.push_back(var_map[x][y1][k]);
            }
            result.push_back(path);
        }
    }
     if((max_turns>=1&&prob.senario==2)||(max_turns==1&&prob.senario==1)){
        // 2 patterns: horizontal-then-vertical or vertical-then-horizontal
        // HV: (x1,y1) -> (x2,y1) -> (x2,y2)
        vector<int> path1;
        int path_len1 = abs(x2 - x1) + abs(y2 - y1) + 1;
        path1.reserve(path_len1);
        for(int x = min(x1,x2); x <= max(x1,x2); x++){
            path1.push_back(var_map[x][y1][k]);
        }
        for(int y = min(y1,y2); y <= max(y1,y2); y++){
            path1.push_back(var_map[x2][y][k]);
        }
        result.push_back(path1);

        // VH: (x1,y1) -> (x1,y2) -> (x2,y2)
        vector<int> path2;
        path2.reserve(path_len1);
        for(int y = min(y1,y2); y <= max(y1,y2); y++){
            path2.push_back(var_map[x1][y][k]);
        }
        for(int x = min(x1,x2); x <= max(x1,x2); x++){
            path2.push_back(var_map[x][y2][k]);
        }
        result.push_back(path2);
    }
     if((max_turns >= 2 && prob.senario == 2) || (max_turns == 2 && prob.senario == 1)){
        // 2-turn paths: HVH or VHV
        // HVH: go horizontal to column my, vertical to row mx, horizontal to (x2,y2)
        for(int my = 0; my < M; my++){
            for(int mx = 0; mx < N; mx++){
                if(mx==x1&&prob.senario==2)continue;
                vector<int> path;
                // seg1: (x1,y1) -> (x1,my)
                for(int y = min(y1,my); y <= max(y1,my); y++){
                    path.push_back(var_map[x1][y][k]);
                }
                // seg2: (x1,my) -> (mx,my)
                for(int x = min(x1,mx); x <= max(x1,mx); x++){
                    path.push_back(var_map[x][my][k]);
                }
                // seg3: (mx,my) -> (mx,y2)
                for(int y = min(my,y2); y <= max(my,y2); y++){
                    path.push_back(var_map[mx][y][k]);
                }
                // check endpoint
                if(mx == x2){ 
                    result.push_back(path);
                }
            }
        }
        
        // VHV: go vertical to row mx, horizontal to column my, vertical to (x2,y2)
        for(int mx = 0; mx < N; mx++){
            for(int my = 0; my < M; my++){
                if(my==y1 && prob.senario==2)continue;
                vector<int> path;
                // seg1: (x1,y1) -> (mx,y1)
                for(int x = min(x1,mx); x <= max(x1,mx); x++){
                    path.push_back(var_map[x][y1][k]);
                }
                // seg2: (mx,y1) -> (mx,my)
                for(int y = min(y1,my); y <= max(y1,my); y++){
                    path.push_back(var_map[mx][y][k]);
                }
                // seg3: (mx,my) -> (x2,my)
                for(int x = min(mx,x2); x <= max(mx,x2); x++){
                    path.push_back(var_map[x][my][k]);
                }
                // check endpoint
                if(my == y2){ 
                    result.push_back(path);
                }
            }
        }
    }
     if(max_turns >= 3){
        // 3-turn paths: HVHV or VHVH (4 segments, 3 direction changes)
        // HVHV: horizontal -> vertical -> horizontal -> vertical
        // Path: (x1,y1) -H-> (x1,my1) -V-> (mx1,my1) -H-> (mx1,my2) -V-> (x2,my2)
        // Final point (x2,my2) must equal (x2,y2), so my2 == y2
        for(int my1 = 0; my1 < M; my1++){
            for(int mx1 = 0; mx1 < N; mx1++){
                if(mx1==x1 && prob.senario==2)continue;
                for(int my2 = 0; my2 < M; my2++){
                    if(my2==my1 && prob.senario==2)continue;
                    // if(my1==my2)continue;
                    // Skip if rectangular loop is formed:
                    // HVHV forms a rectangle if we return to the starting horizontal line
                    // This happens when mx1 == x1 AND my2 is between y1 and my1
                    vector<int> path;
                    // seg1: (x1,y1) horizontal to (x1,my1)
                    bool invalid_path = false;
                    for(int y = min(y1,my1); y <= max(y1,my1); y++){
                        path.push_back(var_map[x1][y][k]); 
                    }
                    // seg2: (x1,my1) vertical to (mx1,my1)
                    for(int x = min(x1,mx1); x <= max(x1,mx1); x++){
                        path.push_back(var_map[x][my1][k]); 
                    }
                    // seg3: (mx1,my1) horizontal to (mx1,my2)
                    for(int y = min(my1,my2); y <= max(my1,my2); y++){
                        path.push_back(var_map[mx1][y][k]); 
                    }
                    // seg4: (mx1,my2) vertical to (x2,my2)
                    for(int x = min(mx1,x2); x <= max(mx1,x2); x++){
                        if(x==x1 && (my2>= min(y1,my1) && my2 <= max(y1,my1))&& prob.senario==2) { invalid_path = true; break;} // skip rectangular loop
                        path.push_back(var_map[x][my2][k]); 
                    }
                    // check endpoint: must end at (x2,y2)
                    if(my2 == y2 && !invalid_path){ 
                        result.push_back(path);
                    }
                }
            }
        }
        
        // VHVH: vertical -> horizontal -> vertical -> horizontal
        // Path: (x1,y1) -V-> (mx1,y1) -H-> (mx1,my1) -V-> (mx2,my1) -H-> (mx2,y2)
        // Final point (mx2,y2) must equal (x2,y2), so mx2 == x2
        for(int mx1 = 0; mx1 < N; mx1++){
            for(int my1 = 0; my1 < M; my1++){
                if(my1==y1 && prob.senario==2)continue;
                for(int mx2 = 0; mx2 < N; mx2++){
                    if(mx2==mx1 && prob.senario==2)continue;
                    // if(mx1==mx2)continue;
                    // Skip if rectangular loop is formed:
                    // VHVH forms a rectangle if we return to the starting vertical line
                    // This happens when my1 == y1 AND mx2 is between x1 and mx1
                     
                    vector<int> path;
                    bool invalid_path = false;
                    // seg1: (x1,y1) vertical to (mx1,y1)
                    for(int x = min(x1,mx1); x <= max(x1,mx1); x++){ 
                        path.push_back(var_map[x][y1][k]);
                    }
                    // seg2: (mx1,y1) horizontal to (mx1,my1)
                    for(int y = min(y1,my1); y <= max(y1,my1); y++){ 
                        path.push_back(var_map[mx1][y][k]);
                    }
                    // seg3: (mx1,my1) vertical to (mx2,my1)
                    for(int x = min(mx1,mx2); x <= max(mx1,mx2); x++){ 
                        path.push_back(var_map[x][my1][k]);
                    }
                    // seg4: (mx2,my1) horizontal to (mx2,y2)
                    for(int y = min(my1,y2); y <= max(my1,y2); y++){ 
                        if(y==y1 && (mx2>= min(x1,mx1) && mx2 <= max(x1,mx1)) && prob.senario==2) { invalid_path = true; break;} // skip rectangular loop
                        path.push_back(var_map[mx2][y][k]);
                    }
                    // check endpoint: must end at (x2,y2)
                    if(mx2 == x2 && !invalid_path){ 
                        result.push_back(path);
                    }
                }
            }
        }
    } 
    // NO PRUNING: Keep all paths to guarantee correctness 
    return result;
}

// Track which path variables include each popular cell
map<pair<int,int>, vector<int>> popular_to_pathvars; // (px,py) -> list of pathVars that include this cell


 

// Adds clauses to enforce that exactly one variable in xs is true.
// Combines at least one clause with at most one sequential encoding.
void add_exactly_one(const vector<int>& xs) {
  if (xs.empty()) return;
  add_clause(xs);                    // at least one
  add_at_most_one_sequential(xs);   // at most one
}


void AT_LEAST_ONE_PATH(const vector<vector<int>>& paths, int metro_line_k){
    // If no valid paths exist for this metro line, problem is UNSAT
    if(paths.empty()){
        // Add empty clause (always false) to make formula UNSAT
        add_clause({});
        return;
    }
    
    //  Useing set to eliminate duplicate paths
    set<vector<int>> unique_paths;
    for(const auto& path : paths){
        unique_paths.insert(path);
    }
    
    vector<int> pathVars;
    pathVars.reserve(unique_paths.size());
    
    // SCENARIO 2: Track which cells belong to which paths (for reverse constraint)
    map<int, vector<int>> cell_to_paths; // cellVar -> list of pathVars containing this cell
    
    for(const auto& path : unique_paths){
        int pathVar = get_new_aux_var();
        pathVars.push_back(pathVar);
        
        // pathVar => all cells in path must be colored
        for(int cellVar : path){
            add_clause({-pathVar, cellVar});
            
            // Track which paths contain this cell
            if(prob.senario == 2){
                cell_to_paths[cellVar].push_back(pathVar);
            }
        }
        
        // SCENARIO 2: Track which popular cells are in this path
        if(prob.senario == 2){
            for(const auto& cell : prob.popular_cells){
                if(cell.size() >= 2){
                    int px = cell[0];
                    int py = cell[1];
                    if(px >= 0 && px < N && py >= 0 && py < M){
                        int pop_var = var_map[px][py][metro_line_k];
                        if(find(path.begin(), path.end(), pop_var) != path.end()){
                            popular_to_pathvars[{px, py}].push_back(pathVar);
                        }
                    }
                }
            }
        }
    }
    
    // SCENARIO 2: Add reverse constraint - if a cell is colored, at least one path containing it must be chosen
    if(prob.senario == 2){
        for(const auto& pair : cell_to_paths){
            int cellVar = pair.first;
            const vector<int>& paths_with_cell = pair.second;
            
            // cellVar => (path1 OR path2 OR ... OR pathN)
            // which is: -cellVar OR path1 OR path2 OR ... OR pathN
            vector<int> clause;
            clause.push_back(-cellVar);
            for(int pv : paths_with_cell){
                clause.push_back(pv);
            }
            add_clause(clause);
        }
        // BUG FIX: the loop above only covers cells that occur in some candidate
        // path of this line. A cell on NO candidate path had no constraint at
        // all, so its colour variable was free; the popular-cell clause
        // "(v1 OR ... OR vK)" could then be satisfied by colouring an
        // unreachable popular cell with a line that never visits it, and the
        // CNF was SAT for impossible instances. The implication
        // "coloured k => some chosen path of k contains it" for such a cell has
        // an empty right-hand side, i.e. the unit clause (-cellVar).
        for(int x = 0; x < N; x++){
            for(int y = 0; y < M; y++){
                int cellVar = var_map[x][y][metro_line_k];
                if(cell_to_paths.find(cellVar) == cell_to_paths.end()){
                    add_clause({-cellVar});
                }
            }
        }
    } 
    
    // Scenario 1: At least one pathVar must be true
    // Scenario 2: Exactly one pathVar must be true
    if(prob.senario == 2){
        // EXACTLY ONE path must be chosen
        // At least one: (p1 OR p2 OR ... OR pn)
        add_clause(pathVars);
        add_at_most_one_sequential(pathVars);
        // At most one: for each pair (pi, pj), add clause (-pi OR -pj)
        // for(size_t i = 0; i < pathVars.size(); i++){
        //     for(size_t j = i + 1; j < pathVars.size(); j++){
        //         add_clause({-pathVars[i], -pathVars[j]});
        //     }
        // }
    } else {
        // SCENARIO 1: At least one pathVar must be true
        add_clause(pathVars);
    }
}

void POPULAR_CELL_COVERAGE(){
    // Scenario 2: Each popular cell must be on at least one CHOSEN path
    if(prob.senario != 2) return;
    
    for(const auto& cell : prob.popular_cells){
        if(cell.size() < 2) continue;
        int px = cell[0];
        int py = cell[1];
        
        // Bounds check
        if(px < 0 || px >= N || py < 0 || py >= M) continue;
        
        // Get all path variables that include this popular cell
        pair<int, int> key = make_pair(px, py);
        if(popular_to_pathvars.find(key) != popular_to_pathvars.end()){
            const vector<int>& pathvars = popular_to_pathvars[key];
            if(!pathvars.empty()){
                // At least one of these path variables must be true
                // This ensures the popular cell is on a CHOSEN path
                add_clause(pathvars);
                
                // ADDITIONAL CONSTRAINT: If a popular cell is colored by metro k,
                // then at least one chosen path of metro k must include it
                // For each metro line k, collect paths that include this cell
                map<int, vector<int>> metro_paths; // metro_k -> paths including this cell
                
                for(int k = 0; k < K; k++){
                    int color_var = var_map[px][py][k];
                    // vector<int> paths_with_this_color;
                    
                    // // Find all paths from popular_to_pathvars that use color k
                    // for(int pv : pathvars){
                    //     // Check if this pathvar corresponds to metro line k
                    //     // (We need to track this - for now we'll add a global constraint)
                    //     paths_with_this_color.push_back(pv);
                    // }
                    
                    // If cell is colored k, at least one path of k must include it
                    // color_var => (path1 OR path2 OR ...)
                    // which is: -color_var OR path1 OR path2 OR ...
                    if(!pathvars.empty()){
                        vector<int> clause;
                        clause.push_back(-color_var);
                        for(int pv : pathvars){
                            clause.push_back(pv);
                        }
                        add_clause(clause);
                    }
                }
            }
        }
        // ALSO: Exactly one color constraint for popular cell (px, py)
        vector<int> color_vars;
        for(int k = 0; k < K; k++){
            color_vars.push_back(var_map[px][py][k]);
        }
        // At least one color: (v1 OR v2 OR ... OR vK)
        add_clause(color_vars);
        add_at_most_one_sequential(color_vars);
        // At most one color: for each pair (vi, vj), add (-vi OR -vj)
        // for(int i = 0; i < K; i++){
        //     for(int j = i + 1; j < K; j++){
        //         add_clause({-color_vars[i], -color_vars[j]});
        //     }
        // }
    }
}


// ============================================================================
// General-J encoding (segment automaton).  Replaces path enumeration.
//
// A route with at most J turns is a chain of at most J+1 straight segments.
// For every line k, cell c, direction d and segment index t in 0..J:
//   E[k][c][d][t]  <=>  line k moves from c to its neighbour in direction d
//                       while on segment t (i.e. after exactly t turns).
// Local constraints only:
//   * start: exactly one outgoing edge, on segment 0, no incoming edge;
//   * end:   exactly one incoming edge, no outgoing edge;
//   * other cells: coloured k  <=>  one edge arrives; coloured k => one edge
//     leaves; at most one incoming and one outgoing edge;
//   * an edge leaving c (d,t) needs an edge arriving at c either straight
//     (d,t) or perpendicular (d',t-1); an edge arriving (d,t) needs an edge
//     leaving straight (d,t) or perpendicular (d',t+1).  U-turns are never
//     allowed.
// Consequence: the cells coloured k are exactly one simple route from start
// to end with <= J turns.  (Degree <= 1 rules out branching; a stray path
// would need a coloured cell without incoming edge; a closed loop has >= 4
// turns, so the segment index would have to grow around it and still return
// to its first value -- impossible.)  Size: ~4*N*M*K*(J+1) variables and
// ~40*N*M*K*(J+1) short clauses: linear in J, independent of path counts.
// ============================================================================
static const int DDX[4] = {-1, 1, 0, 0};   // internal axes: x = row, y = column
static const int DDY[4] = {0, 0, -1, 1};
vector<int> EDGE;                           // edge variables, 0 = edge does not exist
int CELLS;

inline int cell_id(int x, int y){ return x * M + y; }
inline bool in_grid(int x, int y){ return x >= 0 && x < N && y >= 0 && y < M; }
inline int edge_var(int k, int c, int d, int t){
    return EDGE[((size_t)((size_t)k * CELLS + c) * 4 + d) * (J + 1) + t];
}
// edge arriving at cell (x,y) in direction d on segment t (from the neighbour opposite to d)
inline int in_edge_var(int k, int x, int y, int d, int t){
    int px = x - DDX[d], py = y - DDY[d];
    if(!in_grid(px, py)) return 0;
    return edge_var(k, cell_id(px, py), d, t);
}
inline bool perpendicular(int a, int b){ return (a < 2) != (b < 2); }

void ENCODE_GENERAL_J(){
    CELLS = N * M;
    EDGE.assign((size_t)K * CELLS * 4 * (J + 1), 0);
    for(int k = 0; k < K; k++)
        for(int x = 0; x < N; x++)
            for(int y = 0; y < M; y++)
                for(int d = 0; d < 4; d++)
                    if(in_grid(x + DDX[d], y + DDY[d]))
                        for(int t = 0; t <= J; t++)
                            EDGE[((size_t)((size_t)k * CELLS + cell_id(x, y)) * 4 + d) * (J + 1) + t] = get_new_aux_var();

    for(int k = 0; k < K; k++){
        int sx = prob.metro_lines[k][0], sy = prob.metro_lines[k][1];
        int ex = prob.metro_lines[k][2], ey = prob.metro_lines[k][3];
        for(int x = 0; x < N; x++){
            for(int y = 0; y < M; y++){
                int c = cell_id(x, y);
                int xc = var_map[x][y][k];
                vector<int> outs, ins;
                for(int d = 0; d < 4; d++)
                    for(int t = 0; t <= J; t++){
                        int o = edge_var(k, c, d, t); if(o) outs.push_back(o);
                        int i = in_edge_var(k, x, y, d, t); if(i) ins.push_back(i);
                    }
                bool is_start = (x == sx && y == sy), is_end = (x == ex && y == ey);
                if(is_start){
                    for(int v : ins) add_clause({-v});                       // nothing arrives at the start
                    vector<int> first;
                    for(int d = 0; d < 4; d++)
                        for(int t = 0; t <= J; t++){
                            int o = edge_var(k, c, d, t);
                            if(!o) continue;
                            if(t == 0) first.push_back(o); else add_clause({-o});   // leave on segment 0
                        }
                    if(first.empty()) add_clause({});                        // isolated cell: impossible
                    else add_clause(first);
                    add_at_most_one(first);
                    continue;
                }
                if(is_end){
                    for(int v : outs) add_clause({-v});                      // nothing leaves the end
                    if(ins.empty()) add_clause({});
                    else add_clause(ins);                                    // exactly one arrival
                    add_at_most_one(ins);
                    continue;
                }
                // coloured  <=>  some edge arrives ;  coloured  =>  some edge leaves
                vector<int> cl; cl.push_back(-xc);
                for(int v : ins) cl.push_back(v);
                add_clause(cl);
                for(int v : ins) add_clause({-v, xc});
                cl.clear(); cl.push_back(-xc);
                for(int v : outs) cl.push_back(v);
                add_clause(cl);
                for(int v : outs) add_clause({-v, xc});
                add_at_most_one(ins);
                add_at_most_one(outs);
                // segment bookkeeping across the cell
                for(int d = 0; d < 4; d++){
                    for(int t = 0; t <= J; t++){
                        int o = edge_var(k, c, d, t);
                        if(o){   // leaving (d,t)  =>  arrived straight (d,t) or turned from (d',t-1)
                            cl.clear(); cl.push_back(-o);
                            int i = in_edge_var(k, x, y, d, t); if(i) cl.push_back(i);
                            if(t > 0)
                                for(int dp = 0; dp < 4; dp++)
                                    if(perpendicular(d, dp)){ int i2 = in_edge_var(k, x, y, dp, t - 1); if(i2) cl.push_back(i2); }
                            add_clause(cl);
                        }
                        int i = in_edge_var(k, x, y, d, t);
                        if(i){   // arriving (d,t)  =>  leaves straight (d,t) or turns to (d',t+1)
                            cl.clear(); cl.push_back(-i);
                            int o2 = edge_var(k, c, d, t); if(o2) cl.push_back(o2);
                            if(t < J)
                                for(int dp = 0; dp < 4; dp++)
                                    if(perpendicular(d, dp)){ int o3 = edge_var(k, c, dp, t + 1); if(o3) cl.push_back(o3); }
                            add_clause(cl);
                        }
                    }
                }
            }
        }
    }
}

// Legacy path-enumeration encoding (J <= 3 only); kept for cross-checking via --legacy.
void SOLVE(){
    // each line can have at most J turns (J>=3)
    // Strategy: enumerate all possible J-turn paths from (x1,y1) to (x2,y2)
    // A J-turn path has J+1 segments with J direction changes
    // We'll use auxiliary variables: pathVar_i means "path i is chosen"
    // Then: (pathVar_1 OR pathVar_2 OR ... pathVar_n) must be true
    // AND if pathVar_i is true, then all cells in path i must be colored with k
    for(int k=0;k<K;k++){
        int x1=prob.metro_lines[k][0];
        int y1=prob.metro_lines[k][1];
        int x2=prob.metro_lines[k][2];
        int y2=prob.metro_lines[k][3];

        vector<vector<int>> paths = PATH_GENERATOR(x1, y1, x2, y2, k, J);
        AT_LEAST_ONE_PATH(paths, k); // Pass metro line index k
    }
    
    // Scenario 2: Ensure each popular cell is on at least one chosen path
    POPULAR_CELL_COVERAGE();
}
 

int main(int argc, char* argv[]){
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);
    
    time_point<high_resolution_clock> start_time = high_resolution_clock::now(); 
    
    // Accept filename from command line argument, default to "input" if not provided
    string filename = "input";
    bool legacy = false;
    for(int i = 1; i < argc; i++){
        string a = argv[i];
        if(a == "--legacy") legacy = true;
        else filename = a;
    }
    read_PROBLEM(filename);
    // PRINT_BEAUTIFUL();
    next_aux_var = N*M*K + 1; 
    var_map.resize(N, vector<vector<int>>(M, vector<int>(K, 0)));
    GRID.resize(N, vector<int>(M, 0)); // 0 means uncolored
    
    // Open CNF file for buffered writing
    open_cnf_file(filename);
    
    int var_count = 0; 
    for(int x = 0; x < N; x++){
        for(int y = 0; y < M; y++){
            for(int k = 0; k < K; k++){
                var_count++;
                var_map[x][y][k] = var_count;
                int sx = prob.metro_lines[k][0];
                int sy = prob.metro_lines[k][1];
                int ex = prob.metro_lines[k][2];
                int ey = prob.metro_lines[k][3];
                if((x == sx && y == sy) || (x == ex && y == ey)){
                    GRID[x][y] = k + 1; // pre-colored with k+1 
                    add_clause({var_map[x][y][k]});  
                }
            }
        }
    }
    G0();  // At most one color per cell
    if(legacy){
        if(J > 3){ cerr << "encoder: --legacy supports J <= 3 only" << endl; return 2; }
        SOLVE();                 // old path enumeration
    } else {
        ENCODE_GENERAL_J();      // general J
    }
    // now adding the popular cells constraints for scenario 2
    if(prob.senario == 2){
        // at least one color for each popular cell
        for(const vector<int>& cell : prob.popular_cells){
            if(cell.size() < 2) continue;
            int x = cell[0];
            int y = cell[1];
            if(x < 0 || x >= N || y < 0 || y >= M   ) continue;
            vector<int> color_vars;
            for(int k = 0; k < K; k++){
                color_vars.push_back(var_map[x][y][k]);
            }
            add_clause(color_vars);
        }
    }
    // Close file and finalize
    int total_vars = next_aux_var - 1;
    close_cnf_file(filename, total_vars);

    
    time_point<high_resolution_clock> end_time = high_resolution_clock::now();
    milliseconds duration = duration_cast<milliseconds>(end_time - start_time);
    cout << "ENCODING_TIME: " << fixed << setprecision(3) << duration.count() / 1000.0 << " seconds" << endl;
    return 0;
}