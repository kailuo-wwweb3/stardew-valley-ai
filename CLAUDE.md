# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

### C# SMAPI Mod
```bash
cd mod/StardewAgent && dotnet build
```
Requires .NET 6.0 SDK (`brew install dotnet`) and SMAPI installed. Build auto-deploys to the SMAPI Mods folder via `Pathoschild.Stardew.ModBuildConfig`.

### Python Agent
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r agent/requirements.txt
cp .env.example .env  # then fill in API key
cd agent && python agent.py
```
Requires Stardew Valley running via SMAPI with the mod loaded.

### Testing
```bash
# Navigation test (game must be running)
cd agent && python test_navigation.py [target_x] [target_y]

# Manual endpoint tests
curl http://127.0.0.1:7880/state
curl http://127.0.0.1:7880/map
curl -X POST http://127.0.0.1:7880/action -d '{"type":"walk_path","path":[[10,9],[11,9]]}'
curl -X POST http://127.0.0.1:7880/action -d '{"type":"use_tool","targetX":10,"targetY":9,"tool":"Axe"}'
```

## Architecture

Three-process architecture: game (C# mod) ↔ orchestrator (Python) ↔ LLM API.

**C# Mod** (`mod/StardewAgent/`) runs inside the game process:
- `ModEntry.cs` — HTTP server (port 7880) + WebSocket server (port 7881), path execution in `UpdateTicked` (~60 ticks/sec), heartbeat monitor (5s timeout)
- `GameStateService.cs` — State snapshots (player pos, stamina, time, 7x7 local tile grid) and RLE-encoded full collision maps
- `ActionService.cs` — Tool use with facing direction, stamina checks, tile-to-pixel path conversion
- `WebSocketServer.cs` — One-way event broadcast (time_changed, location_changed, menu_opened/closed, day_started, inventory_changed)

**Python Agent** (`agent/`) runs as a separate process:
- `game_client.py` — Synchronous httpx wrapper for all mod endpoints
- `actions.py` — Map caching (RLE decode), A* pathfinding with local tile overlay, `walk_to()` with heartbeat thread
- `agent.py` — Main loop with state machine (idle/working/blocked), safety overrides (bedtime at 2500, stamina ≤ 15), frustration counter (3 repeats → blocked), WebSocket listener thread
- `ai_brain.py` — Multi-provider LLM (Anthropic/OpenAI/DeepSeek via `LLM_PROVIDER` env var), contextual mechanics loading from `.harness/04_mechanics_*.md`

**Thread safety:** HTTP requests signal the game thread via `ManualResetEventSlim`; game state is only read on the game tick. The Python agent runs a daemon WebSocket listener thread and spawns daemon heartbeat threads per walk.

## Key conventions

- **Tile ↔ pixel:** `tile * 64` = pixel position. Player `Tile` property uses rounding, so pixel paths use `tile * 64` (not `tile * 64 + 32`).
- **Game time:** Integer format — 600 = 6:00 AM, 2400 = midnight, 2500 = 1:00 AM (critical).
- **Facing direction:** 0=up, 1=right, 2=down, 3=left.
- **RLE format:** `[{"w": true, "c": 5}, {"w": false, "c": 2}]` — row-major scan.
- **LLM responses:** Must be a single JSON object with `action`, target fields, and `reason`.

## Harness files

`.harness/` contains domain knowledge fed to the LLM contextually:
- `04_mechanics_core.md` — Time, movement, stamina, SMAPI entry point snippets
- `04_mechanics_farming.md` — Crop IDs, soil states, tool usage code
- `04_mechanics_navigation.md` — Collision checks, A* setup, map transitions

These are loaded by `ai_brain.py` based on keyword matching in the current context.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`.
