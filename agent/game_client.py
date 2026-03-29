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
