"""
Stardew Valley Automation Bot
Controls character movement and basic actions via keyboard simulation.

Usage:
    source venv/bin/activate
    python stardew_bot.py

IMPORTANT: macOS requires Accessibility permissions for pyautogui.
  System Settings > Privacy & Security > Accessibility > enable your terminal app.

Make sure Stardew Valley is the focused window before running.
"""

import pyautogui
import time
import sys

# Safety: pyautogui will raise an exception if the mouse is moved to a corner
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05  # small delay between pyautogui calls

# Stardew Valley default key bindings
KEYS = {
    "up": "w",
    "down": "s",
    "left": "a",
    "right": "d",
    "action": "x",       # check/do action (default: right-click equivalent)
    "use_tool": "c",     # use tool (default: left-click equivalent)
    "menu": "e",         # open menu / inventory
    "journal": "f",      # open journal
    "run": "shift",      # hold to run (if enabled)
}


def wait_for_game(seconds=3):
    """Give the user time to switch to the Stardew Valley window."""
    print(f"Switching to Stardew Valley in {seconds} seconds...")
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("Starting!")


def move(direction, duration=0.5):
    """Move the character in a direction for a given duration (seconds)."""
    key = KEYS.get(direction)
    if not key:
        print(f"Unknown direction: {direction}")
        return
    print(f"Moving {direction} for {duration}s")
    pyautogui.keyDown(key)
    time.sleep(duration)
    pyautogui.keyUp(key)


def use_tool():
    """Use the currently equipped tool."""
    print("Using tool")
    pyautogui.press(KEYS["use_tool"])


def do_action():
    """Perform an action (interact with objects/NPCs)."""
    print("Performing action")
    pyautogui.press(KEYS["action"])


def open_menu():
    """Open the inventory/menu."""
    print("Opening menu")
    pyautogui.press(KEYS["menu"])


def select_toolbar_slot(slot):
    """Select a toolbar slot (1-9)."""
    if 1 <= slot <= 9:
        print(f"Selecting toolbar slot {slot}")
        pyautogui.press(str(slot))


def move_path(steps):
    """
    Move along a path defined as a list of (direction, duration) tuples.
    Example: [("right", 1.0), ("down", 0.5), ("left", 1.0)]
    """
    for direction, duration in steps:
        move(direction, duration)
        time.sleep(0.1)  # brief pause between steps


# ---------------------------------------------------------------------------
# Example routines - customize these for your farm!
# ---------------------------------------------------------------------------

def demo_walk_square():
    """Walk in a square pattern as a demo."""
    print("\n--- Demo: Walking in a square ---")
    path = [
        ("right", 1.0),
        ("down", 1.0),
        ("left", 1.0),
        ("up", 1.0),
    ]
    move_path(path)
    print("Square complete!\n")


def demo_water_crops():
    """
    Example: walk right along a row, using the tool at each step.
    Equip your watering can to slot 1 before running this.
    """
    print("\n--- Demo: Watering a row of crops ---")
    select_toolbar_slot(1)  # select watering can
    time.sleep(0.3)

    for _ in range(5):
        use_tool()
        time.sleep(0.4)
        move("right", 0.3)
        time.sleep(0.2)

    print("Done watering!\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("  Stardew Valley Automation Bot")
    print("=" * 50)
    print()
    print("Available demos:")
    print("  1 - Walk in a square")
    print("  2 - Water a row of crops (equip watering can to slot 1)")
    print("  q - Quit")
    print()
    print("TIP: Move your mouse to any screen corner to emergency-stop (failsafe).")
    print()

    while True:
        choice = input("Choose a demo (1/2/q): ").strip().lower()

        if choice == "q":
            print("Bye!")
            sys.exit(0)
        elif choice == "1":
            wait_for_game()
            demo_walk_square()
        elif choice == "2":
            wait_for_game()
            demo_water_crops()
        else:
            print("Invalid choice, try again.")


if __name__ == "__main__":
    main()
