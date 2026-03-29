# Farming Mechanics Reference

## Soil & Crops

- Tilled soil: `HoeDirt` object on the terrain layer.
- Check if tilled: `location.terrainFeatures[tile] is HoeDirt`.
- Plant a seed: `hoeDirt.plant(seedIndex, farmer, false)`.
- Water soil: `hoeDirt.state.Value = 1` (1 = watered, 0 = dry).
- Crop growth: `hoeDirt.crop.currentPhase.Value` (int, increments daily when watered).
- Harvest ready: `hoeDirt.crop.currentPhase.Value >= hoeDirt.crop.phaseDays.Count - 1`.

## Common Crop IDs (Seeds)

| Crop        | Seed ID | Season  | Days to Grow |
|-------------|---------|---------|--------------|
| Parsnip     | 472     | Spring  | 4            |
| Potato      | 475     | Spring  | 6            |
| Cauliflower | 474     | Spring  | 12           |
| Melon       | 479     | Summer  | 12           |
| Pumpkin     | 490     | Fall    | 13           |

## Tools

- **Hoe:** `Game1.player.CurrentTool is Hoe` — tills soil.
- **Watering Can:** `Game1.player.CurrentTool is WateringCan` — waters tilled soil.
- **Pickaxe:** Breaks rocks and ore.
- **Axe:** Chops trees and stumps.
- **Scythe:** Harvests crops, cuts grass.

## Tool Usage (SMAPI)

```csharp
// Switch to a tool by name
var tool = Game1.player.Items.FirstOrDefault(i => i is Tool t && t.Name == "Hoe") as Tool;
if (tool != null)
{
    Game1.player.CurrentToolIndex = Game1.player.Items.IndexOf(tool);
}

// Use the current tool at a tile
Game1.player.BeginUsingTool();
```
