"""Phase 1: Navigation & Environment tests.

Validates movement, A* pathfinding, and map transitions.
"""

import time

import pytest

from tests.helpers import wait_for_state, FARM_TEST_X, FARM_TEST_Y


@pytest.mark.phase1
class TestLocalMovement:
    """Basic tile-to-tile movement."""

    def test_walk_to_adjacent_tile(self, client, actions):
        state = client.get_state()
        start_x, start_y = state["tileX"], state["tileY"]
        target_x = start_x + 1

        success = actions.walk_to(target_x, start_y)
        assert success

        final = client.get_state()
        assert final["tileX"] == target_x
        assert final["tileY"] == start_y

    def test_walk_short_path(self, client, actions):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]
        target_x, target_y = sx + 3, sy + 2

        success = actions.walk_to(target_x, target_y)
        assert success

        final = client.get_state()
        assert final["tileX"] == target_x
        assert final["tileY"] == target_y

    def test_walk_already_at_target(self, client, actions):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]

        success = actions.walk_to(sx, sy)
        assert success


@pytest.mark.phase1
class TestObstacleAvoidance:
    """A* pathfinding around obstacles."""

    def test_pathfind_around_obstacle(self, client, actions):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]

        # Spawn a vertical wall of stones 2 tiles east
        for dy in range(-2, 3):
            client.spawn_object(sx + 2, sy + dy, "450")

        time.sleep(0.2)
        actions.refresh_map(force=True)

        # Walk to a tile 4 east — A* must route around the wall
        target_x = sx + 4
        success = actions.walk_to(target_x, sy)
        assert success

        final = client.get_state()
        assert final["tileX"] == target_x


@pytest.mark.phase1
@pytest.mark.slow
class TestMapTransitions:
    """Location changes when walking to map edges."""

    def test_farm_to_farmhouse(self, client, actions):
        # Warp near the FarmHouse door (entry at tile 64,15 on standard farm)
        client.warp("Farm", 64, 15)
        time.sleep(0.5)

        actions.refresh_map(force=True)

        # Walk north into the FarmHouse door
        actions.walk_to(64, 14)

        # Verify location changed to FarmHouse
        final = wait_for_state(
            client,
            lambda s: s["location"] == "FarmHouse",
            timeout=8.0
        )
        assert final["location"] == "FarmHouse"
