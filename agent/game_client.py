"""HTTP client wrapper for the Stardew Valley SMAPI mod."""

import httpx
from config import MOD_HTTP_URL, HTTP_TIMEOUT


class GameClient:
    """Synchronous HTTP client for communicating with the SMAPI mod."""

    def __init__(self):
        self._client = httpx.Client(base_url=MOD_HTTP_URL, timeout=HTTP_TIMEOUT)

    def get_state(self) -> dict:
        """Fetch current game state."""
        resp = self._client.get("/state")
        resp.raise_for_status()
        return resp.json()

    def get_map(self) -> dict:
        """Fetch full collision map (RLE encoded)."""
        resp = self._client.get("/map", timeout=10.0)
        resp.raise_for_status()
        return resp.json()

    def use_tool(self, target_x: int, target_y: int, tool: str = None) -> dict:
        """Use a tool at the target tile."""
        payload = {"type": "use_tool", "targetX": target_x, "targetY": target_y}
        if tool:
            payload["tool"] = tool
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def walk_path(self, path: list[list[int]]) -> dict:
        """Start walking a path. Returns 202 if accepted."""
        payload = {"type": "walk_path", "path": path}
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def heartbeat(self) -> dict:
        """Send heartbeat to keep path walking alive."""
        resp = self._client.post("/heartbeat")
        resp.raise_for_status()
        return resp.json()

    def get_path_status(self) -> dict:
        """Check active path progress."""
        resp = self._client.get("/pathstatus")
        resp.raise_for_status()
        return resp.json()

    def stop(self) -> dict:
        """Cancel active path."""
        resp = self._client.post("/stop")
        resp.raise_for_status()
        return resp.json()

    def freeze_time(self, frozen: bool = True) -> dict:
        """Freeze or unfreeze the in-game clock."""
        resp = self._client.post("/freeze-time", json={"frozen": frozen})
        resp.raise_for_status()
        return resp.json()

    def clear_area(self, center_x: int, center_y: int, radius: int = 5) -> dict:
        """Remove all objects and terrain features within radius of center tile."""
        payload = {"type": "clear_area", "centerX": center_x, "centerY": center_y, "radius": radius}
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def interact(self, target_x: int, target_y: int, item_name: str = None) -> dict:
        """Right-click interact with a tile. If item_name given, select that item first (for planting)."""
        payload = {"type": "interact", "targetX": target_x, "targetY": target_y}
        if item_name:
            payload["itemName"] = item_name
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def spawn_object(self, tile_x: int, tile_y: int, object_id: str) -> dict:
        """Spawn a game object at a tile (e.g. object_id='450' for stone)."""
        payload = {"type": "spawn_object", "targetX": tile_x, "targetY": tile_y, "objectId": object_id}
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def add_item(self, item_id: str, count: int = 1) -> dict:
        """Add an item to the player's inventory (e.g. item_id='(O)472' for parsnip seeds)."""
        payload = {"type": "add_item", "itemId": item_id, "count": count}
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()

    def warp(self, location: str, tile_x: int, tile_y: int) -> dict:
        """Warp the player to a location and tile."""
        payload = {"type": "warp", "targetX": tile_x, "targetY": tile_y, "locationName": location}
        resp = self._client.post("/action", json=payload)
        resp.raise_for_status()
        return resp.json()
