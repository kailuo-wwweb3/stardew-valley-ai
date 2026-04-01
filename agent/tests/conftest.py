"""Pytest fixtures for Stardew Valley E2E tests.

Requires the game to be running with SMAPI and the StardewAgent mod loaded.
"""

import os
import sys
import time

import pytest

# Allow imports from the agent package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game_client import GameClient
from actions import Actions
from tests.helpers import FARM_TEST_X, FARM_TEST_Y, FARM_TEST_RADIUS


@pytest.fixture(scope="session")
def client():
    """Single GameClient for the entire test session."""
    c = GameClient()
    state = c.get_state()
    assert "tileX" in state, "Game not responding correctly"
    return c


@pytest.fixture(scope="session")
def actions(client):
    """Single Actions instance for the session."""
    return Actions(client)


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Before every test: freeze time, warp to farm, clear the test area."""
    client.freeze_time(True)
    client.warp("Farm", FARM_TEST_X, FARM_TEST_Y)
    time.sleep(0.3)
    client.clear_area(FARM_TEST_X, FARM_TEST_Y, FARM_TEST_RADIUS)
    time.sleep(0.1)
    yield
