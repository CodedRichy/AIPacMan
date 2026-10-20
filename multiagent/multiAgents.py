# multiAgents.py
# --------------
# Licensing Information:  You are free to use or extend these projects for
# educational purposes provided that (1) you do not distribute or publish
# solutions, (2) you retain this notice, and (3) you provide clear
# attribution to UC Berkeley, including a link to http://ai.berkeley.edu.
# 
# Attribution Information: The Pacman AI projects were developed at UC Berkeley.
# The core projects and autograders were primarily created by John DeNero
# (denero@cs.berkeley.edu) and Dan Klein (klein@cs.berkeley.edu).
# Student side autograding was added by Brad Miller, Nick Hay, and
# Pieter Abbeel (pabbeel@cs.berkeley.edu).


from util import manhattanDistance
from game import Directions
import random, util

from game import Agent
from pacman import GameState

class ReflexAgent(Agent):
    """
    A reflex agent chooses an action at each choice point by examining
    its alternatives via a state evaluation function.

    The code below is provided as a guide.  You are welcome to change
    it in any way you see fit, so long as you don't touch our method
    headers.
    """


    def getAction(self, gameState: GameState):
        """
        You do not need to change this method, but you're welcome to.

        getAction chooses among the best options according to the evaluation function.

        Just like in the previous project, getAction takes a GameState and returns
        some Directions.X for some X in the set {NORTH, SOUTH, WEST, EAST, STOP}
        """
        # Collect legal moves and successor states
        legalMoves = gameState.getLegalActions()

        # Choose one of the best actions
        scores = [self.evaluationFunction(gameState, action) for action in legalMoves]
        bestScore = max(scores)
        bestIndices = [index for index in range(len(scores)) if scores[index] == bestScore]
        chosenIndex = random.choice(bestIndices) # Pick randomly among the best

        "Add more of your code here if you want to"

        return legalMoves[chosenIndex]

    def evaluationFunction(self, currentGameState: GameState, action):
        """
        Design a better evaluation function here.

        The evaluation function takes in the current and proposed successor
        GameStates (pacman.py) and returns a number, where higher numbers are better.

        The code below extracts some useful information from the state, like the
        remaining food (newFood) and Pacman position after moving (newPos).
        newScaredTimes holds the number of moves that each ghost will remain
        scared because of Pacman having eaten a power pellet.

        Print out these variables to see what you're getting, then combine them
        to create a masterful evaluation function.
        """
        # Useful information you can extract from a GameState (pacman.py)
        successorGameState = currentGameState.generatePacmanSuccessor(action)
        newPos = successorGameState.getPacmanPosition()
        newFood = successorGameState.getFood()
        newGhostStates = successorGameState.getGhostStates()
        newScaredTimes = [ghostState.scaredTimer for ghostState in newGhostStates]

        score = successorGameState.getScore()

        # Reward moving closer to the nearest remaining food.
        foodList = newFood.asList()
        if foodList:
            score += 1.0 / (min(manhattanDistance(newPos, food) for food in foodList) + 1)

        # Strongly avoid ghosts, unless they are scared (then seek them out).
        for ghostState, scaredTime in zip(newGhostStates, newScaredTimes):
            ghostDist = manhattanDistance(newPos, ghostState.getPosition())
            if scaredTime > 0:
                score += 2.0 / (ghostDist + 1)
            elif ghostDist <= 1:
                score -= 1000
            else:
                score -= 1.0 / ghostDist

        return score

def scoreEvaluationFunction(currentGameState: GameState):
    """
    This default evaluation function just returns the score of the state.
    The score is the same one displayed in the Pacman GUI.

    This evaluation function is meant for use with adversarial search agents
    (not reflex agents).
    """
    return currentGameState.getScore()

class MultiAgentSearchAgent(Agent):
    """
    This class provides some common elements to all of your
    multi-agent searchers.  Any methods defined here will be available
    to the MinimaxPacmanAgent, AlphaBetaPacmanAgent & ExpectimaxPacmanAgent.

    You *do not* need to make any changes here, but you can if you want to
    add functionality to all your adversarial search agents.  Please do not
    remove anything, however.

    Note: this is an abstract class: one that should not be instantiated.  It's
    only partially specified, and designed to be extended.  Agent (game.py)
    is another abstract class.
    """

    def __init__(self, evalFn = 'scoreEvaluationFunction', depth = '2'):
        self.index = 0 # Pacman is always agent index 0
        self.evaluationFunction = util.lookup(evalFn, globals())
        self.depth = int(depth)

class MinimaxAgent(MultiAgentSearchAgent):
    """
    Your minimax agent (question 2)
    """

    def minimax(self, gameState: GameState, depth, agentIndex):
        if depth == 0 or gameState.isWin() or gameState.isLose():
            return self.evaluationFunction(gameState)

        legalActions = gameState.getLegalActions(agentIndex)
        if not legalActions:
            return self.evaluationFunction(gameState)

        if agentIndex == 0:
            return max(
                self.minimax(gameState.generateSuccessor(agentIndex, action), depth, 1)
                for action in legalActions
            )

        nextAgent = agentIndex + 1
        nextDepth = depth
        if agentIndex == gameState.getNumAgents() - 1:
            nextAgent = 0
            nextDepth = depth - 1

        return min(
            self.minimax(gameState.generateSuccessor(agentIndex, action), nextDepth, nextAgent)
            for action in legalActions
        )

    def getAction(self, gameState: GameState):
        """
        Returns the minimax action from the current gameState using self.depth
        and self.evaluationFunction.
        """
        legalActions = gameState.getLegalActions(0)
        if not legalActions:
            return Directions.STOP

        bestAction = None
        bestScore = float('-inf')
        for action in legalActions:
            nextState = gameState.generateSuccessor(0, action)
            score = self.minimax(nextState, self.depth, 1)
            if score > bestScore:
                bestScore = score
                bestAction = action
        return bestAction

