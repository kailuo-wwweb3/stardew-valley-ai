# Stardew Valley AI Agent — Implementation Plan

## Rules of Engagement for the AI Agent

1. **Strictly Sequential:** Do NOT attempt multiple phases at once. You must complete the current Phase, ask the user to verify the "Testing Criteria", and WAIT for user approval before beginning the next Phase.
2. **State Tracking:** Update `.harness/03_current_task.md` whenever you start or finish a phase. **Overwrite the file completely** to reflect only the current state and immediate next steps. Do not append an endless log to preserve context window limits.
3. **Do Not Hallucinate APIs:** Stardew Valley SMAPI is a specific, complex framework. Do not guess how to read map layers, collision logic, or player stats. Rely strictly on the code snippets provided in the `.harness/04_mechanics_*.md` files. If a required property is missing from the harness, stop and ask the user to provide the SMAPI documentation or game decompile snippet.

---

## Goal

Build an AI agent that autonomously plays Stardew Valley by reading game state via a SMAPI mod and making decisions via the Claude API.

## Architecture

```text
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   SMAPI Mod      │  HTTP   │   Python Agent   │  HTTP   │   LLM (Claude)   │
│   (C# in-game)   │◄───────►│  (orchestrator)  │◄───────►│   (decision AI)  │
│                  │         │                  │   API   │                  │
│ - HTTP (Commands)│  WSS    │ - HTTP Client    │         │ - High-level plan│
│ - WSS (Firehose) │───────► │ - WSS Listener   │         │ - Reason blockers│
│ - Execute paths  │         │ - A* Pathfinding │         │                  │
│ - Sub-tile move  │         │ - Event loop     │         │                  │
│ - Safety checks  │         │ - Frustration    │         │                  │
└──────────────────┘         └──────────────────┘         └──────────────────┘
         │                            │
    Runs inside                 Runs as separate
    game process                Python process
    on local machine            
    on port 7880 (HTTP)
    and 7881 (WSS)
```

## Prerequisites

Before starting implementation:

1. **Install .NET 6.0+ SDK** — required to compile the C# SMAPI mod.
2. **Install SMAPI** — the Stardew Valley modding framework.
3. **Verify SMAPI works** — launch Stardew Valley via SMAPI.
4. **Locate key paths on macOS**:
   - Game install: `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/`
   - Mods folder: `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/`

---

## Phase 0: Project Bootstrapping

**Goal:** Scaffold the empty repository and establish the modular AI control harness.

**Scope:**
* Create the `.harness/` directory and populate the Markdown files (`01_goal.md`, `03_current_task.md`, `05_target_files.md`).
* Create the modular mechanics files: `04_mechanics_core.md`, `04_mechanics_farming.md`, `04_mechanics_navigation.md`.
* Create the empty `mod/` and `agent/` directories.
* Set up the Python virtual environment and `requirements.txt`.

**Testing Criteria (Definition of Done):**
1. The file tree exactly matches the "Project Structure" section below.
2. `.harness/03_current_task.md` is updated to state Phase 0 is complete and the agent is waiting to begin Phase 1.

---

## Phase 1: Read-Only Mod Infrastructure (The Eyes)

**Goal:** Establish the C# project, start the background HTTP listener, and serialize the game state into JSON.

**Scope:**
* `StardewAgent.csproj` & `manifest.json`.
* `ModEntry.cs` (Background thread for HTTP server).
* `GameStateService.cs` (Capture player pos, stamina, time, compressed 7x7 local tile grid).
* Add `isMenuOpen` flag. 
* Add an endpoint (`/map`) to dump the *entire* navigable collision matrix when requested. Use **Run-Length Encoding (RLE)** serialization (e.g., `[{"walkable": true, "count": 45}, ...]`) to prevent massive JSON bloat and C# lag on large maps like the Farm.

**Testing Criteria (Definition of Done):**
1. Launch the game via SMAPI. Mod loads without console errors.
2. Open a terminal and run: `curl http://127.0.0.1:7880/state`.
3. **Success:** You receive a valid JSON response containing `isMenuOpen`, coordinates, and stamina. 
4. Open the shipping bin in-game and run the curl command again.
5. **Success:** `isMenuOpen` returns `true`.
6. Run: `curl http://127.0.0.1:7880/map`.
7. **Success:** You receive an RLE-serialized representation of the current location's collision data.

---

## Phase 2: Action Execution & Safety (The Hands)

**Goal:** Allow the mod to accept POST requests to queue actions, manage the sub-tile pathing array, and execute tool usage safely.

**Scope:**
* `ActionService.cs` (Tool use, directional facing context, stamina depletion checks).
* `ModEntry.cs` (Add `_activePath` execution in `UpdateTicked`, Heartbeat monitor, return `202 Accepted` for async POSTs).
* Add POST route parsing to the HTTP listener.

