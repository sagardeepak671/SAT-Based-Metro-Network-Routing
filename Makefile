CXX ?= c++
CXXFLAGS ?= -std=c++11 -O2 -Wall -Wextra

.PHONY: all run test clean
all: encoder decoder

encoder: encoder.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

decoder: decoder.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

# The baseline stops at CNF generation.
run: encoder
	./run1.sh input

# Generate the regression cases (reproducible, fixed seed) and run
# encode -> solve -> compare against the expected SAT/UNSAT verdicts.
test: encoder decoder
	python3 testcase_gen.py --out tests
	python3 TESTER.py --tests tests

clean:
	rm -f encoder decoder input.satinput input.satoutput input.metromap
	rm -f tests/*.satinput tests/*.satoutput
