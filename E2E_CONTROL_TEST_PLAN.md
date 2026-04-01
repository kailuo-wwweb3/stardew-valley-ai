# Stardew Valley Agent: End-to-End (E2E) Test Implementation Plan

## Overview

This document outlines the strategy for building a robust, idempotent integration and end-to-end testing suite for the Stardew Valley agent. The goal is to verify that the Python program can reliably control the game character (moving, using tools, farming, shopping) without succumbing to game-engine quirks like the daily clock or dirty environment states.

## 1. Test Suite Architecture

We will use `**pytest**` as our structured testing framework. 

### Test Runner Orchestration

For this implementation, the `pytest` suite assumes that Stardew Valley is **already running**, the SMAPI mod is loaded, and the player is actively loaded into a "Test Save" file. The Python suite will act as a client connecting to the running C# WebSocket/HTTP server.

### Standard Test Flow & Idempotency

Because Stardew runs on a continuous 60FPS tick loop, tests must manage time, state, and asynchronous delays. Every test will follow this pattern:

1. **Idempotent Setup (Clean Slate):** Trigger a C# debug command to clear the local testing area (e.g., removing all crops, debris, or objects within a 10-tile radius) or reload the pristine test save to prevent cascading failures from previous tests.
2. **Command:** Issue the target action (e.g., `actions.walk_to`, `actions.use_tool`).
3. **Poll & Assert (`wait_for_state`):** Use a Python helper `wait_for_state(condition_lambda, timeout)` that polls the `/state` endpoint every 100ms. If the lambda evaluates to true before the timeout, the test passes.

---

## 2. Implementation Phases

### Phase 1: Navigation & Environment

Validating movement, pathfinding, and map transitions.

- **Test Local Movement:** Verify walking to an adjacent tile updates `tileX` and `tileY`.
- **Test Obstacle Avoidance:** Verify walking across a cluttered farm reaches the destination using A*.
- **Test Map Transitions:** Walk to the edge of the map (e.g., Farm to Bus Stop) and assert via `wait_for_state` that the `location` string updates.

### Phase 1.5: C# API Expansion & Test Hardening (Prerequisites)

Before writing gameplay assertions, the C# mod (`StardewAgent`) must be hardened to expose critical data and control the environment:

- **Time Management (The 2 AM Problem):** Add a hook to lock `Game1.gameTimeInterval` to freeze the in-game clock. Tests should run in a frozen-time state unless crop growth or NPC schedules are specifically being tested.
- **Environment Reset Hooks:** Add a debug command to clear specific tiles (destroying crops/debris) to ensure idempotency.
- **Menu State Detection:** Update `GameStateService.GetState()` to serialize `Game1.activeClickableMenu`. Python must know if the UI is hijacking inputs.
- **Inventory Serialization:** Serialize `player.Items` (IDs, names, stack sizes) so Python can assert bag contents.
- **Entity Tracking:** Update `GetLocalTileGrid()` to scan `location.characters` (NPCs/Monsters) and append them to the grid.
- **The "Interact" Hook:** Add an endpoint in `ActionService.cs` that triggers `Game1.tryToCheckAt(Vector2 tileLocation, Farmer who)` for right-click mechanics.

### Phase 2: Tool Usage & Resource Clearing

Validating inventory management, stamina drain, and basic tool swings.

- **Test Tool Selection:** Iterate through the inventory, equip tools, and verify `CurrentToolIndex`.
- **Test Stamina Depletion:** Swing a tool repeatedly. Assert `player.Stamina` decreases, and verify the failure state at `<= 2` stamina.
- **Test Resource Clearing:** 1. Spawn a rock via Setup.
  1. Walk to it and face it.
  2. Use the Pickaxe.
  3. Assert via `wait_for_state` that the object is removed from `localTiles`.

### Phase 3: The Farming Cycle

Validating the core loop of tilling, planting, watering, and harvesting.

- **Test Tilling:** Walk to empty dirt, use the `Hoe`, and verify the terrain feature changes to `HoeDirt`.
- **Test Planting:** Equip a seed, face the `HoeDirt`, and trigger the "Interact" endpoint. Assert `hoeDirt.crop` is populated.
- **Test Watering:** Equip the `WateringCan`, use it on the planted tile, and assert `hoeDirt.state.Value == 1`.
- **Test Harvesting:** 1. Advance time via SMAPI until the crop is fully grown.
  1. Use the "Interact" endpoint to harvest.
  2. Assert the crop is added to the serialized inventory and removed from the tile.

### Phase 4: Commerce (Buying & Selling)

Validating NPC interactions, shop menus, and shipping.

- **Test Shop Navigation:** Walk from the Farm to Pierre's.
- **Test Menu Interaction:** Use `tryToCheckAt` on the shop counter. Assert via `wait_for_state` that the `/state` endpoint reports `activeMenu == "ShopMenu"`.
- **Test Purchasing:** Send a menu command to purchase Parsnip Seeds. Assert gold decreases and seeds appear in the inventory.
- **Test Shipping Bin:** Walk to the shipping bin, interact to deposit a crop, and verify it leaves the inventory.

### Phase 5: Fishing Mechanics

Validating timing-based tool actions and mini-games.

- **Test Casting:** Walk to water, equip the Fishing Rod, and cast.
- **Test Bite Detection:** Poll for the bobber status to detect a bite.
- **Test Catching:** Add a debug flag in C# to auto-win the mini-game. Assert a fish is added to the inventory after a bite.

### Phase 6: Mining & Combat

Validating dynamic environment reactions.

- **Test Ladder Discovery:** Break rocks in the mines and scan the dynamically updated tile map to detect ladder spawns.
- **Test Combat:** Identify an enemy in `localTiles` (via Phase 1.5 entity tracking), pathfind to it, equip the Sword, and trigger rapid tool usage while tracking enemy HP.

---

## 3. Required C# Mod API Additions (Summary)

1. **State & Entities:** `player.Items` serialization, `location.characters` exposure, and `Game1.activeClickableMenu` tracking.
2. **Interaction:** `Game1.tryToCheckAt` endpoint for right-clicking.
3. **Menu Manipulation:** Endpoints to read shop contents and trigger buy/sell logic.
4. **God-Mode Hooks:** Time freezing (`Game1.gameTimeInterval`), environment clearing, and auto-win fishing flags for deterministic testing.

