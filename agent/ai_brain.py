"""
AI Brain — LLM integration for decision-making.

Supports Anthropic (Claude), OpenAI, and DeepSeek APIs.
Set the provider via the LLM_PROVIDER env var (default: anthropic).

Called only when the agent is `idle` (needs a new plan) or `blocked`
(needs to reason about an obstacle). Returns structured JSON actions.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

HARNESS_DIR = Path(__file__).parent.parent / ".harness"

# Provider config: env var → (module, default model, base_url override)
PROVIDERS = {
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
}

SYSTEM_PROMPT = """\
You are an AI agent playing Stardew Valley. You observe the game state and decide \
what action to take next. You must respond with a single JSON object — no other text.

## Available actions

1. **walk_to** — Walk to a tile coordinate.
   ```json
   {"action": "walk_to", "x": 10, "y": 15, "reason": "Walking to crop field"}
   ```

2. **use_tool** — Use a tool on a target tile. Optionally specify which tool.
   ```json
   {"action": "use_tool", "x": 10, "y": 15, "tool": "Pickaxe", "reason": "Breaking rock blocking path"}
   ```

3. **wait** — Do nothing for now (e.g., waiting for a menu to close).
   ```json
   {"action": "wait", "reason": "Nothing urgent to do right now"}
   ```

## Rules
- Always include a "reason" field explaining your decision.
- Only use tools that exist in the player's inventory.
- If stamina is low, prefer to stop working and head to bed.
- If it's past midnight (time >= 2400), go to bed immediately.
- If blocked by an obstacle, use the appropriate tool to clear it.
- Plan productive tasks: water crops, clear farm debris, plant seeds, harvest.
- Prefer simple, achievable goals over ambitious multi-step plans.
"""


class AIBrain:
    """Interfaces with an LLM provider to make gameplay decisions."""

    def __init__(self, provider: str = None, model: str = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "anthropic")).lower()
        if self.provider not in PROVIDERS:
            raise ValueError(f"Unknown provider '{self.provider}'. Supported: {list(PROVIDERS.keys())}")

        config = PROVIDERS[self.provider]
        self.model = model or os.getenv("LLM_MODEL") or config["default_model"]
        self._day_plan = None
        self._mechanics_cache = {}

        # Initialize the appropriate client
        if self.provider == "anthropic":
            import anthropic
            api_key = os.getenv(config["env_key"])
            self._client = anthropic.Anthropic(api_key=api_key)
        else:
            # OpenAI and DeepSeek both use the openai SDK
            import openai
            api_key = os.getenv(config["env_key"])
            base_url = config.get("base_url")
            self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

        print(f"[AI] Provider: {self.provider}, Model: {self.model}")

    def decide(self, state: dict, context: str = "") -> dict | None:
        """
        Ask the LLM to decide the next action based on game state.

        Args:
            state: Current game state from /state endpoint.
            context: Additional context (e.g., why we're blocked).

        Returns:
            Parsed action dict or None if the LLM fails.
        """
        user_msg = self._build_prompt(state, context)

        system = SYSTEM_PROMPT
        mechanics = self._get_relevant_mechanics(context)
        if mechanics:
            system += f"\n\n## Game Mechanics Reference\n{mechanics}"

        try:
            text = self._call_llm(system, user_msg)

            # Extract JSON from response (handle markdown code blocks)
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            action = json.loads(text)
            print(f"[AI] Decision: {action.get('action')} — {action.get('reason', '')}")
            return action

        except json.JSONDecodeError as e:
            print(f"[AI] Failed to parse LLM response: {e}")
            print(f"[AI] Raw response: {text[:200]}")
            return None
        except Exception as e:
            print(f"[AI] API error: {e}")
            return None

    def _call_llm(self, system: str, user_msg: str) -> str:
        """Call the LLM and return the response text."""
        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=self.model,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            return response.content[0].text.strip()
        else:
            # OpenAI / DeepSeek compatible API
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
            )
            return response.choices[0].message.content.strip()

    def _build_prompt(self, state: dict, context: str) -> str:
        """Build the user prompt with compressed game state."""
        parts = []

        time_str = self._format_time(state.get("timeOfDay", 600))
        parts.append(f"## Current State")
        parts.append(f"- Time: {time_str}")
        parts.append(f"- Day: {state.get('season', '?')} {state.get('dayOfMonth', '?')}, Year {state.get('year', '?')}")
        parts.append(f"- Location: {state.get('location', '?')}")
        parts.append(f"- Position: tile ({state.get('tileX', '?')}, {state.get('tileY', '?')})")
        parts.append(f"- Stamina: {state.get('stamina', '?')}/{state.get('maxStamina', '?')}")
        parts.append(f"- Health: {state.get('health', '?')}/{state.get('maxHealth', '?')}")
        parts.append(f"- Current tool: {state.get('currentTool', 'none')}")
        parts.append(f"- Money: {state.get('money', 0)}g")
        parts.append(f"- Menu open: {state.get('isMenuOpen', False)}")

        # Local tiles — only include non-empty/blocked tiles to save tokens
        local_tiles = state.get("localTiles", [])
        notable_tiles = []
        for tile in local_tiles:
            if not tile.get("walkable", True) or tile.get("feature", "none") != "none":
                notable_tiles.append(
                    f"  ({tile['x']},{tile['y']}): walkable={tile['walkable']}, feature={tile['feature']}"
                )
        if notable_tiles:
            parts.append(f"\n## Nearby tiles (notable only)")
            parts.extend(notable_tiles)

        if context:
            parts.append(f"\n## Context")
            parts.append(context)

        parts.append(f"\nWhat action should I take? Respond with a single JSON object.")
        return "\n".join(parts)

    def _get_relevant_mechanics(self, context: str) -> str:
        """Load relevant mechanics files based on context keywords."""
        mechanics = []
        context_lower = context.lower() if context else ""

        core = self._load_mechanics("04_mechanics_core.md")
        if core:
            mechanics.append(core)

        if any(kw in context_lower for kw in ["farm", "crop", "water", "plant", "harvest", "hoe", "seed"]):
            farming = self._load_mechanics("04_mechanics_farming.md")
            if farming:
                mechanics.append(farming)

        if any(kw in context_lower for kw in ["path", "walk", "blocked", "navigate", "stuck"]):
            nav = self._load_mechanics("04_mechanics_navigation.md")
            if nav:
                mechanics.append(nav)

        return "\n\n".join(mechanics) if mechanics else ""

    def _load_mechanics(self, filename: str) -> str | None:
        """Load and cache a mechanics file."""
        if filename in self._mechanics_cache:
            return self._mechanics_cache[filename]

        path = HARNESS_DIR / filename
        if path.exists():
            content = path.read_text()
            self._mechanics_cache[filename] = content
            return content
        return None

    @staticmethod
    def _format_time(game_time: int) -> str:
        hours = game_time // 100
        minutes = game_time % 100
        period = "AM" if hours < 12 else "PM"
        display_hours = hours % 12 or 12
        return f"{display_hours}:{minutes:02d} {period}"