**Testing Criteria (Definition of Done):**
1. Stand on the farm in-game. Use Postman or curl to send a POST request with `{"type": "use_tool", "targetX": [x], "targetY": [y]}`.
2. **Success:** The character physically turns to face the target coordinates and swings their tool.
3. Send a POST request with a short, 3-tile path array.
4. **Success:** The character walks smoothly to the destination and stops. Force-close the terminal during the walk; the Heartbeat monitor must stop the character after 5 seconds.

---

## Phase 3: Python Client & Full-Map Pathfinding (The Nervous System)

**Goal:** Build the Python HTTP wrapper, cache the location map, and build long-distance A* pathfinding. Test without the LLM.

**Scope:**
* `game_client.py` (Wrapper for requests. Use synchronous `httpx` with a strict 2.0 second timeout).
* `actions.py` (Fetch and cache the full map collision matrix on location change **and upon the start of a new day at 0600**. Overlay the 7x7 dynamic grid for local obstacle avoidance. Calculate A* using the combined matrix).

**Testing Criteria (Definition of Done):**
1. Create a temporary script: `test_navigation.py`.
2. Hardcode a command: `actions.walk_to(distant_x, distant_y)` (e.g., from farmhouse to the south exit).
3. **Success:** The script fetches the full map, calculates the long-distance path, sends it to the C# mod, and the character navigates successfully.

---

## Phase 4: State Machine, Overrides, & WebSockets (The Reflexes)

**Goal:** Implement the event loop, safety overrides, frustration counters, and augment with a WebSocket firehose.

**Scope:**
* `agent.py` (The `while True` loop tracking `idle`, `working`, and `blocked` statuses).
* Time and Stamina safety overrides.
* **Frustration Counter:** If the agent attempts the exact same action/path 3 times without a state change, force `agent_status = "blocked"`.
* **Hybrid WebSocket Event Firehose:** Do NOT rewrite the HTTP client. Augment it. Open a background WebSocket server in C# and a listener thread in Python. C# broadcasts one-way events (`{"event": "time_changed", "time": 2500}`, `damage_taken`, `menu_opened`) to trigger Python interrupts instantly.

**Testing Criteria (Definition of Done):**
1. Run the Python loop.
2. Change the time in-game: `debug time 2500` (1:00 AM).
3. **Success:** The WebSocket fires the event, the Python terminal instantly prints "CRITICAL: 1:00 AM reached", and fires an HTTP command to walk to bed.
4. Manually force the script to repeat a failed action 3 times.
5. **Success:** Python terminal prints "Frustration limit reached. State set to blocked."

---

## Phase 5: Event-Driven LLM Integration (The Brain)

**Goal:** Connect Claude to reason about blockers and plan tasks efficiently.

**Scope:**
* `ai_brain.py` (Prompt construction, token compression, Claude API integration).
* Hook `ai_brain.decide()` into the `agent.py` loop. The LLM is ONLY called when the status is `idle` or `blocked`.
* Contextual loading: Only read `04_mechanics_farming.md` if the overarching day plan involves farming.

**Testing Criteria (Definition of Done):**
1. Spawn a rock directly in front of the player on their path.
2. **Success:** The agent tries to walk, hits the rock, increments the frustration counter, and enters the `blocked` state.
3. The LLM is queried, recognizes the blocker, and returns a JSON payload choosing the "Pickaxe" targeting the rock.
4. The agent breaks the rock, returns to `idle`, and the LLM plans the next step.

---

## Project Structure & Harness Engineering

The modular `.harness/` directory isolates domain knowledge and explicitly controls the AI's context boundaries.

```text
stardew-valley-ai/
├── .harness/                        
│   ├── 01_goal.md                   
│   ├── 03_current_task.md           # Update this per Phase. Overwrite, do not append.
│   ├── 04_mechanics_core.md         # Time formats, movement, stamina, exact SMAPI code snippets
│   ├── 04_mechanics_farming.md      # Crop IDs, growth times, watering logic
│   ├── 04_mechanics_navigation.md   # A* logic, map transitions, collision data formats
│   └── 05_target_files.md           # Explicit file paths Claude is allowed to edit
├── PLAN.md                          # this file
├── mod/                             # Phase 1, 2, & 4: SMAPI C# mod
│   └── StardewAgent/
│       ├── StardewAgent.csproj
│       ├── manifest.json
│       ├── ModEntry.cs              
│       ├── GameStateService.cs      
│       ├── ActionService.cs         
│       └── Models/                  
├── agent/                           # Phase 3, 4, & 5: Python orchestrator
│   ├── game_client.py               
│   ├── agent.py                     
│   ├── actions.py                   
│   ├── ai_brain.py                  
│   ├── config.py                    
│   └── requirements.txt
└── venv/                            
```

## Dependencies to Install

```bash
# .NET SDK (for SMAPI mod)
brew install dotnet

# Python packages
cd stardew-valley-ai
python3 -m venv venv
source venv/bin/activate
pip install httpx websockets anthropic pathfinding
```