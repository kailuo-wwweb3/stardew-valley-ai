"""Phase 3 test: navigate from current position to a distant tile."""

import sys
sys.path.insert(0, ".")

from game_client import GameClient
from actions import Actions

client = GameClient()
actions = Actions(client)

# Get current state
state = client.get_state()
print(f"Current: ({state['tileX']},{state['tileY']}) in {state['location']}")

# Walk to the farmhouse door area (tile 3,11) or a target passed as args
if len(sys.argv) >= 3:
    tx, ty = int(sys.argv[1]), int(sys.argv[2])
else:
    # Default: walk to near the farmhouse door
    tx, ty = 3, 9

print(f"Target: ({tx},{ty})")
success = actions.walk_to(tx, ty)
print(f"Result: {'SUCCESS' if success else 'FAILED'}")
