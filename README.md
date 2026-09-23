# AI Pac-Man

## Project Overview

AI Pac-Man is a multi-agent adversarial maze intelligence project built on the foundations of the Berkeley CS188 Pac-Man search assignment. The project turns the traditional single-agent Pac-Man environment into a collaborative ghost AI system in which each ghost acts as an intelligent agent with shared information, tactical roles, and coordinated path planning.

The goal is to move beyond isolated, hard-coded ghost behavior and instead model a real-time cooperative decision system that searches, predicts, and restricts Pac-Man's movement through the maze.

---

## Core Objectives

- Eliminate redundant pursuit by coordinating ghost paths instead of letting agents overlap.
- Execute pincer and containment strategies through position prediction and route planning.
- Use search and heuristic methods such as DFS, BFS, UCS, and A* to generate tactical movement.
- Simulate adversarial intelligence in a discrete grid environment with real-time state updates.
- Expose AI reasoning in a visual interface through telemetry, roles, and path data.

---

## Why this project matters

Traditional Pac-Man implementations usually treat ghosts as independent behaviors. This project reframes them as a team of rational agents operating under a shared environment model.

Each ghost evaluates global board state, identifies strategic opportunities, and chooses a behavioral role based on the current scenario. The result is a stronger, more coherent adversarial simulation that resembles real multi-agent coordination rather than scripted motion.

---

## Theoretical Foundation

This project builds directly on the core ideas of AI search:

### 1. Agents and Environments

The environment is a fully observable grid-world with:

- discrete tile-based movement
- dynamic occupancy changes
- adversarial movement logic
- exact coordinates for both Pac-Man and ghosts

The ghosts are modeled as goal-based agents with shared perception and cooperative decision-making.

### 2. Search and Heuristics

A central part of the project is implementing optimal or near-optimal path planning with search methods such as:

- Depth-first search for exploration
- Breadth-first search for shortest path in unweighted graphs
- Uniform-cost search for weighted decisions
- A* search for efficient target-driven route finding

The standard evaluation function used in graph search is:

$$f(n) = g(n) + h(n)$$

where:

- $g(n)$ is the path cost from the start to node $n$
- $h(n)$ is the heuristic estimate to the goal

A common admissible heuristic is Manhattan distance:

$$h(n) = |x_1 - x_2| + |y_1 - y_2|$$

---

## Multi-Agent Role Allocation

The central coordinator assigns each ghost a role depending on the tactical state of the map.

### Direct Pursuer

The chaser executes a direct path search toward Pac-Man's current location, applying constant pressure and reducing escape space.

### Trajectory Interceptor

The interceptor predicts Pac-Man's future position by estimating velocity and aiming ahead of the player to anticipate turns and route advances.

### Choke-Point Blocker

This ghost identifies likely bottlenecks or corridors and moves to intercept Pac-Man at a narrow path, reducing his options.

### Perimeter Sweeper

This ghost covers alternate routes and patrols territory to prevent Pac-Man from escaping into open or previously cleared space.

To avoid ghost overlap and deadlocks, agents maintain reserved path priorities and treat high-priority movement as temporary occupancy for lower-priority agents.

---

## System Architecture

The project uses a modular architecture that mirrors modern AI game systems:

```text
Client / Visualization
        |
        v
WebSocket / State Sync
        |
        v
Game State Manager
        |
        v
Ghost Coordinator
        |
        +--> Chaser Agent
        +--> Interceptor Agent
        +--> Blocker Agent
        +--> Sweeper Agent
```

### Core components

- Game state manager: tracks maze layout, scores, and tick state
- Ghost coordinator: makes global strategic decisions
- Path planner: computes movement using search and heuristics
- Role allocator: assigns tactical responsibilities to each ghost
- Visualization layer: exposes agent decisions and movement traces

---

## Technology Stack

- Python 3.10+
- FastAPI for the backend
- WebSockets for live state synchronization
- NumPy for spatial computations and heuristics
- HTML5 Canvas / JavaScript for visualization

---

## Relationship to Berkeley Pac-Man Search

The local Pac-Man project extracted from the Berkeley CS188 archive provides the foundation for this repository:

- maze representation
- state transitions
- action planning
- search algorithm implementations
- heuristic design exercises

This AI Pac-Man project extends that foundation into a collaboration-heavy multi-agent adversarial system.

In short:

- Berkeley Pac-Man Project = search fundamentals in a maze
- AI Pac-Man = strategic multi-agent planning on top of those foundations

---

## Implementation Direction

The repository is organized to support an iterative build:

1. Understand the maze and action model.
2. Implement fundamental search algorithms.
3. Model ghost agent coordination.
4. Add role-based decision logic.
5. Add prediction and interception behavior.
6. Expose the system through a visual dashboard.

---

## Project Status

This repository currently contains the Pac-Man search foundation files pulled from the Berkeley archive, and the README has been reframed to describe the larger AI Pac-Man project concept built on top of those search primitives.

---

## Quick Start

Use the Pac-Man search project as the underlying engine and build on top of it with the following progression:

```bash
python pacman.py
python pacman.py -l tinyMaze -p SearchAgent
python pacman.py -l mediumMaze -p SearchAgent -a fn=bfs
python pacman.py -l bigMaze -z .5 -p SearchAgent -a fn=astar,heuristic=manhattanHeuristic
```

---

## Summary

AI Pac-Man is a project about turning ghost behavior from simple reactive logic into coordinated, strategic, adversarial intelligence. It leverages search-based planning as the mechanism for decision-making and builds toward a real-time multi-agent AI system.

The result is a conceptually richer version of Pac-Man—one where the enemies act like a team rather than isolated scripts.

