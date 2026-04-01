"""High-level actions: map caching, A* pathfinding, and walk_to."""

import time
import threading
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder

from game_client import GameClient
from config import HEARTBEAT_INTERVAL, PATH_POLL_INTERVAL


class Actions:
    """Provides high-level game actions built on the GameClient."""

    def __init__(self, client: GameClient):
        self.client = client
        self._cached_location = None
        self._cached_matrix = None
        self._map_width = 0
        self._map_height = 0

    def refresh_map(self, force: bool = False) -> None:
        """Fetch and cache the collision map. Refreshes on location change or if forced."""
        state = self.client.get_state()
        current_location = state["location"]

        if not force and self._cached_location == current_location and self._cached_matrix is not None:
            return

        print(f"Fetching map for {current_location}...")
        map_data = self.client.get_map()
        self._cached_location = map_data["location"]
        self._map_width = map_data["width"]
        self._map_height = map_data["height"]

        # Decode RLE into a 2D matrix (1 = walkable, 0 = blocked)
        rle = map_data["collisionRLE"]
        flat = []
        for run in rle:
            val = 1 if run["w"] else 0
            flat.extend([val] * run["c"])

        # Reshape into rows (row-major: top-to-bottom, left-to-right)
        self._cached_matrix = []
        for y in range(self._map_height):
            row_start = y * self._map_width
            self._cached_matrix.append(flat[row_start:row_start + self._map_width])

        print(f"Map cached: {self._map_width}x{self._map_height}, {sum(sum(r) for r in self._cached_matrix)} walkable tiles")

    def overlay_local_tiles(self, matrix: list[list[int]], local_tiles: list[dict]) -> list[list[int]]:
        """Overlay the 7x7 dynamic tile grid onto the cached matrix for local obstacle avoidance."""
        # Deep copy the matrix
        overlay = [row[:] for row in matrix]
        for tile in local_tiles:
            x, y = tile["x"], tile["y"]
            if 0 <= y < len(overlay) and 0 <= x < len(overlay[0]):
                overlay[y][x] = 1 if tile["walkable"] else 0
        return overlay

    def find_path(self, start_x: int, start_y: int, end_x: int, end_y: int) -> list[list[int]] | None:
        """Run A* pathfinding from start to end tile. Returns path as [[x,y], ...] or None."""
        if self._cached_matrix is None:
            self.refresh_map()

        # Bounds check
        if not (0 <= end_x < self._map_width and 0 <= end_y < self._map_height):
            print(f"Target ({end_x},{end_y}) out of bounds (map is {self._map_width}x{self._map_height})")
            return None
        if not (0 <= start_x < self._map_width and 0 <= start_y < self._map_height):
            print(f"Start ({start_x},{start_y}) out of bounds")
            return None

        # Get local tiles for dynamic overlay
        state = self.client.get_state()
        matrix = self.overlay_local_tiles(self._cached_matrix, state.get("localTiles", []))

        grid = Grid(matrix=matrix)
        start = grid.node(start_x, start_y)
        end = grid.node(end_x, end_y)

        finder = AStarFinder()
        path, _runs = finder.find_path(start, end, grid)

        if not path:
            print(f"No path found from ({start_x},{start_y}) to ({end_x},{end_y})")
            return None

        # Convert to [[x,y], ...] format
        return [[node.x, node.y] for node in path]

    def walk_to(self, target_x: int, target_y: int) -> bool:
        """Navigate to a target tile using A* pathfinding. Returns True if successful."""
        # Ensure map is cached
        self.refresh_map()

        # Get current position
        state = self.client.get_state()
        start_x, start_y = state["tileX"], state["tileY"]

        if start_x == target_x and start_y == target_y:
            print("Already at target")
            return True

        print(f"Planning path from ({start_x},{start_y}) to ({target_x},{target_y})...")
        path = self.find_path(start_x, start_y, target_x, target_y)
        if path is None:
            return False

        # Skip the first point (current position)
        path = path[1:]
        if not path:
            return True

        print(f"Walking {len(path)} tiles...")

        # Start walking
        self.client.walk_path(path)

        # Heartbeat + poll loop
        stop_heartbeat = threading.Event()

        def heartbeat_loop():
            while not stop_heartbeat.is_set():
                try:
                    self.client.heartbeat()
                except Exception:
                    pass
                stop_heartbeat.wait(HEARTBEAT_INTERVAL)

        hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        hb_thread.start()

        try:
            while True:
                time.sleep(PATH_POLL_INTERVAL)
                status = self.client.get_path_status()
                if not status["active"]:
                    break
        finally:
            stop_heartbeat.set()
            hb_thread.join(timeout=3)

        # Verify arrival
        state = self.client.get_state()
        arrived_x, arrived_y = state["tileX"], state["tileY"]
        success = arrived_x == target_x and arrived_y == target_y
        if success:
            print(f"Arrived at ({target_x},{target_y})")
        else:
            print(f"Stopped at ({arrived_x},{arrived_y}), target was ({target_x},{target_y})")
        return success
