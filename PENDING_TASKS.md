# AI Pac-Man - Pending Tasks Checklist

## Phase 1: Search (Completed)
> Status: done. Verified by autograder tests per earlier notes (26/25 as recorded; not re-run in this pass).
- [x] Understand maze and action model
- [x] Implement Depth-First Search (DFS)
- [x] Implement Breadth-First Search (BFS)
- [x] Implement Uniform-Cost Search (UCS)
- [x] Implement A* Search
- [x] Corners problem implementation
- [x] Corners heuristic (MST-based)
- [x] Food search / All-food heuristic (MST-based)
- [x] Closest dot search
- [x] All search tests passing (26/25)

## Phase 2: Multi-Agent (Completed)
> Status: done. 25/25 autograder result is as recorded earlier; not re-run in this pass. Expectimax/AlphaBeta depth 2 run in the benchmark without errors.
- [x] ReflexAgent implementation
- [x] MinimaxAgent implementation
- [x] AlphaBetaAgent implementation
- [x] ExpectimaxAgent implementation
- [x] Better evaluation function
- [x] All multi-agent tests passing (25/25)

## Phase 3: Ghost Coordination & Strategic Planning (Completed)
> Status: implemented; verified to run (integration tests, no illegal moves, no freezes). NOT verified as effective: reservation never fires (0/4302 checks in an instrumented run) and the enhanced team is a weaker hunter than the base team. See benchmarks/BASELINE.md and docs/ARCHITECTURE.md.
- [x] **Ghost Coordinator Design** - Implement a centralized coordinator to orchestrate ghost behavior
- [x] **Role Allocation System** - Assign roles (Chaser, Interceptor, Blocker, Sweeper) dynamically based on game state
- [x] **Path Planning for Ghosts** - Implement search-based path planning for coordinated ghost movement
- [x] **Trajectory Prediction** - Predict Pac-Man's future position based on velocity and maze layout
- [x] **Pincer/Containment Strategies** - Implement coordinated encirclement tactics
- [x] **Path Priority & Collision Avoidance** - Prevent ghost overlap and deadlocks with reserved paths

## Phase 4: Advanced Coordination Features (Completed)
> Status: implemented; verified to run; effectiveness measured NEGATIVE. TRAP_AMBUSH is the most common tactical state but has no behavior attached; strategy switching only retargets the sweeper. Shared perception and scared scatter run but have no measured benefit.
- [x] **Shared Perception Model** - Ensure ghosts share global board state information
- [x] **Tactical State Machine** - Implement role transitions based on Pac-Man's position/power-ups
- [x] **Dynamic Strategy Switching** - Adapt coordination based on remaining food/capsules
- [x] **Scared Ghost Coordination** - Differentiate behavior when ghosts are scared vs hunting

## Phase 5: Visualization & Dashboard (Pending)
> Status: not done on this branch (dashboard is being built on a separate branch; nothing here is verified).
- [ ] **WebSocket/State Sync Backend** - Implement real-time game state broadcasting
- [ ] **FastAPI Backend** - Create API endpoints for game control and telemetry
- [ ] **HTML5 Canvas Visualization** - Build visual dashboard showing agent decisions
- [ ] **Telemetry Display** - Show ghost roles, planned paths, and target predictions
- [ ] **Path Tracing** - Visualize search paths and coordination strategies
- [ ] **Real-time Metrics** - Display coordination efficiency and strategy effectiveness

## Phase 6: Integration & Polish (In progress)
> Status: harness, tests, docs, demo layouts and profile are done and verified by running them. The config module exists but is NOT wired into the ghost files. Performance optimization is not done (profile only).
- [x] **Integration Testing** - `tests/test_integration.py` (4 teams x 10 layouts x 2 seeds: no exceptions, no illegal actions, no frozen-ghost stalls); `python3 -m unittest discover -s tests -v`
- [x] **Benchmark harness** - `benchmarks/run_benchmark.py`, baseline in `benchmarks/BASELINE.md`
- [ ] **Performance Optimization** - profiled (`benchmarks/PROFILE.md`); ghost decisions cost about 0.2 ms each, so no urgent hotspot; nothing optimized
- [~] **Configuration System** - `multiagent/ghostConfig.py` written and tested; not wired in (`docs/CONFIG_WIRING.md`)
- [x] **Documentation** - `docs/ARCHITECTURE.md`, `docs/CONFIG_WIRING.md`, `docs/DEMO_LAYOUTS.md`
- [x] **Demo Layouts** - six `multiagent/layouts/demo_*.lay`, load and play with every team
- [ ] **Make the Phase 3/4 features actually help** - fix reservation reset key, give TRAP_AMBUSH a behavior, re-benchmark
