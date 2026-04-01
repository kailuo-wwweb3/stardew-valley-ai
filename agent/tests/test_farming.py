"""Phase 3: Farming Cycle tests.

Validates tilling, planting, watering, and harvesting.
"""

import time

import pytest

from tests.helpers import wait_for_state


@pytest.mark.phase3
class TestFarmingCycle:
    """Till, plant, water, harvest."""

    def test_till_soil(self, client):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]
        target_x, target_y = sx + 1, sy

        client.use_tool(target_x, target_y, "Hoe")

        def soil_tilled(s):
            tile = next(
                (t for t in s["localTiles"] if t["x"] == target_x and t["y"] == target_y),
                None
            )
            return tile is not None and tile["feature"] == "HoeDirt"

        wait_for_state(client, soil_tilled, timeout=5.0)

    def test_water_soil(self, client):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]
        target_x, target_y = sx + 1, sy

        # Till first
        client.use_tool(target_x, target_y, "Hoe")
        time.sleep(1.0)

        # Water
        client.use_tool(target_x, target_y, "Watering Can")

        # Verify watered flag
        def soil_watered(s):
            tile = next(
                (t for t in s["localTiles"] if t["x"] == target_x and t["y"] == target_y),
                None
            )
            return tile is not None and tile.get("watered") is True

        wait_for_state(client, soil_watered, timeout=5.0)

    def test_plant_seed(self, client):
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]
        target_x, target_y = sx + 1, sy

        # Till
        client.use_tool(target_x, target_y, "Hoe")
        time.sleep(1.0)

        # Add parsnip seeds to inventory
        client.add_item("(O)472", 5)
        time.sleep(0.2)

        # Plant by interacting with the seed selected
        client.interact(target_x, target_y, item_name="Parsnip Seeds")

        # Verify crop appeared
        def crop_planted(s):
            tile = next(
                (t for t in s["localTiles"] if t["x"] == target_x and t["y"] == target_y),
                None
            )
            return tile is not None and tile.get("hasCrop") is True

        wait_for_state(client, crop_planted, timeout=5.0)

    def test_full_farming_cycle(self, client):
        """Integration: till -> plant -> water -> verify state."""
        state = client.get_state()
        sx, sy = state["tileX"], state["tileY"]
        tx, ty = sx + 1, sy

        # Till
        client.use_tool(tx, ty, "Hoe")
        time.sleep(1.0)

        # Add seeds
        client.add_item("(O)472", 1)
        time.sleep(0.2)

        # Count seeds before planting
        before_state = client.get_state()
        seed_count_before = sum(
            i["stack"] for i in before_state.get("inventory", [])
            if "Parsnip" in i.get("name", "")
        )

        # Plant with seed selected
        client.interact(tx, ty, item_name="Parsnip Seeds")
        time.sleep(0.5)

        # Water
        client.use_tool(tx, ty, "Watering Can")

        # Verify tile has a watered crop
        def crop_watered(s):
            tile = next(
                (t for t in s["localTiles"] if t["x"] == tx and t["y"] == ty),
                None
            )
            return (
                tile is not None
                and tile.get("hasCrop") is True
                and tile.get("watered") is True
            )

        final = wait_for_state(client, crop_watered, timeout=5.0)

        # Verify seed was consumed from inventory
        seed_count_after = sum(
            i["stack"] for i in final.get("inventory", [])
            if "Parsnip" in i.get("name", "")
        )
        assert seed_count_after < seed_count_before
