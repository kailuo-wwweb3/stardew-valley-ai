"""
Stardew Valley AI Agent — event loop with state machine, safety overrides,
frustration counter, and WebSocket event listener.
"""

import sys
import time
import json
import threading
from enum import Enum

import websockets
import websockets.sync.client

from game_client import GameClient
from actions import Actions
from config import MOD_HTTP_URL

WSS_URL = "ws://127.0.0.1:7881/"

# Safety thresholds
BEDTIME_THRESHOLD = 2400        # 12:00 AM — head to bed
CRITICAL_TIME = 2500            # 1:00 AM — emergency
STAMINA_RESERVE = 15            # minimum stamina before stopping work
FRUSTRATION_LIMIT = 3           # same action repeated this many times → blocked

# Bed tile in FarmHouse (standard layout)
BED_TILE = (10, 5)


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"


class Agent:
    def __init__(self):
        self.client = GameClient()
        self.actions = Actions(self.client)
        self.status = AgentStatus.IDLE
        self.current_task = None

        # Frustration tracking
        self._last_action_key = None
        self._frustration_count = 0

        # WebSocket events
        self._events = []
        self._events_lock = threading.Lock()
        self._ws_thread = None
        self._running = False

        # Safety flags (set by WS events or polling)
        self._critical_time = False
        self._menu_open = False

    # ── WebSocket listener ─────────────────────────────────────────

    def _start_ws_listener(self):
        """Start background thread that listens for WebSocket events."""
        self._running = True
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def _ws_loop(self):
        """Connect to the C# WebSocket server and process events."""
        while self._running:
            try:
                with websockets.sync.client.connect(WSS_URL) as ws:
                    print("[WS] Connected to event firehose")
                    while self._running:
                        try:
                            msg = ws.recv(timeout=1.0)
                            event = json.loads(msg)
                            self._handle_ws_event(event)
                        except TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            break
            except (ConnectionRefusedError, OSError) as e:
                if self._running:
                    print(f"[WS] Connection failed ({e}), retrying in 3s...")
                    time.sleep(3)

    def _handle_ws_event(self, event: dict):
        """Process an incoming WebSocket event."""
        event_type = event.get("event", "")

        with self._events_lock:
            self._events.append(event)

        if event_type == "time_changed":
            game_time = event.get("time", 0)
            if game_time >= CRITICAL_TIME:
                self._critical_time = True
                print(f"[SAFETY] CRITICAL: {self._format_time(game_time)} reached — must sleep!")
            elif game_time >= BEDTIME_THRESHOLD:
                print(f"[SAFETY] Warning: it's {self._format_time(game_time)}, should head to bed")

        elif event_type == "menu_opened":
            self._menu_open = True

        elif event_type == "menu_closed":
            self._menu_open = False

        elif event_type == "location_changed":
            print(f"[EVENT] Location changed to: {event.get('location')}")

        elif event_type == "day_started":
            print(f"[EVENT] New day: {event.get('season')} {event.get('day')}, Year {event.get('year')}")
            self._critical_time = False

    def drain_events(self) -> list[dict]:
        """Return and clear all queued events."""
        with self._events_lock:
            events = self._events[:]
            self._events.clear()
        return events

    # ── Frustration counter ────────────────────────────────────────

    def track_action(self, action_key: str):
        """Track repeated actions. If the same action is attempted 3 times, set blocked."""
        if action_key == self._last_action_key:
            self._frustration_count += 1
            if self._frustration_count >= FRUSTRATION_LIMIT:
                print(f"[FRUSTRATION] Frustration limit reached. State set to blocked.")
                self.status = AgentStatus.BLOCKED
        else:
            self._last_action_key = action_key
            self._frustration_count = 1

    def reset_frustration(self):
        """Reset frustration counter (called on successful state change)."""
        self._last_action_key = None
        self._frustration_count = 0

    # ── Safety overrides ───────────────────────────────────────────

    def check_safety(self, state: dict) -> str | None:
        """Check for safety conditions. Returns an override action name or None."""
        # Critical time — must go to bed immediately
        if self._critical_time or state.get("timeOfDay", 0) >= CRITICAL_TIME:
            self._critical_time = True
            return "go_to_bed"

        # Low stamina
        if state.get("stamina", 999) <= STAMINA_RESERVE:
            print(f"[SAFETY] Stamina critically low ({state['stamina']})")
            return "conserve_stamina"

        # Menu is open — wait
        if state.get("isMenuOpen", False) or self._menu_open:
            return "wait_for_menu"

        return None

    def execute_safety_override(self, override: str):
        """Execute a safety override action."""
        if override == "go_to_bed":
            state = self.client.get_state()
            if state.get("location") == "FarmHouse":
                print("[SAFETY] Walking to bed...")
                self.actions.walk_to(*BED_TILE)
            else:
                print("[SAFETY] Not in FarmHouse — need to navigate home first")
                # For now, just flag it; Phase 5 LLM will handle multi-location nav

        elif override == "conserve_stamina":
            print("[SAFETY] Conserving stamina — setting status to idle")
            self.status = AgentStatus.IDLE

        elif override == "wait_for_menu":
            time.sleep(0.5)

    # ── Main loop ──────────────────────────────────────────────────

    def run(self):
        """Main agent loop."""
        print("=" * 50)
        print("  Stardew Valley AI Agent")
        print("=" * 50)

        self._start_ws_listener()

        # Wait for game to be ready
        print("Waiting for game connection...")
        while True:
            try:
                state = self.client.get_state()
                print(f"Connected! Location: {state['location']}, "
                      f"Time: {self._format_time(state['timeOfDay'])}")
                break
            except Exception:
                time.sleep(1)

        # Cache initial map
        self.actions.refresh_map(force=True)

        print(f"Agent status: {self.status.value}")
        print("Agent loop started. Press Ctrl+C to stop.\n")

        try:
            while True:
                self._tick()
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nAgent stopped.")
            self._running = False

    def _tick(self):
        """Single iteration of the agent loop."""
        # Get current state
        try:
            state = self.client.get_state()
        except Exception as e:
            print(f"[ERROR] Failed to get state: {e}")
            time.sleep(1)
            return

        # Check safety overrides first
        override = self.check_safety(state)
        if override:
            self.execute_safety_override(override)
            return

        # Drain and process WebSocket events
        events = self.drain_events()

        # State machine
        if self.status == AgentStatus.IDLE:
            # In Phase 5, the LLM will be called here to decide what to do.
            # For now, just report idle status periodically.
            pass

        elif self.status == AgentStatus.WORKING:
            # In Phase 5, this will execute the current task plan.
            pass

        elif self.status == AgentStatus.BLOCKED:
            # In Phase 5, the LLM will be called to reason about the blocker.
            print(f"[BLOCKED] Agent is blocked. Waiting for LLM integration (Phase 5).")
            time.sleep(2)

    # ── Utilities ──────────────────────────────────────────────────

    @staticmethod
    def _format_time(game_time: int) -> str:
        """Format game time integer to readable string."""
        hours = game_time // 100
        minutes = game_time % 100
        period = "AM" if hours < 12 else "PM"
        display_hours = hours % 12 or 12
        return f"{display_hours}:{minutes:02d} {period}"


if __name__ == "__main__":
    agent = Agent()
    agent.run()
