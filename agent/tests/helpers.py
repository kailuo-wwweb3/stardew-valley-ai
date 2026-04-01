"""Shared test helpers and constants."""

import time


# Known clear area on the standard farm
FARM_TEST_X = 44
FARM_TEST_Y = 12
FARM_TEST_RADIUS = 5


def wait_for_state(client, condition, timeout=5.0, poll=0.1):
    """Poll /state until condition(state) returns True, or raise TimeoutError."""
    deadline = time.time() + timeout
    last_state = None
    while time.time() < deadline:
        last_state = client.get_state()
        if condition(last_state):
            return last_state
        time.sleep(poll)
    # One final check
    last_state = client.get_state()
    if condition(last_state):
        return last_state
    raise TimeoutError(
        f"Condition not met within {timeout}s. "
        f"Last state: tile=({last_state.get('tileX')},{last_state.get('tileY')}), "
        f"location={last_state.get('location')}"
    )
