# Navigation Mechanics Reference

## Collision & Walkability

- Each tile can be checked for passability:
  ```csharp
  location.isTilePassable(new xTile.Dimensions.Location(tileX * 64, tileY * 64), Game1.viewport)
  ```
- Buildings layer blocking: `location.isTileOccupiedByFarmer(tile)` or check `location.Objects`, `location.terrainFeatures`, `location.largeTerrainFeatures`.
- Water tiles: check the tile index on the "Back" layer against known water tile indices, or use `location.isOpenWater(tileX, tileY)`.

## Map Data

- Current map dimensions:
  ```csharp
  var map = location.Map;
  int width = map.Layers[0].LayerWidth;   // in tiles
  int height = map.Layers[0].LayerHeight; // in tiles
  ```

## Full Collision Matrix (for A*)

Build a boolean grid of the entire map for pathfinding:

```csharp
bool[,] grid = new bool[width, height];
for (int x = 0; x < width; x++)
{
    for (int y = 0; y < height; y++)
    {
        grid[x, y] = !location.isTilePassable(
            new xTile.Dimensions.Location(x * 64, y * 64),
            Game1.viewport
        );
    }
}
```

## RLE Serialization

Serialize the collision grid using run-length encoding to reduce payload size:

```
[{"w":true,"c":5},{"w":false,"c":12},...]
```

Where `w` = walkable, `c` = count of consecutive tiles with the same value. Scan row-by-row (left-to-right, top-to-bottom).

## A* Pathfinding (Python Side)

Use the `pathfinding` library:

```python
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder

grid = Grid(matrix=matrix)  # 1 = walkable, 0 = blocked
start = grid.node(sx, sy)
end = grid.node(ex, ey)
finder = AStarFinder()
path, runs = finder.find_path(start, end, grid)
```

## Map Transitions

- Warps are defined in the map's `Paths` layer or via `Game1.currentLocation.warps`.
- Each warp: `warp.X`, `warp.Y` (source tile), `warp.TargetName` (destination location), `warp.TargetX`, `warp.TargetY`.
