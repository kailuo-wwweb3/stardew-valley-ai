# Core Mechanics Reference

## Time

- Game time is an integer: `600` = 6:00 AM, `2600` = 2:00 AM (next day).
- Each 10-minute increment takes ~7 real seconds.
- The player passes out at `2:00 AM` (2600) with a gold penalty.
- Access via: `Game1.timeOfDay` (int).

## Movement

- The game world uses a tile grid. Each tile is 64x64 pixels.
- Player position in pixels: `Game1.player.Position` (Vector2).
- Player tile position: `Game1.player.Tile` (Vector2) — returns tile coordinates.
- Movement speed: `Game1.player.Speed` (int, default 2) + `Game1.player.addedSpeed`.
- To move the player, set `Game1.player.Position` each tick or use controller input simulation.

## Stamina (Energy)

- `Game1.player.Stamina` (float) — current energy.
- `Game1.player.MaxStamina` (int) — max energy (default 270, upgrades to 508).
- Using a tool costs energy. Eating food restores energy.
- At 0 energy the player moves very slowly. Negative energy causes exhaustion.

## Player State

- Current location name: `Game1.player.currentLocation.Name` (string).
- Current tool: `Game1.player.CurrentTool` (Tool object).
- Facing direction: `Game1.player.FacingDirection` (int: 0=up, 1=right, 2=down, 3=left).

## Menus

- `Game1.activeClickableMenu` — non-null when a menu/dialogue is open.
- Check with: `Game1.activeClickableMenu != null`.

## SMAPI Entry Point

```csharp
public class ModEntry : Mod
{
    public override void Entry(IModHelper helper)
    {
        helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
        helper.Events.GameLoop.SaveLoaded += OnSaveLoaded;
        helper.Events.GameLoop.DayStarted += OnDayStarted;
    }
}
```
