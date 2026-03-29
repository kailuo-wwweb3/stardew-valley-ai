# Stardew Valley AI Agent — Implementation Plan

## Goal

Build an AI agent that autonomously plays Stardew Valley by reading game state via a SMAPI mod (C# HTTP bridge inside the game) and making decisions via Claude API.

## Architecture

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   SMAPI Mod      │  HTTP   │   Python Agent    │  HTTP   │   LLM (Claude)   │
│   (C# in-game)   │◄───────►│   (orchestrator)  │◄───────►│   (decision AI)  │
│                  │  JSON   │                  │   API   │                  │
│ - Read game state│         │ - Poll state      │         │ - Plan actions   │
│ - Expose via API │         │ - Send to LLM     │         │ - Reason about   │
│ - Execute actions│         │ - Execute actions  │         │   game strategy  │
└──────────────────┘         └──────────────────┘         └──────────────────┘
         │                            │
    Runs inside                 Runs as separate
    game process                Python process
    on port 7880                on local machine
```

## Prerequisites

Before starting implementation:

1. **Install .NET 6.0+ SDK** — required to compile the C# SMAPI mod
   ```bash
   brew install dotnet
   dotnet --version  # should be 6.0+
   ```

2. **Install SMAPI** — the Stardew Valley modding framework
   - Download from https://smapi.io/
   - Extract the zip (NOT inside the game folder)
   - Right-click `install on Mac.command` → Open
   - SMAPI installs into the game directory

3. **Verify SMAPI works** — launch Stardew Valley via SMAPI
   ```bash
   # Steam should now launch via SMAPI automatically
   # Or run directly:
   ~/Library/Application\ Support/Steam/steamapps/common/Stardew\ Valley/Contents/MacOS/StardewModdingAPI
   ```

4. **Locate key paths on macOS**:
   - Game install: `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/`
   - Mods folder: `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods/`
   - SMAPI config: `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/smapi-internal/`

---

## Phase 1: SMAPI Mod — Game State HTTP Bridge

### 1.1 Project Scaffolding

Create the C# project at `mod/StardewAgent/`.

**File: `mod/StardewAgent/StardewAgent.csproj`**
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <AssemblyName>StardewAgent</AssemblyName>
    <RootNamespace>StardewAgent</RootNamespace>
    <Version>1.0.0</Version>
    <TargetFramework>net6.0</TargetFramework>
    <Nullable>enable</Nullable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Pathoschild.Stardew.ModBuildConfig" Version="4.4.0" />
  </ItemGroup>
</Project>
```

**File: `mod/StardewAgent/manifest.json`**
```json
{
  "$schema": "https://smapi.io/schemas/manifest.json",
  "Name": "Stardew Agent",
  "Author": "StardewAI",
  "Version": "1.0.0",
  "Description": "Exposes game state via HTTP for AI agent control",
  "UniqueID": "StardewAI.StardewAgent",
  "EntryDll": "StardewAgent.dll",
  "MinimumApiVersion": "4.0.0"
}
```

**Build & deploy:**
```bash
cd mod/StardewAgent
dotnet build
# ModBuildConfig auto-copies output to the game's Mods/ folder on build
```

### 1.2 Mod Entry Point — `ModEntry.cs`

This is the main mod class. It:
1. Starts an `HttpListener` on a background thread (port 7880)
2. On each game tick (`UpdateTicked`), snapshots game state and processes queued actions
3. Routes HTTP requests to read state or queue actions

**Thread safety model:**
- The `HttpListener` runs on a background `Task.Run` thread
- Game state is ONLY read on the game thread inside `UpdateTicked`
- A `_latestState` object is snapshotted each tick and served to HTTP GET requests (read-only, safe)
- Action requests from HTTP POST are enqueued into a `ConcurrentQueue<ActionRequest>` and dequeued/executed on the game thread in `UpdateTicked`

```csharp
// Skeleton structure for ModEntry.cs
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;

namespace StardewAgent
{
    public class ModEntry : Mod
    {
        private HttpListener _listener;
        private CancellationTokenSource _cts;
        private ConcurrentQueue<ActionRequest> _actionQueue = new();
        private GameStateSnapshot _latestState;

        // Tracks ongoing movement: direction + remaining ticks
        private MovementCommand? _activeMovement;

        public override void Entry(IModHelper helper)
        {
            helper.Events.GameLoop.SaveLoaded += OnSaveLoaded;
            helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
            helper.Events.GameLoop.ReturnedToTitle += OnReturnedToTitle;
        }

        private void OnSaveLoaded(object sender, SaveLoadedEventArgs e)
        {
            StartHttpServer();
        }

        private void OnReturnedToTitle(object sender, ReturnedToTitleEventArgs e)
        {
            StopHttpServer();
        }

        private void OnUpdateTicked(object sender, UpdateTickedEventArgs e)
        {
            if (!Context.IsWorldReady) return;

            // 1. Snapshot game state (every 15 ticks = ~4x/sec is enough)
            if (e.IsMultipleOf(15))
                _latestState = GameStateService.CaptureState();

            // 2. Process movement (hold key for N ticks)
            ProcessMovement();

            // 3. Dequeue and execute one action per tick
            if (_actionQueue.TryDequeue(out var action))
                ActionService.Execute(action, this);
        }
        // ... HTTP server methods below
    }
}
```

### 1.3 Game State Service — `GameStateService.cs`

Reads all game state into plain C# objects (DTOs) for JSON serialization.

**`GameStateSnapshot` — the full state object returned by `GET /state`:**
```csharp
public class GameStateSnapshot
{
    public PlayerState Player { get; set; }
    public TimeState Time { get; set; }
    public LocationState Location { get; set; }
    public List<InventoryItem> Inventory { get; set; }
    public List<NearbyTile> NearbyTiles { get; set; }  // 7x7 grid around player
    public List<NpcInfo> Npcs { get; set; }
}
```

**`PlayerState`:**
```csharp
public class PlayerState
{
    public float X { get; set; }              // Game1.player.Position.X
    public float Y { get; set; }              // Game1.player.Position.Y
    public int TileX { get; set; }            // Game1.player.TileLocation.X
    public int TileY { get; set; }            // Game1.player.TileLocation.Y
    public float Stamina { get; set; }        // Game1.player.Stamina
    public float MaxStamina { get; set; }     // Game1.player.MaxStamina
    public int Health { get; set; }           // Game1.player.Health
    public int MaxHealth { get; set; }        // Game1.player.maxHealth
    public int Money { get; set; }            // Game1.player.Money
    public string CurrentTool { get; set; }   // Game1.player.CurrentTool?.Name
    public int FacingDirection { get; set; }  // 0=up, 1=right, 2=down, 3=left
}
```

**`TimeState`:**
```csharp
public class TimeState
{
    public int TimeOfDay { get; set; }    // Game1.timeOfDay (e.g., 600 = 6:00 AM)
    public int Day { get; set; }          // Game1.dayOfMonth
    public string Season { get; set; }    // Game1.season.ToString()
    public int Year { get; set; }         // Game1.year
    public bool IsRaining { get; set; }   // Game1.isRaining
    public string DayOfWeek { get; set; } // Game1.shortDayNameFromDayOfSeason(Game1.dayOfMonth)
}
```

**`LocationState`:**
```csharp
public class LocationState
{
    public string Name { get; set; }                  // Game1.currentLocation.Name
    public List<LocationObject> Objects { get; set; } // placed objects (machines, debris)
    public List<string> NpcsPresent { get; set; }     // NPC names in this location
}
```

**`InventoryItem`:**
```csharp
public class InventoryItem
{
    public int Slot { get; set; }         // 0-35 (0-11 = toolbar)
    public string Name { get; set; }      // item.Name
    public int Stack { get; set; }        // item.Stack
    public int Quality { get; set; }      // 0=normal, 1=silver, 2=gold, 3=iridium
    public string Category { get; set; }  // "Seed", "Tool", "Mineral", etc.
    public bool IsTool { get; set; }      // item is Tool
}
```

**`NearbyTile` — 7x7 grid around player:**
```csharp
public class NearbyTile
{
    public int X { get; set; }
    public int Y { get; set; }
    public bool IsWalkable { get; set; }
    public bool IsWater { get; set; }
    public bool IsTilled { get; set; }
    public bool IsWatered { get; set; }
    public string CropName { get; set; }       // null if no crop
    public int CropPhase { get; set; }         // growth phase (0-4)
    public bool CropReadyToHarvest { get; set; }
    public bool CropDead { get; set; }
    public string ObjectName { get; set; }     // placed object name (e.g., "Chest")
}
```

**How to read tile data:**
```csharp
// Inside GameStateService.CaptureState()
public static List<NearbyTile> GetNearbyTiles(int radius = 3)
{
    var tiles = new List<NearbyTile>();
    var location = Game1.currentLocation;
    var playerTile = Game1.player.TileLocation;

    for (int dx = -radius; dx <= radius; dx++)
    {
        for (int dy = -radius; dy <= radius; dy++)
        {
            int x = (int)playerTile.X + dx;
            int y = (int)playerTile.Y + dy;
            var tileVec = new Vector2(x, y);
            var tile = new NearbyTile { X = x, Y = y };

            // Walkability
            tile.IsWalkable = !location.isTileOccupiedForPlacement(tileVec)
                && location.isTilePassable(x, y);

            // Water
            tile.IsWater = location.doesTileHaveProperty(x, y, "Water", "Back") != null;

            // Crop state via HoeDirt
            if (location.terrainFeatures.TryGetValue(tileVec, out var feature)
                && feature is HoeDirt dirt)
            {
                tile.IsTilled = true;
                tile.IsWatered = dirt.state.Value == 1; // 0=dry, 1=watered
                if (dirt.crop != null)
                {
                    tile.CropName = dirt.crop.indexOfHarvest.Value; // item ID
                    tile.CropPhase = dirt.crop.currentPhase.Value;
                    tile.CropReadyToHarvest = dirt.crop.fullyGrown.Value
                        && dirt.crop.dayOfCurrentPhase.Value <= 0;
                    tile.CropDead = dirt.crop.dead.Value;
                }
            }

            // Placed objects
            if (location.Objects.TryGetValue(tileVec, out var obj))
            {
                tile.ObjectName = obj.Name;
            }

            tiles.Add(tile);
        }
    }
    return tiles;
}
```

**`NpcInfo`:**
```csharp
public class NpcInfo
{
    public string Name { get; set; }
    public float X { get; set; }
    public float Y { get; set; }
    public string Location { get; set; }
    public int FriendshipPoints { get; set; } // Game1.player.friendshipData[name].Points
    public int HeartLevel { get; set; }       // points / 250
}

// How to gather NPC data:
public static List<NpcInfo> GetNpcs()
{
    var npcs = new List<NpcInfo>();
    foreach (var npc in Utility.getAllVillagers())
    {
        var info = new NpcInfo
        {
            Name = npc.Name,
            X = npc.Position.X,
            Y = npc.Position.Y,
            Location = npc.currentLocation?.Name,
        };
        if (Game1.player.friendshipData.TryGetValue(npc.Name, out var friendship))
        {
            info.FriendshipPoints = friendship.Points;
            info.HeartLevel = friendship.Points / 250;
        }
        npcs.Add(info);
    }
    return npcs;
}
```

### 1.4 Action Service — `ActionService.cs`

Processes action commands received from the Python agent via HTTP POST.

**`ActionRequest` — the command object:**
```csharp
public class ActionRequest
{
    public string Type { get; set; }           // "move", "use_tool", "interact", "select_slot"
    public string Direction { get; set; }      // for move: "up", "down", "left", "right"
    public int DurationMs { get; set; }        // for move: milliseconds to hold key
    public int Slot { get; set; }              // for select_slot: 1-12
    public HttpListenerContext HttpContext { get; set; } // to send response after execution
}
```

**Movement implementation — hold key for N game ticks:**
```csharp
// Movement is special: it spans multiple ticks
// We track an active movement and press/release keys across ticks

public class MovementCommand
{
    public SButton Key { get; set; }
    public int RemainingTicks { get; set; }
}

public static class ActionService
{
    // Direction → SButton mapping
    private static readonly Dictionary<string, SButton> DirectionKeys = new()
    {
        ["up"] = SButton.W,
        ["down"] = SButton.S,
        ["left"] = SButton.A,
        ["right"] = SButton.D,
    };

    public static MovementCommand? StartMove(ActionRequest req, IInputHelper input)
    {
        if (!DirectionKeys.TryGetValue(req.Direction, out var key))
            return null;

        // Convert ms to ticks (game runs at 60 ticks/sec)
        int ticks = Math.Max(1, req.DurationMs * 60 / 1000);

        input.Press(key);
        return new MovementCommand { Key = key, RemainingTicks = ticks };
    }

    public static void TickMovement(ref MovementCommand? cmd, IInputHelper input)
    {
        if (cmd == null) return;

        cmd.RemainingTicks--;
        if (cmd.RemainingTicks <= 0)
        {
            input.Release(cmd.Key);
            cmd = null;
        }
        else
        {
            // Keep holding the key
            input.Press(cmd.Key);
        }
    }

    public static void Execute(ActionRequest req, ModEntry mod)
    {
        switch (req.Type)
        {
            case "move":
                mod._activeMovement = StartMove(req, mod.Helper.Input);
                Respond(req.HttpContext, 200, new { status = "moving" });
                break;

            case "use_tool":
                // Simulate left-click (tool use)
                Game1.pressUseToolButton();
                Respond(req.HttpContext, 200, new { status = "tool_used" });
                break;

            case "interact":
                // Simulate action button
                Game1.pressActionButton(Game1.input.GetKeyboardState(),
                    Game1.input.GetMouseState(),
                    Game1.input.GetGamePadState());
                Respond(req.HttpContext, 200, new { status = "interacted" });
                break;

            case "select_slot":
                Game1.player.CurrentToolIndex = req.Slot - 1; // 0-indexed
                Respond(req.HttpContext, 200, new { status = "slot_selected", slot = req.Slot });
                break;
        }
    }
}
```

### 1.5 HTTP Server — Routing

Embedded in `ModEntry.cs`. Runs on background thread, serves JSON.

**Routes:**

| Method | Path | Handler |
|--------|------|---------|
| `GET` | `/state` | Return full `_latestState` as JSON |
| `GET` | `/player` | Return `_latestState.Player` |
| `GET` | `/inventory` | Return `_latestState.Inventory` |
| `GET` | `/time` | Return `_latestState.Time` |
| `GET` | `/location` | Return `_latestState.Location` |
| `GET` | `/tiles` | Return `_latestState.NearbyTiles` |
| `GET` | `/npcs` | Return `_latestState.Npcs` |
| `GET` | `/health` | Return `{ "status": "ok" }` — health check |
| `POST` | `/action/move` | Parse `{ "direction": "up", "duration": 500 }`, enqueue |
| `POST` | `/action/use-tool` | Enqueue tool use action |
| `POST` | `/action/interact` | Enqueue interact action |
| `POST` | `/action/select-slot` | Parse `{ "slot": 1 }`, enqueue |

**HTTP server implementation:**
```csharp
private void StartHttpServer()
{
    _cts = new CancellationTokenSource();
    _listener = new HttpListener();
    _listener.Prefixes.Add("http://localhost:7880/");
    _listener.Start();
    Monitor.Log("HTTP server started on port 7880", LogLevel.Info);

    Task.Run(async () =>
    {
        while (!_cts.Token.IsCancellationRequested)
        {
            try
            {
                var context = await _listener.GetContextAsync();
                HandleRequest(context);
            }
            catch (Exception ex) when (_cts.Token.IsCancellationRequested)
            {
                break; // server shutting down
            }
            catch (Exception ex)
            {
                Monitor.Log($"HTTP error: {ex.Message}", LogLevel.Error);
            }
        }
    }, _cts.Token);
}

private void HandleRequest(HttpListenerContext context)
{
    var path = context.Request.Url.AbsolutePath.ToLower();
    var method = context.Request.HttpMethod;

    if (method == "GET")
    {
        object responseData = path switch
        {
            "/state"     => _latestState,
            "/player"    => _latestState?.Player,
            "/inventory" => _latestState?.Inventory,
            "/time"      => _latestState?.Time,
            "/location"  => _latestState?.Location,
            "/tiles"     => _latestState?.NearbyTiles,
            "/npcs"      => _latestState?.Npcs,
            "/health"    => new { status = "ok" },
            _            => null,
        };

        if (responseData != null)
            Respond(context, 200, responseData);
        else
            Respond(context, 404, new { error = "not found" });
    }
    else if (method == "POST")
    {
        // Read JSON body
        using var reader = new StreamReader(context.Request.InputStream);
        var body = reader.ReadToEnd();
        var json = JsonDocument.Parse(body);

        var action = new ActionRequest { HttpContext = context };

        switch (path)
        {
            case "/action/move":
                action.Type = "move";
                action.Direction = json.RootElement.GetProperty("direction").GetString();
                action.DurationMs = json.RootElement.GetProperty("duration").GetInt32();
                break;
            case "/action/use-tool":
                action.Type = "use_tool";
                break;
            case "/action/interact":
                action.Type = "interact";
                break;
            case "/action/select-slot":
                action.Type = "select_slot";
                action.Slot = json.RootElement.GetProperty("slot").GetInt32();
                break;
            default:
                Respond(context, 404, new { error = "unknown action" });
                return;
        }

        _actionQueue.Enqueue(action);
        // Response is sent after action executes on game thread
    }
}

private static void Respond(HttpListenerContext ctx, int statusCode, object data)
{
    var json = JsonSerializer.Serialize(data, new JsonSerializerOptions
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false
    });
    var bytes = System.Text.Encoding.UTF8.GetBytes(json);
    ctx.Response.StatusCode = statusCode;
    ctx.Response.ContentType = "application/json";
    ctx.Response.ContentLength64 = bytes.Length;
    ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
    ctx.Response.Close();
}
```

### 1.6 Build & Test

```bash
cd mod/StardewAgent
dotnet build

# The DLL + manifest.json auto-deploy to Mods/StardewAgent/ on build
# Launch Stardew Valley (via SMAPI), load a save

# Test from terminal:
curl http://localhost:7880/health
# → {"status":"ok"}

curl http://localhost:7880/state
# → full game state JSON

curl -X POST http://localhost:7880/action/move \
  -H "Content-Type: application/json" \
  -d '{"direction": "right", "duration": 500}'
# → {"status":"moving"}
```

---

## Phase 2: Python Agent — Orchestrator

### 2.1 Game Client — `agent/game_client.py`

HTTP client wrapping all SMAPI mod endpoints. This is the Python-side interface to the game.

```python
"""
Game client — HTTP wrapper for the SMAPI mod's REST API.

Usage:
    client = GameClient()
    state = client.get_state()
    client.move("right", duration=500)
    client.use_tool()
"""
import httpx
import time

class GameClient:
    def __init__(self, base_url: str = "http://localhost:7880", timeout: float = 5.0):
        self.base_url = base_url
        self.http = httpx.Client(base_url=base_url, timeout=timeout)

    # -- Read endpoints --

    def get_state(self) -> dict:
        """Full game state snapshot."""
        return self.http.get("/state").json()

    def get_player(self) -> dict:
        return self.http.get("/player").json()

    def get_inventory(self) -> list[dict]:
        return self.http.get("/inventory").json()

    def get_time(self) -> dict:
        return self.http.get("/time").json()

    def get_location(self) -> dict:
        return self.http.get("/location").json()

    def get_tiles(self) -> list[dict]:
        return self.http.get("/tiles").json()

    def get_npcs(self) -> list[dict]:
        return self.http.get("/npcs").json()

    def is_connected(self) -> bool:
        try:
            r = self.http.get("/health")
            return r.status_code == 200
        except httpx.ConnectError:
            return False

    # -- Action endpoints --

    def move(self, direction: str, duration: int = 500) -> dict:
        """Move in a direction for `duration` ms. direction: up/down/left/right."""
        return self.http.post("/action/move", json={
            "direction": direction, "duration": duration
        }).json()

    def use_tool(self) -> dict:
        """Use the currently equipped tool."""
        return self.http.post("/action/use-tool").json()

    def interact(self) -> dict:
        """Interact with the object/NPC the player is facing."""
        return self.http.post("/action/interact").json()

    def select_slot(self, slot: int) -> dict:
        """Select toolbar slot (1-12)."""
        return self.http.post("/action/select-slot", json={"slot": slot}).json()

    # -- Convenience --

    def wait_for_connection(self, timeout: float = 30.0):
        """Block until the mod's HTTP server is reachable."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_connected():
                return True
            time.sleep(1)
        raise ConnectionError(f"Could not connect to SMAPI mod at {self.base_url}")
```

### 2.2 Action Primitives — `agent/actions.py`

Higher-level actions composed from the raw client calls. These are what the AI brain invokes.

```python
"""
High-level game actions built on top of GameClient.

Each function handles its own polling, timing, and error recovery.
"""
import time
from game_client import GameClient

class Actions:
    def __init__(self, client: GameClient):
        self.client = client

    def walk_to(self, target_x: int, target_y: int, timeout: float = 10.0):
        """
        Walk the player to a target tile using simple pathfinding.
        Moves on X axis first, then Y axis (no obstacle avoidance yet).
        """
        start = time.time()
        while time.time() - start < timeout:
            player = self.client.get_player()
            px, py = player["tileX"], player["tileY"]

            if px == target_x and py == target_y:
                return True  # arrived

            # Move horizontally first
            if px < target_x:
                self.client.move("right", duration=300)
            elif px > target_x:
                self.client.move("left", duration=300)
            # Then vertically
            elif py < target_y:
                self.client.move("down", duration=300)
            elif py > target_y:
                self.client.move("up", duration=300)

            time.sleep(0.4)  # wait for movement to complete

        return False  # timed out

    def water_all_crops(self):
        """Find unwatered crops nearby and water them."""
        self.client.select_slot(1)  # assume watering can in slot 1
        time.sleep(0.2)

        tiles = self.client.get_tiles()
        unwatered = [
            t for t in tiles
            if t.get("isTilled") and not t.get("isWatered")
            and t.get("cropName") and not t.get("cropDead")
        ]

        for tile in unwatered:
            self.walk_to(tile["x"], tile["y"])
            self.client.use_tool()
            time.sleep(0.3)

    def harvest_crops(self):
        """Harvest all ready crops nearby."""
        tiles = self.client.get_tiles()
        ready = [t for t in tiles if t.get("cropReadyToHarvest")]

        for tile in ready:
            self.walk_to(tile["x"], tile["y"])
            self.client.interact()
            time.sleep(0.3)

    def go_to_bed(self):
        """
        Navigate to the farmhouse bed.
        Bed is at approximately tile (9, 9) inside the FarmHouse.
        This assumes the player is on the farm — would need map transitions for other locations.
        """
        # First go to farm house entrance (roughly tile 64, 15 on the farm)
        self.walk_to(64, 15)
        time.sleep(0.5)
        # Walk into the door (move up)
        self.client.move("up", duration=500)
        time.sleep(1.0)
        # Inside farmhouse, walk to bed
        self.walk_to(9, 9)
        time.sleep(0.5)
        self.client.interact()

    def eat_item(self, slot: int):
        """Eat a food item from the given inventory slot."""
        self.client.select_slot(slot)
        time.sleep(0.2)
        self.client.interact()
```

### 2.3 Agent Loop — `agent/agent.py`

The main loop that ties everything together.

```python
"""
Main agent loop.

Modes:
  - "scripted": Runs a hardcoded daily routine (no LLM)
  - "ai": Uses Claude to make decisions each cycle

Usage:
    python agent.py --mode scripted
    python agent.py --mode ai
"""
import argparse
import time
from game_client import GameClient
from actions import Actions
from ai_brain import AIBrain

TICK_INTERVAL = 2.0  # seconds between decision cycles

def scripted_loop(client: GameClient, actions: Actions):
    """Simple scripted daily routine: water, harvest, go to bed."""
    while True:
        state = client.get_state()
        time_of_day = state["time"]["timeOfDay"]
        stamina = state["player"]["stamina"]

        print(f"[{time_of_day}] Stamina: {stamina}")

        if time_of_day < 900:
            print("Morning: watering crops")
            actions.water_all_crops()
        elif time_of_day < 1200:
            print("Late morning: harvesting")
            actions.harvest_crops()
        elif time_of_day >= 2200 or stamina < 20:
            print("Late night or low stamina: going to bed")
            actions.go_to_bed()
            time.sleep(10)  # wait for day transition
        else:
            print("Idle — waiting")

        time.sleep(TICK_INTERVAL)

def ai_loop(client: GameClient, actions: Actions, brain: AIBrain):
    """AI-driven loop: Claude decides what to do each cycle."""
    day_plan = None
    last_day = None

    while True:
        state = client.get_state()
        current_day = state["time"]["day"]

        # At the start of each new game day, create a day plan
        if current_day != last_day:
            day_plan = brain.plan_day(state)
            last_day = current_day
            print(f"=== Day {current_day} Plan ===")
            for step in day_plan:
                print(f"  - {step}")

        # Each tick, ask the brain what to do next given current state + plan
        decision = brain.decide(state, day_plan)
        print(f"[{state['time']['timeOfDay']}] Action: {decision['action']}")

        # Execute the decision
        execute_decision(decision, actions, client)

        time.sleep(TICK_INTERVAL)

def execute_decision(decision: dict, actions: Actions, client: GameClient):
    """Map an AI decision to an action primitive call."""
    action = decision["action"]
    params = decision.get("params", {})

    match action:
        case "walk_to":
            actions.walk_to(params["x"], params["y"])
        case "water_crops":
            actions.water_all_crops()
        case "harvest":
            actions.harvest_crops()
        case "use_tool":
            client.use_tool()
        case "interact":
            client.interact()
        case "select_slot":
            client.select_slot(params["slot"])
        case "go_to_bed":
            actions.go_to_bed()
        case "move":
            client.move(params["direction"], params.get("duration", 500))
        case "wait":
            pass  # do nothing this tick
        case _:
            print(f"Unknown action: {action}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scripted", "ai"], default="scripted")
    args = parser.parse_args()

    client = GameClient()
    print("Waiting for SMAPI mod connection...")
    client.wait_for_connection()
    print("Connected!")

    actions = Actions(client)

    if args.mode == "scripted":
        scripted_loop(client, actions)
    else:
        brain = AIBrain()
        ai_loop(client, actions, brain)

if __name__ == "__main__":
    main()
```

### 2.4 Configuration — `agent/config.py`

```python
"""Agent configuration. Loaded from environment variables or defaults."""
import os

# SMAPI mod connection
MOD_URL = os.getenv("STARDEW_MOD_URL", "http://localhost:7880")

# Agent settings
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "2.0"))  # seconds
STATE_HISTORY_SIZE = int(os.getenv("STATE_HISTORY_SIZE", "20"))  # keep last N states

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
```

---

## Phase 3: AI Brain — Claude Decision Making

### 3.1 AI Brain — `agent/ai_brain.py`

Sends game state to Claude API and receives structured action decisions.

```python
"""
AI Brain — uses Claude to make game decisions.

Two main functions:
  - plan_day(state): Called once per game day, returns a list of goals
  - decide(state, plan): Called each tick, returns the next action to take
"""
import json
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

SYSTEM_PROMPT = """You are an AI playing Stardew Valley. You receive game state as JSON
and must decide what action to take next.

You have access to these actions:
- walk_to: {"action": "walk_to", "params": {"x": int, "y": int}}
- water_crops: {"action": "water_crops"}
- harvest: {"action": "harvest"}
- use_tool: {"action": "use_tool"}
- interact: {"action": "interact"}
- select_slot: {"action": "select_slot", "params": {"slot": int}}
- go_to_bed: {"action": "go_to_bed"}
- move: {"action": "move", "params": {"direction": "up|down|left|right", "duration": int_ms}}
- wait: {"action": "wait"}

Key game rules:
- Player passes out at 2:00 AM (timeOfDay=2600) and loses money. Go to bed before midnight.
- Stamina depletes when using tools. Eat food or go to bed to restore.
- Crops must be watered daily or they won't grow. Rain waters them automatically.
- Each season is 28 days. Crops die when seasons change.
- The mine has 120 levels. Take elevator every 5 levels.

Respond ONLY with valid JSON. No explanation text."""

class AIBrain:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.state_history = []

    def plan_day(self, state: dict) -> list[str]:
        """Create a plan for the current game day."""
        prompt = f"""It's the start of a new day. Create a prioritized plan.

Current state:
{json.dumps(state, indent=2)}

Respond with a JSON array of goal strings, ordered by priority.
Example: ["Water all crops", "Harvest ready crops", "Go to Pierre's to buy seeds", "Mine to level 25", "Go to bed by 11 PM"]"""

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        return json.loads(response.content[0].text)

    def decide(self, state: dict, day_plan: list[str] | None) -> dict:
        """Decide the next action given current state and day plan."""
        # Keep a rolling history of recent states for context
        self.state_history.append(self._summarize_state(state))
        if len(self.state_history) > 10:
            self.state_history.pop(0)

        prompt = f"""Current state:
{json.dumps(state, indent=2)}

Today's plan: {json.dumps(day_plan)}

Recent history (last {len(self.state_history)} ticks):
{json.dumps(self.state_history, indent=2)}

What is the single next action to take? Respond with one JSON action object."""

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        return json.loads(response.content[0].text)

    def _summarize_state(self, state: dict) -> dict:
        """Compact state summary for history (saves tokens)."""
        return {
            "time": state["time"]["timeOfDay"],
            "pos": f"{state['player']['tileX']},{state['player']['tileY']}",
            "stamina": round(state["player"]["stamina"]),
            "location": state["location"]["name"],
        }
```

### 3.2 Goal System & Priority Overrides

The AI brain handles this naturally via the system prompt, but there are hard-coded safety overrides in the agent loop that take priority over LLM decisions:

```python
# In agent.py ai_loop(), before calling brain.decide():

def check_urgent_overrides(state: dict) -> dict | None:
    """Hard-coded safety overrides that bypass the LLM."""
    time_of_day = state["time"]["timeOfDay"]
    stamina = state["player"]["stamina"]
    health = state["player"]["health"]

    # MUST go to bed before 2 AM or lose money
    if time_of_day >= 2400:
        return {"action": "go_to_bed"}

    # Very low stamina — stop using tools
    if stamina < 10 and time_of_day > 1800:
        return {"action": "go_to_bed"}

    # Critical health in mines — eat food
    if health < 20:
        return {"action": "eat_food", "params": {"slot": 12}}  # emergency food slot

    return None  # no override, let LLM decide
```

---

## Phase 4: Game Knowledge Base

### 4.1 Crop Data — `agent/knowledge/crops.json`

Structure (abbreviated — full file should contain all crops):
```json
{
  "spring": [
    {"name": "Parsnip", "seed": "Parsnip Seeds", "seedCost": 20, "growthDays": 4, "regrowDays": -1, "sellPrice": 35},
    {"name": "Potato", "seed": "Seed Potato", "seedCost": 50, "growthDays": 6, "regrowDays": -1, "sellPrice": 100},
    {"name": "Cauliflower", "seed": "Cauliflower Seeds", "seedCost": 80, "growthDays": 12, "regrowDays": -1, "sellPrice": 175},
    {"name": "Kale", "seed": "Kale Seeds", "seedCost": 70, "growthDays": 6, "regrowDays": -1, "sellPrice": 110},
    {"name": "Strawberry", "seed": "Strawberry Seeds", "seedCost": 100, "growthDays": 8, "regrowDays": 4, "sellPrice": 120}
  ],
  "summer": [
    {"name": "Melon", "seed": "Melon Seeds", "seedCost": 80, "growthDays": 12, "regrowDays": -1, "sellPrice": 250},
    {"name": "Blueberry", "seed": "Blueberry Seeds", "seedCost": 80, "growthDays": 13, "regrowDays": 4, "sellPrice": 240},
    {"name": "Starfruit", "seed": "Starfruit Seeds", "seedCost": 400, "growthDays": 13, "regrowDays": -1, "sellPrice": 800},
    {"name": "Hot Pepper", "seed": "Hot Pepper Seeds", "seedCost": 40, "growthDays": 5, "regrowDays": 3, "sellPrice": 40},
    {"name": "Tomato", "seed": "Tomato Seeds", "seedCost": 50, "growthDays": 11, "regrowDays": 4, "sellPrice": 60}
  ],
  "fall": [
    {"name": "Cranberry", "seed": "Cranberry Seeds", "seedCost": 240, "growthDays": 7, "regrowDays": 5, "sellPrice": 130},
    {"name": "Pumpkin", "seed": "Pumpkin Seeds", "seedCost": 100, "growthDays": 13, "regrowDays": -1, "sellPrice": 320},
    {"name": "Grape", "seed": "Grape Seeds", "seedCost": 60, "growthDays": 10, "regrowDays": 3, "sellPrice": 80},
    {"name": "Amaranth", "seed": "Amaranth Seeds", "seedCost": 70, "growthDays": 7, "regrowDays": -1, "sellPrice": 150},
    {"name": "Artichoke", "seed": "Artichoke Seeds", "seedCost": 30, "growthDays": 8, "regrowDays": -1, "sellPrice": 160}
  ]
}
```

### 4.2 NPC Gift Data — `agent/knowledge/npcs.json`

```json
{
  "universalLoves": ["Golden Pumpkin", "Magic Rock Candy", "Pearl", "Prismatic Shard", "Rabbit's Foot"],
  "npcs": {
    "Abigail": {"loves": ["Amethyst", "Chocolate Cake", "Banana Pudding"], "location": "Pierre's Shop"},
    "Sebastian": {"loves": ["Frozen Tear", "Obsidian", "Pumpkin Soup"], "location": "Carpenter's Shop basement"},
    "Shane": {"loves": ["Beer", "Hot Pepper", "Pepper Poppers"], "location": "Marnie's Ranch"},
    "Penny": {"loves": ["Diamond", "Emerald", "Poppyseed Muffin"], "location": "Trailer"},
    "Emily": {"loves": ["Amethyst", "Cloth", "Emerald"], "location": "Haley's House"},
    "Haley": {"loves": ["Coconut", "Fruit Salad", "Pink Cake"], "location": "Haley's House"},
    "Maru": {"loves": ["Battery Pack", "Diamond", "Gold Bar"], "location": "Carpenter's Shop"},
    "Leah": {"loves": ["Goat Cheese", "Salad", "Stir Fry"], "location": "Leah's Cottage"},
    "Alex": {"loves": ["Complete Breakfast", "Salmon Dinner"], "location": "Alex's House"},
    "Sam": {"loves": ["Cactus Fruit", "Maple Bar", "Pizza"], "location": "Sam's House"},
    "Elliott": {"loves": ["Crab Cakes", "Lobster", "Tom Kha Soup"], "location": "Elliott's Cabin"},
    "Harvey": {"loves": ["Coffee", "Pickles", "Super Meal"], "location": "Harvey's Clinic"}
  }
}
```

### 4.3 Mining Data — `agent/knowledge/mining.json`

```json
{
  "totalLevels": 120,
  "elevatorEvery": 5,
  "ores": {
    "copper": {"firstLevel": 1, "peakLevels": [20, 30], "barsForUpgrade": 5},
    "iron": {"firstLevel": 40, "peakLevels": [60, 70], "barsForUpgrade": 5},
    "gold": {"firstLevel": 80, "peakLevels": [100, 110], "barsForUpgrade": 5},
    "iridium": {"firstLevel": 100, "peakLevels": [115, 120], "barsForUpgrade": 5}
  },
  "toolUpgrades": [
    {"tier": "Copper", "cost": 2000, "bars": 5, "barType": "Copper Bar"},
    {"tier": "Steel", "cost": 5000, "bars": 5, "barType": "Iron Bar"},
    {"tier": "Gold", "cost": 10000, "bars": 5, "barType": "Gold Bar"},
    {"tier": "Iridium", "cost": 25000, "bars": 5, "barType": "Iridium Bar"}
  ]
}
```

---

## Project Structure (Final)

```
star/
├── PLAN.md                          # this file
├── stardew_bot.py                   # Phase 0: basic pyautogui bot (done)
├── mod/                             # Phase 1: SMAPI C# mod
│   └── StardewAgent/
│       ├── StardewAgent.csproj      # .NET 6 project file
│       ├── manifest.json            # SMAPI mod manifest
│       ├── ModEntry.cs              # Entry point + HTTP server + game loop
│       ├── GameStateService.cs      # Reads game state → DTOs
│       ├── ActionService.cs         # Executes actions in-game
│       └── Models/                  # DTO classes
│           ├── GameStateSnapshot.cs
│           ├── PlayerState.cs
│           ├── TimeState.cs
│           ├── LocationState.cs
│           ├── InventoryItem.cs
│           ├── NearbyTile.cs
│           ├── NpcInfo.cs
│           └── ActionRequest.cs
├── agent/                           # Phase 2 & 3: Python agent
│   ├── game_client.py               # HTTP client for SMAPI mod
│   ├── agent.py                     # Main agent loop (scripted + AI modes)
│   ├── actions.py                   # High-level action primitives
│   ├── ai_brain.py                  # Claude API integration
│   ├── config.py                    # Settings (env vars)
│   └── knowledge/                   # Static game data
│       ├── crops.json
│       ├── npcs.json
│       └── mining.json
└── venv/                            # Python virtual environment
```

## Implementation Order (Step-by-Step)

| Step | What | Depends On | Deliverable |
|------|------|------------|-------------|
| 1 | Install .NET SDK + SMAPI on macOS | Nothing | SMAPI launches game with console |
| 2 | Create mod scaffolding (csproj, manifest, empty ModEntry) | Step 1 | Mod loads in SMAPI console log |
| 3 | Add HttpListener + `/health` endpoint | Step 2 | `curl localhost:7880/health` returns OK |
| 4 | Implement `GameStateService` + `GET /state` | Step 3 | Full JSON state from curl |
| 5 | Implement all GET endpoints (/player, /inventory, etc.) | Step 4 | Each endpoint returns correct data |
| 6 | Create `agent/game_client.py` | Step 5 | Python can read game state |
| 7 | Implement `ActionService` + POST endpoints | Step 3 | curl can move the character |
| 8 | Create `agent/actions.py` with `walk_to`, `water_crops`, etc. | Steps 6+7 | Python can control the character |
| 9 | Create `agent/agent.py` scripted loop | Step 8 | Bot does a daily farming routine |
| 10 | Create `agent/knowledge/*.json` files | Nothing | Static data files |
| 11 | Create `agent/ai_brain.py` with Claude integration | Step 9+10 | `--mode ai` uses Claude for decisions |
| 12 | Test full AI loop: Claude plays a full game day | Step 11 | End-to-end autonomous play |

## Dependencies to Install

```bash
# .NET SDK (for SMAPI mod)
brew install dotnet

# Python packages (in venv)
cd star && source venv/bin/activate
pip install httpx anthropic

# SMAPI — download from https://smapi.io/
# Extract and run: install on Mac.command
```

## Key Technical Decisions & Gotchas

1. **Thread safety**: The HTTP server runs on a background thread but ALL game state access and modification MUST happen on the game thread (inside `UpdateTicked`). The `ConcurrentQueue<ActionRequest>` bridges the two threads.

2. **State snapshot frequency**: Capture state every 15 ticks (~4x/sec). This balances freshness with performance. The tile scan (7x7 = 49 tiles) is the most expensive part.

3. **Movement model**: Movement is key-hold based (press W for N ticks), not teleportation. The mod tracks a `MovementCommand` with remaining ticks and presses/releases keys across game ticks. The HTTP POST returns immediately; movement completes over subsequent ticks.

4. **LLM call frequency**: Don't call Claude every tick. Call `plan_day()` once per game day, and `decide()` every 2-5 seconds. Use compact state summaries to save tokens. A full game day at 2s intervals ≈ ~500 LLM calls — use `claude-sonnet` not `claude-opus` for cost efficiency.

5. **Pathfinding**: Phase 2 uses naive "move X then Y" pathfinding. This works on the open farm but fails in buildings/town with obstacles. A* pathfinding using tile walkability data from `/tiles` would be a Phase 4 improvement.

6. **Input simulation fallback**: If `Helper.Input.Press()` doesn't work reliably for all actions (some game actions check raw input state), fall back to `pyautogui` from the Python side for those specific actions. The mod should log when an action fails.

7. **macOS-specific**: Stardew Valley on macOS runs under MonoGame. SMAPI handles cross-platform compatibility. The game path is `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/`. HttpListener may require allowing incoming connections in macOS firewall settings for `localhost`.
