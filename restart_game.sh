#!/bin/bash
# Restart Stardew Valley via SMAPI/Steam and wait for the mod to be ready.
#
# Usage: ./restart_game.sh [--no-wait]

set -e

GAME_DIR="$HOME/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS"
MOD_URL="http://127.0.0.1:7880/state"
STEAM_APP_ID=413150
MAX_WAIT=60

# 1. Kill the game if running
echo "Stopping Stardew Valley..."
pkill -f "StardewModdingAPI" 2>/dev/null && echo "  Game process killed." || echo "  No game process found."
sleep 2

# 2. Rebuild the mod
echo "Building mod..."
cd "$(dirname "$0")/mod/StardewAgent"
dotnet build --verbosity quiet 2>&1
echo "  Build complete."

# 3. Launch SMAPI directly (bypasses Steam's .command dialog)
echo "Launching SMAPI..."
cd "$GAME_DIR"
./StardewModdingAPI --use-current-shell &

if [[ "$1" == "--no-wait" ]]; then
    echo "Launched. Not waiting for mod to be ready."
    exit 0
fi

# 4. Wait for the mod's HTTP server to respond
echo "Waiting for mod to be ready..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    if curl -s --max-time 2 "$MOD_URL" > /dev/null 2>&1; then
        echo "  Mod is ready! (${elapsed}s)"
        exit 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    printf "  %ds...\r" $elapsed
done

echo ""
echo "WARNING: Mod did not respond within ${MAX_WAIT}s."
echo "  You may need to load a save file manually."
exit 1
