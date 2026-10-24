# AI Pac-Man - Pending Tasks Checklist

## Phase 1: Search (Completed)
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
- [x] ReflexAgent implementation
- [x] MinimaxAgent implementation
- [x] AlphaBetaAgent implementation
- [x] ExpectimaxAgent implementation
- [x] Better evaluation function
- [x] All multi-agent tests passing (25/25)

## Phase 3: Ghost Coordination & Strategic Planning (Completed)
- [x] **Ghost Coordinator Design** - Implement a centralized coordinator to orchestrate ghost behavior
- [x] **Role Allocation System** - Assign roles (Chaser, Interceptor, Blocker, Sweeper) dynamically based on game state
- [x] **Path Planning for Ghosts** - Implement search-based path planning for coordinated ghost movement
- [x] **Trajectory Prediction** - Predict Pac-Man's future position based on velocity and maze layout
- [x] **Pincer/Containment Strategies** - Implement coordinated encirclement tactics
- [x] **Path Priority & Collision Avoidance** - Prevent ghost overlap and deadlocks with reserved paths

## Phase 4: Advanced Coordination Features (In Progress)
- [x] **Shared Perception Model** - Ensure ghosts share global board state information
- [ ] **Tactical State Machine** - Implement role transitions based on Pac-Man's position/power-ups
- [ ] **Dynamic Strategy Switching** - Adapt coordination based on remaining food/capsules
- [x] **Scared Ghost Coordination** - Differentiate behavior when ghosts are scared vs hunting

## Phase 5: Visualization & Dashboard (Pending)
- [ ] **WebSocket/State Sync Backend** - Implement real-time game state broadcasting
- [ ] **FastAPI Backend** - Create API endpoints for game control and telemetry
- [ ] **HTML5 Canvas Visualization** - Build visual dashboard showing agent decisions
- [ ] **Telemetry Display** - Show ghost roles, planned paths, and target predictions
- [ ] **Path Tracing** - Visualize search paths and coordination strategies
- [ ] **Real-time Metrics** - Display coordination efficiency and strategy effectiveness

## Phase 6: Integration & Polish (Pending)
- [ ] **Integration Testing** - Test coordinated ghost system against various layouts
- [ ] **Performance Optimization** - Optimize search/path planning for real-time play
- [ ] **Configuration System** - Add tunable parameters for coordination strategies
- [ ] **Documentation** - Document coordination algorithms and architecture
- [ ] **Demo Layouts** - Create/test on strategic scenarios