class AlphaBetaAgent(MultiAgentSearchAgent):
    """
    Your minimax agent with alpha-beta pruning (question 3)
    """

    def alphabeta(self, gameState: GameState, depth, agentIndex, alpha, beta):
        if depth == 0 or gameState.isWin() or gameState.isLose():
            return self.evaluationFunction(gameState)

        legalActions = gameState.getLegalActions(agentIndex)
        if not legalActions:
            return self.evaluationFunction(gameState)

        if agentIndex == 0:
            value = float('-inf')
            for action in legalActions:
                value = max(value, self.alphabeta(gameState.generateSuccessor(agentIndex, action), depth, 1, alpha, beta))
                if value > beta:
                    return value
                alpha = max(alpha, value)
            return value

        nextAgent = agentIndex + 1
        nextDepth = depth
        if agentIndex == gameState.getNumAgents() - 1:
            nextAgent = 0
            nextDepth = depth - 1

        value = float('inf')
        for action in legalActions:
            value = min(value, self.alphabeta(gameState.generateSuccessor(agentIndex, action), nextDepth, nextAgent, alpha, beta))
            if value < alpha:
                return value
            beta = min(beta, value)
        return value

    def getAction(self, gameState: GameState):
        """
        Returns the minimax action using self.depth and self.evaluationFunction
        """
        legalActions = gameState.getLegalActions(0)
        if not legalActions:
            return Directions.STOP

        bestAction = None
        bestScore = float('-inf')
        alpha = float('-inf')
        beta = float('inf')
        for action in legalActions:
            score = self.alphabeta(gameState.generateSuccessor(0, action), self.depth, 1, alpha, beta)
            if score > bestScore:
                bestScore = score
                bestAction = action
            alpha = max(alpha, bestScore)
        return bestAction

class ExpectimaxAgent(MultiAgentSearchAgent):
    """
      Your expectimax agent (question 4)
    """

    def expectimax(self, gameState: GameState, depth, agentIndex):
        if depth == 0 or gameState.isWin() or gameState.isLose():
            return self.evaluationFunction(gameState)

        legalActions = gameState.getLegalActions(agentIndex)
        if not legalActions:
            return self.evaluationFunction(gameState)

        if agentIndex == 0:
            return max(
                self.expectimax(gameState.generateSuccessor(agentIndex, action), depth, 1)
                for action in legalActions
            )

        nextAgent = agentIndex + 1
        nextDepth = depth
        if agentIndex == gameState.getNumAgents() - 1:
            nextAgent = 0
            nextDepth = depth - 1

        values = [
            self.expectimax(gameState.generateSuccessor(agentIndex, action), nextDepth, nextAgent)
            for action in legalActions
        ]
        return sum(values) / float(len(values))

    def getAction(self, gameState: GameState):
        """
        Returns the expectimax action using self.depth and self.evaluationFunction

        All ghosts should be modeled as choosing uniformly at random from their
        legal moves.
        """
        legalActions = gameState.getLegalActions(0)
        if not legalActions:
            return Directions.STOP

        bestAction = None
        bestScore = float('-inf')
        for action in legalActions:
            nextState = gameState.generateSuccessor(0, action)
            score = self.expectimax(nextState, self.depth, 1)
            if score > bestScore:
                bestScore = score
                bestAction = action
        return bestAction

def betterEvaluationFunction(currentGameState: GameState):
    """
    Your extreme ghost-hunting, pellet-nabbing, food-gobbling, unstoppable
    evaluation function (question 5).

    DESCRIPTION: Combines the game score with: proximity to the nearest food
    (reciprocal Manhattan distance), distance from active ghosts (penalized,
    with a large penalty when adjacent), and proximity to scared ghosts
    (rewarded so Pacman chases them).  Because Q5 is graded with an
    expectimax agent, this is a leaf evaluation function rather than a
    reflex heuristic.
    """
    if currentGameState.isWin():
        return float('inf')
    if currentGameState.isLose():
        return float('-inf')

    pos = currentGameState.getPacmanPosition()
    food = currentGameState.getFood().asList()
    ghostStates = currentGameState.getGhostStates()
    scaredTimes = [ghostState.scaredTimer for ghostState in ghostStates]

    score = currentGameState.getScore()

    if food:
        score += 1.5 / (min(manhattanDistance(pos, f) for f in food) + 1)

    for ghostState, scaredTime in zip(ghostStates, scaredTimes):
        ghostDist = manhattanDistance(pos, ghostState.getPosition())
        if scaredTime > 0:
            score += 3.0 / (ghostDist + 1)
        elif ghostDist <= 1:
            score -= 500
        else:
            score -= 2.0 / ghostDist

    return score

# Abbreviation
better = betterEvaluationFunction
