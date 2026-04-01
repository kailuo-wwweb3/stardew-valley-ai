using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Xna.Framework;
using StardewValley;
using xTile.Dimensions;

namespace StardewAgent
{
    /// <summary>
    /// Captures game state snapshots and map collision data.
    /// </summary>
    public static class GameStateService
    {
        /// <summary>
        /// Returns the current game state as a dictionary suitable for JSON serialization.
        /// </summary>
        public static Dictionary<string, object> GetState()
        {
            var player = Game1.player;
            var location = player.currentLocation;

            var state = new Dictionary<string, object>
            {
                ["isMenuOpen"] = Game1.activeClickableMenu != null,
                ["timeOfDay"] = Game1.timeOfDay,
                ["dayOfMonth"] = Game1.dayOfMonth,
                ["season"] = Game1.currentSeason,
                ["year"] = Game1.year,
                ["location"] = location?.Name ?? "unknown",
                ["tileX"] = (int)player.Tile.X,
                ["tileY"] = (int)player.Tile.Y,
                ["posX"] = player.Position.X,
                ["posY"] = player.Position.Y,
                ["facingDirection"] = player.FacingDirection,
                ["stamina"] = player.Stamina,
                ["maxStamina"] = player.MaxStamina,
                ["health"] = player.health,
                ["maxHealth"] = player.maxHealth,
                ["currentTool"] = player.CurrentTool?.Name ?? "none",
                ["money"] = player.Money,
                ["activeMenu"] = Game1.activeClickableMenu?.GetType().Name ?? "none",
                ["localTiles"] = GetLocalTileGrid(location, (int)player.Tile.X, (int)player.Tile.Y, 3),
                ["inventory"] = GetInventory(player)
            };

            return state;
        }

        /// <summary>
        /// Returns a (2*radius+1) x (2*radius+1) grid of tile info around the player.
        /// Each tile reports whether it is walkable and what object/feature is on it.
        /// </summary>
        private static List<Dictionary<string, object>> GetLocalTileGrid(
            GameLocation location, int centerX, int centerY, int radius)
        {
            var tiles = new List<Dictionary<string, object>>();
            if (location == null) return tiles;

            for (int dy = -radius; dy <= radius; dy++)
            {
                for (int dx = -radius; dx <= radius; dx++)
                {
                    int tx = centerX + dx;
                    int ty = centerY + dy;
                    var tileVec = new Vector2(tx, ty);

                    bool walkable = IsWalkable(location, tx, ty);
                    string feature = "none";

                    if (location.Objects.ContainsKey(tileVec))
                        feature = location.Objects[tileVec].Name;
                    else if (location.terrainFeatures.ContainsKey(tileVec))
                        feature = location.terrainFeatures[tileVec].GetType().Name;

                    var tileDict = new Dictionary<string, object>
                    {
                        ["x"] = tx,
                        ["y"] = ty,
                        ["walkable"] = walkable,
                        ["feature"] = feature
                    };

                    // Enhanced HoeDirt detail for farming tests
                    if (location.terrainFeatures.ContainsKey(tileVec) &&
                        location.terrainFeatures[tileVec] is StardewValley.TerrainFeatures.HoeDirt hd)
                    {
                        tileDict["watered"] = hd.state.Value == 1;
                        tileDict["hasCrop"] = hd.crop != null;
                        if (hd.crop != null)
                        {
                            tileDict["cropPhase"] = hd.crop.currentPhase.Value;
                            tileDict["cropReady"] = hd.crop.currentPhase.Value >= hd.crop.phaseDays.Count - 1;
                        }
                    }

                    tiles.Add(tileDict);
                }
            }

            return tiles;
        }

        /// <summary>
        /// Checks whether a tile is walkable (passable and not blocked by objects/buildings).
        /// </summary>
        private static bool IsWalkable(GameLocation location, int tileX, int tileY)
        {
            try
            {
                var tileVec = new Vector2(tileX, tileY);

                // Check tile passability from the map layers
                var loc = new Location(tileX * 64, tileY * 64);
                if (!location.isTilePassable(loc, Game1.viewport))
                    return false;

                // Check for blocking objects
                if (location.Objects.ContainsKey(tileVec) && !location.Objects[tileVec].isPassable())
                    return false;

                // Check for blocking terrain features (e.g., trees)
                if (location.terrainFeatures.ContainsKey(tileVec) &&
                    !location.terrainFeatures[tileVec].isPassable())
                    return false;

                return true;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Serializes the player's inventory as a list of item dictionaries.
        /// </summary>
        private static List<Dictionary<string, object>> GetInventory(Farmer player)
        {
            var inventory = new List<Dictionary<string, object>>();
            for (int i = 0; i < player.Items.Count; i++)
            {
                var item = player.Items[i];
                if (item != null)
                {
                    inventory.Add(new Dictionary<string, object>
                    {
                        ["slot"] = i,
                        ["itemId"] = item.ItemId,
                        ["name"] = item.Name,
                        ["stack"] = item.Stack,
                        ["category"] = item.Category
                    });
                }
            }
            return inventory;
        }

        /// <summary>
        /// Returns the full collision matrix for the current location using RLE encoding.
        /// Format: [{"w": true/false, "c": count}, ...]
        /// Scanned row-by-row, left-to-right, top-to-bottom.
        /// </summary>
        public static Dictionary<string, object> GetMapData()
        {
            var location = Game1.player.currentLocation;
            if (location == null)
            {
                return new Dictionary<string, object>
                {
                    ["error"] = "No location loaded"
                };
            }

            var map = location.Map;
            int width = map.Layers[0].LayerWidth;
            int height = map.Layers[0].LayerHeight;

            // Build RLE-encoded collision data
            var rle = new List<Dictionary<string, object>>();
            bool? currentWalkable = null;
            int currentCount = 0;

            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    bool walkable = IsWalkable(location, x, y);

                    if (currentWalkable == null)
                    {
                        currentWalkable = walkable;
                        currentCount = 1;
                    }
                    else if (walkable == currentWalkable)
                    {
                        currentCount++;
                    }
                    else
                    {
                        rle.Add(new Dictionary<string, object>
                        {
                            ["w"] = currentWalkable.Value,
                            ["c"] = currentCount
                        });
                        currentWalkable = walkable;
                        currentCount = 1;
                    }
                }
            }

            // Flush the last run
            if (currentCount > 0 && currentWalkable != null)
            {
                rle.Add(new Dictionary<string, object>
                {
                    ["w"] = currentWalkable.Value,
                    ["c"] = currentCount
                });
            }

            return new Dictionary<string, object>
            {
                ["location"] = location.Name,
                ["width"] = width,
                ["height"] = height,
                ["collisionRLE"] = rle
            };
        }
    }
}
