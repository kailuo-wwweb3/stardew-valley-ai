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
