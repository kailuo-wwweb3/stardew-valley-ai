using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Xna.Framework;
using StardewValley;
using StardewValley.Tools;

namespace StardewAgent
{
    /// <summary>
    /// Handles action execution: tool use, facing direction, and stamina checks.
    /// </summary>
    public static class ActionService
    {
        /// <summary>
        /// Faces the player toward a target tile and uses the current tool.
        /// Returns a status message.
        /// </summary>
        public static string UseTool(int targetX, int targetY, string toolName = null)
        {
            var player = Game1.player;

            // Check stamina before using tool
            if (player.Stamina <= 2)
                return "error: stamina too low to use tool";

            // Switch tool if specified
            if (toolName != null)
            {
                bool found = false;
                for (int i = 0; i < player.Items.Count; i++)
                {
                    if (player.Items[i] is Tool t && t.Name.Equals(toolName, StringComparison.OrdinalIgnoreCase))
                    {
                        player.CurrentToolIndex = i;
                        found = true;
                        break;
                    }
                }
                if (!found)
                    return $"error: tool '{toolName}' not found in inventory";
            }

            if (player.CurrentTool == null)
                return "error: no tool equipped";

            // Face toward target
            int playerTileX = (int)player.Tile.X;
            int playerTileY = (int)player.Tile.Y;
            player.FacingDirection = GetFacingDirection(playerTileX, playerTileY, targetX, targetY);

            // Begin using the tool
            player.BeginUsingTool();

            return "ok";
        }

        /// <summary>
        /// Calculates facing direction from source to target tile.
        /// </summary>
        public static int GetFacingDirection(int fromX, int fromY, int toX, int toY)
        {
            int dx = toX - fromX;
            int dy = toY - fromY;

            // Prefer the axis with the larger delta
            if (Math.Abs(dx) >= Math.Abs(dy))
                return dx >= 0 ? 1 : 3; // right : left
            else
                return dy >= 0 ? 2 : 0; // down : up
        }

        /// <summary>
        /// Clears all objects and terrain features within a radius of the center tile.
        /// Used for test setup to ensure idempotent test environments.
        /// </summary>
        public static string ClearArea(int centerX, int centerY, int radius)
        {
            var location = Game1.player.currentLocation;
            int removed = 0;

            for (int dy = -radius; dy <= radius; dy++)
            {
                for (int dx = -radius; dx <= radius; dx++)
                {
                    var tileVec = new Vector2(centerX + dx, centerY + dy);
                    if (location.Objects.Remove(tileVec))
                        removed++;
                    if (location.terrainFeatures.Remove(tileVec))
                        removed++;
                }
            }

            return "ok";
        }

        /// <summary>
        /// Faces the player toward a target tile and triggers a right-click interaction.
        /// If itemName is specified, selects that item as the active item first (needed for planting seeds).
        /// </summary>
        public static string Interact(int targetX, int targetY, string itemName = null)
        {
            var player = Game1.player;
            player.FacingDirection = GetFacingDirection(
                (int)player.Tile.X, (int)player.Tile.Y, targetX, targetY);

            // Select item if specified (e.g., seeds for planting)
            if (itemName != null)
            {
                bool found = false;
                for (int i = 0; i < player.Items.Count; i++)
                {
                    if (player.Items[i] != null &&
                        player.Items[i].Name.Equals(itemName, StringComparison.OrdinalIgnoreCase))
                    {
                        player.CurrentToolIndex = i;
                        found = true;
                        break;
                    }
                }
                if (!found)
                    return $"error: item '{itemName}' not found in inventory";
            }

            var location = player.currentLocation;

            // Try to place item on the tile (handles seed planting on HoeDirt)
            if (player.ActiveObject != null)
            {
                var tileVec = new Vector2(targetX, targetY);
                if (Utility.tryToPlaceItem(location, player.ActiveObject, (int)(tileVec.X * 64), (int)(tileVec.Y * 64)))
                {
                    if (player.ActiveObject.Stack <= 0)
                        player.removeItemFromInventory(player.ActiveObject);
                    return "ok";
                }
            }

            // Fall back to checkAction (NPCs, objects, etc.)
            var tileLoc = new xTile.Dimensions.Location(targetX * 64, targetY * 64);
            location.checkAction(tileLoc, Game1.viewport, player);
            return "ok";
        }

        /// <summary>
        /// Spawns a game object at the specified tile. Removes any existing object first.
        /// </summary>
        public static string SpawnObject(int tileX, int tileY, string objectId)
        {
            var location = Game1.player.currentLocation;
            var tileVec = new Vector2(tileX, tileY);
            location.Objects.Remove(tileVec);

            var qualifiedId = objectId.StartsWith("(") ? objectId : "(O)" + objectId;
            var item = ItemRegistry.Create(qualifiedId);
            if (item is StardewValley.Object obj)
            {
                obj.TileLocation = tileVec;
                location.Objects.Add(tileVec, obj);
                return "ok";
            }
            return $"error: could not create object '{objectId}'";
        }

        /// <summary>
        /// Adds an item to the player's inventory.
        /// </summary>
        public static string AddItem(string itemId, int count)
        {
            var item = ItemRegistry.Create(itemId, count);
            if (item != null)
            {
                Game1.player.addItemToInventory(item);
                return "ok";
            }
            return $"error: could not create item '{itemId}'";
        }

        /// <summary>
        /// Warps the player to a specified location and tile.
        /// </summary>
        public static string WarpPlayer(string locationName, int tileX, int tileY)
        {
            var player = Game1.player;
            if (player.currentLocation?.Name == locationName)
            {
                // Same location — just reposition
                player.Position = new Vector2(tileX * 64, tileY * 64);
                player.Halt();
            }
            else
            {
                Game1.warpFarmer(locationName, tileX, tileY, false);
            }
            return "ok";
        }

        /// <summary>
        /// Validates a path array and converts tile coordinates to pixel positions
        /// for sub-tile movement. Returns the pixel path or null with an error message.
        /// </summary>
        public static List<Vector2> BuildPixelPath(List<int[]> tilePath, out string error)
        {
            error = null;
            if (tilePath == null || tilePath.Count == 0)
            {
                error = "error: empty path";
                return null;
            }

            var pixelPath = new List<Vector2>();
            foreach (var tile in tilePath)
            {
                if (tile.Length < 2)
                {
                    error = "error: each path point must have [x, y]";
                    return null;
                }
                // Align to tile origin (tile * 64) so Tile property reports correctly
                pixelPath.Add(new Vector2(tile[0] * 64, tile[1] * 64));
            }

            return pixelPath;
        }
    }
}
