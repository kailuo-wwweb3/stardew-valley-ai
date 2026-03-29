# Goal

Build an AI agent that autonomously plays Stardew Valley by reading game state via a SMAPI mod and making decisions via the Claude API.

## Architecture

- **SMAPI Mod (C#):** Runs inside the game process. Exposes game state over HTTP (port 7880) and broadcasts events over WebSocket (port 7881).
- **Python Agent:** Orchestrator that polls game state, runs A* pathfinding, manages an event loop with safety overrides and frustration counters.
- **LLM (Claude):** Called only when the agent is `idle` or `blocked` to plan tasks and reason about obstacles.
