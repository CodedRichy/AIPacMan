from game import Agent, Directions, Actions
from util import manhattanDistance, Queue

_coordinator_instance = None

class GhostCoordinator:
    def __init__(self, gameState=None):
        self.gameState = gameState
        self.roles = {}
        self.assignedTargets = {}
    
    def assignRoles(self, gameState):
        pacmanPos = gameState.getPacmanPosition()
        ghostPositions = gameState.getGhostPositions()
        numGhosts = len(ghostPositions)
        self.roles = {}
        self.assignedTargets = {}
        if numGhosts == 0:
            return
        ghostDists = [(i+1, manhattanDistance(pacmanPos, pos), pos) 
                      for i, pos in enumerate(ghostPositions)]
        ghostDists.sort(key=lambda x: x[1])
        if numGhosts >= 1:
            ghostIdx, dist, pos = ghostDists[0]
            self.roles[ghostIdx] = 'chaser'
            self.assignedTargets[ghostIdx] = pacmanPos
        if numGhosts >= 2:
            ghostIdx, dist, pos = ghostDists[1]
            self.roles[ghostIdx] = 'interceptor'
            self.assignedTargets[ghostIdx] = self.predictPacmanPosition(gameState)
        if numGhosts >= 3:
            ghostIdx, dist, pos = ghostDists[2]
            self.roles[ghostIdx] = 'blocker'
            chokePoint = self.findChokePoint(gameState)
            self.assignedTargets[ghostIdx] = chokePoint if chokePoint else pacmanPos
        if numGhosts >= 4:
            ghostIdx, dist, pos = ghostDists[3]
            self.roles[ghostIdx] = 'sweeper'
            sweepTarget = self.findSweepTarget(gameState)
            self.assignedTargets[ghostIdx] = sweepTarget if sweepTarget else pacmanPos
    
    def predictPacmanPosition(self, gameState, steps=4):
        pacmanPos = gameState.getPacmanPosition()
        current = pacmanPos
        for _ in range(steps):
            legal = gameState.getLegalActions(0)
            validMoves = [a for a in legal if a != Directions.STOP]
            if not validMoves:
                break
            bestMove = validMoves[0]
            dx, dy = Actions.directionToVector(bestMove)
            current = (int(current[0] + dx), int(current[1] + dy))
        return current
    
    def findChokePoint(self, gameState):
        walls = gameState.getWalls()
        pacmanPos = gameState.getPacmanPosition()
        width, height = walls.width, walls.height
        bestChoke = None
        bestScore = -1
        for x in range(1, width-1):
            for y in range(1, height-1):
                if walls[x][y] or (x,y) == pacmanPos:
                    continue
                exits = 0
                for dx,dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                    nx, ny = x+dx, y+dy
                    if 0 <= nx < width and 0 <= ny < height and not walls[nx][ny]:
                        exits += 1
                if exits <= 2:
                    dist = manhattanDistance(pacmanPos, (x,y))
                    score = (3 - exits) * 10 / (dist + 1)
                    if score > bestScore:
                        bestScore = score
                        bestChoke = (x,y)
        return bestChoke
    
    def findSweepTarget(self, gameState):
        food = gameState.getFood().asList()
        pacmanPos = gameState.getPacmanPosition()
        if not food:
            return pacmanPos
        foodSorted = sorted(food, key=lambda f: manhattanDistance(pacmanPos, f), reverse=True)
        return foodSorted[0]

class CoordinatedGhostTeam(Agent):
    def __init__(self, index):
        self.index = index
        global _coordinator_instance
        if _coordinator_instance is None:
            _coordinator_instance = GhostCoordinator(None)
    
    def getAction(self, state):
        global _coordinator_instance
        _coordinator_instance.assignRoles(state)
        target = _coordinator_instance.assignedTargets.get(self.index, state.getPacmanPosition())
        legalActions = state.getLegalActions(self.index)
        if not legalActions or (Directions.STOP in legalActions and len(legalActions) == 1):
            return Directions.STOP
        ghostPos = state.getGhostPosition(self.index)
        if ghostPos == target:
            bestAction = legalActions[0]
            bestDist = float('inf')
            for action in legalActions:
                if action == Directions.STOP:
                    continue
                dx, dy = Actions.directionToVector(action)
                nextPos = (int(ghostPos[0]+dx), int(ghostPos[1]+dy))
                dist = manhattanDistance(nextPos, state.getPacmanPosition())
                if dist < bestDist:
                    bestDist = dist
                    bestAction = action
            return bestAction
        walls = state.getWalls()
        width, height = walls.width, walls.height
        visited = set([ghostPos])
        queue = Queue()
        for action in legalActions:
            if action == Directions.STOP:
                continue
            dx, dy = Actions.directionToVector(action)
            nextPos = (int(ghostPos[0]+dx), int(ghostPos[1]+dy))
            if 0 <= nextPos[0] < width and 0 <= nextPos[1] < height and not walls[nextPos[0]][nextPos[1]]:
                if nextPos == target:
                    return action
                if nextPos not in visited:
                    visited.add(nextPos)
                    queue.push((nextPos, action))
        while not queue.isEmpty():
            currentPos, firstAction = queue.pop()
            for action in [Directions.NORTH, Directions.SOUTH, Directions.EAST, Directions.WEST]:
                dx, dy = Actions.directionToVector(action)
                nextPos = (int(currentPos[0]+dx), int(currentPos[1]+dy))
                if 0 <= nextPos[0] < width and 0 <= nextPos[1] < height:
                    if walls[nextPos[0]][nextPos[1]] or nextPos in visited:
                        continue
                    if nextPos == target:
                        return firstAction
                    visited.add(nextPos)
                    queue.push((nextPos, firstAction))
        bestAction = legalActions[0]
        bestDist = float('inf')
        for action in legalActions:
            if action == Directions.STOP:
                continue
            dx, dy = Actions.directionToVector(action)
            nextPos = (int(ghostPos[0]+dx), int(ghostPos[1]+dy))
            dist = manhattanDistance(nextPos, target)
            if dist < bestDist:
                bestDist = dist
                bestAction = action
        return bestAction
