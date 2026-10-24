# arcadeGhostAgents.py
# --------------------
# pacman.py's loadAgent() only searches modules named *gents.py, so this shim
# exposes the arcade-mode ghosts (defined in arcadeRules.py) to `--ghost`.
from arcadeRules import (ArcadeBlinky, ArcadePinky, ArcadeInky,  # noqa: F401
                         ArcadeClyde, ArcadeGhostTeam)
