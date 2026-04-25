from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


ProviderType = Literal["ollama", "openai", "gemini", "mock"]


@dataclass
class CriticConfig:
    provider: ProviderType = "ollama"
    model: str = "llama3"
    temperature: float = 0.2
    max_tokens: int = 700
    timeout_seconds: int = 90

    ollama_host: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    gemini_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))


class LLMCritic:
    """Resilient LLM critic for No-Limit Hold'em coaching feedback."""

    def __init__(self, config: Optional[CriticConfig] = None) -> None:
        self.config = config or CriticConfig()

    def generate_critique(
        self,
        game_state: dict,
        user_action: dict,
        solver_context: dict = None,
    ) -> str:
        """Public API for app integration.

        Raises ValueError when input payloads do not match expected schema.
        Returns a structured critique string in both live and fallback modes.
        """

        self._validate_state(game_state)
        self._validate_user_action(user_action)
        if solver_context is not None and not isinstance(solver_context, dict):
            raise ValueError("solver_context must be a dict when provided.")

        prompts = self._build_prompts(game_state, user_action, solver_context)
        try:
            return self._generate_response(
                system_prompt=prompts["system_prompt"],
                user_prompt=prompts["user_prompt"],
            )
        except Exception as exc:
            return self._offline_mock_critique(exc)

    @staticmethod
    def _pretty_json(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=True)

    def _build_prompts(
        self,
        game_state: Dict[str, Any],
        user_action: Dict[str, Any],
        solver_context: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        system_prompt = (
            "You are an elite No-Limit Texas Hold'em coach. "
            "Your style is tough-but-fair, concise, and educational.\n\n"
            "Primary goals:\n"
            "1) Evaluate the user's decision quality using fundamentals, GTO baselines, and exploitative context.\n"
            "2) Correct logic errors without insulting the user.\n"
            "3) Show poker math explicitly when relevant (pot odds, MDF intuition, equity requirements).\n\n"
            "Hard constraints to prevent hallucinations:\n"
            "- Use ONLY facts present in the provided game state and action history.\n"
            "- If needed data is missing, write: 'Insufficient data for exact math' and continue with bounded assumptions.\n"
            "- Never invent cards, stack sizes, bet sizes, positions, or prior actions.\n"
            "- Every numeric claim must reference input values and a formula in plain text.\n"
            "- Distinguish clearly between: FACTS, INFERENCE, and ASSUMPTIONS.\n\n"
            "Output format (strict):\n"
            "1) VERDICT: one sentence (Good / Marginal / Mistake + confidence 0-100).\n"
            "2) FACT CHECK: bullet list of table facts used.\n"
            "3) LEAKS: up to 3 strategic errors ranked by impact.\n"
            "4) MATH: pot odds/equity threshold with shown arithmetic.\n"
            "5) BETTER LINE: preferred action and why (GTO baseline + exploit adjustment).\n"
            "6) TRAINING DRILL: one concrete rule-of-thumb for next similar spot."
        )

        normalized_state = {
            "hand_id": game_state.get("hand_id"),
            "format": game_state.get("format"),
            "stakes": game_state.get("stakes"),
            "blinds": game_state.get("blinds"),
            "street": game_state.get("street"),
            "hero": game_state.get("hero"),
            "villains": game_state.get("villains", []),
            "board_cards": game_state.get("board_cards", []),
            "pot_size": game_state.get("pot_size"),
            "effective_stack": game_state.get("effective_stack"),
            "action_history": game_state.get("action_history", []),
            "reads": game_state.get("reads", []),
        }

        normalized_action = {
            "action": user_action.get("action"),
            "reasoning": user_action.get("reasoning"),
            "amount": user_action.get("amount"),
            "target_street": user_action.get("target_street"),
        }

        user_prompt = (
            "Evaluate this poker decision.\n\n"
            "GAME STATE JSON:\n"
            f"{self._pretty_json(normalized_state)}\n\n"
            "USER ACTION JSON:\n"
            f"{self._pretty_json(normalized_action)}\n\n"
            "SOLVER CONTEXT JSON (OPTIONAL):\n"
            f"{self._pretty_json(solver_context or {})}\n\n"
            "Instruction: Use the strict output format from the system prompt. "
            "If a number cannot be computed from provided inputs, say so explicitly."
        )

        raw_prompt = (
            "===== SYSTEM PROMPT =====\n"
            f"{system_prompt}\n\n"
            "===== USER PROMPT =====\n"
            f"{user_prompt}"
        )

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_prompt": raw_prompt,
        }

    def _generate_response(self, system_prompt: str, user_prompt: str) -> str:
        if self.config.provider == "ollama":
            return self._call_ollama(system_prompt, user_prompt)
        if self.config.provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        if self.config.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        if self.config.provider == "mock":
            return self._offline_mock_critique(RuntimeError("Mock provider selected."))
        raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        try:
            from ollama import Client
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency 'ollama'. Install with: pip install ollama"
            ) from exc

        client = Client(host=self.config.ollama_host)
        response = client.chat(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        )
        return response["message"]["content"]

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        if not self.config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        raise RuntimeError("OpenAI integration is not wired yet in this local-first build.")

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        if not self.config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is missing.")
        raise RuntimeError("Gemini integration is not wired yet in this local-first build.")

    def _offline_mock_critique(self, error: Exception) -> str:
        return (
            "VERDICT: Offline Mode Active. Could not reach LLM (confidence 0).\n"
            "FACT CHECK:\n"
            "- LLM request failed during provider call.\n"
            f"- Error detail: {type(error).__name__}: {error}.\n"
            "- Returning deterministic fallback output for UI continuity.\n"
            "LEAKS:\n"
            "- Placeholder: Live strategic leak analysis unavailable in offline mode.\n"
            "- Placeholder: Opponent range assessment unavailable in offline mode.\n"
            "- Placeholder: Bet-sizing critique unavailable in offline mode.\n"
            "MATH:\n"
            "- Insufficient data for exact math in offline mode.\n"
            "- Placeholder formula: required_equity = call_amount / (pot_before_call + call_amount).\n"
            "BETTER LINE:\n"
            "- Placeholder: Re-run critique once provider connectivity is restored.\n"
            "- Placeholder: Compare current line vs check/call and check/raise branches.\n"
            "TRAINING DRILL:\n"
            "- For each flop decision, write pot size, facing bet, and required equity before acting."
        )

    def _validate_state(self, game_state: Dict[str, Any]) -> None:
        if not isinstance(game_state, dict):
            raise ValueError("game_state must be a dict.")

        self._require_keys(
            obj=game_state,
            required_keys=[
                "format",
                "blinds",
                "street",
                "hero",
                "villains",
                "board_cards",
                "pot_size",
                "effective_stack",
                "action_history",
            ],
            path="game_state",
        )

        if not isinstance(game_state["format"], str) or not game_state["format"].strip():
            raise ValueError("game_state.format must be a non-empty string.")
        if not isinstance(game_state["street"], str) or not game_state["street"].strip():
            raise ValueError("game_state.street must be a non-empty string.")
        if game_state["street"] not in {"preflop", "flop", "turn", "river", "showdown"}:
            raise ValueError("game_state.street must be one of: preflop, flop, turn, river, showdown.")
        if not isinstance(game_state["pot_size"], (int, float)):
            raise ValueError("game_state.pot_size must be numeric.")
        if not isinstance(game_state["effective_stack"], (int, float)):
            raise ValueError("game_state.effective_stack must be numeric.")

        blinds = game_state["blinds"]
        if not isinstance(blinds, dict):
            raise ValueError("game_state.blinds must be a dict.")
        self._require_keys(blinds, ["small_blind", "big_blind"], "game_state.blinds")
        if not isinstance(blinds["small_blind"], (int, float)):
            raise ValueError("game_state.blinds.small_blind must be numeric.")
        if not isinstance(blinds["big_blind"], (int, float)):
            raise ValueError("game_state.blinds.big_blind must be numeric.")

        hero = game_state["hero"]
        if not isinstance(hero, dict):
            raise ValueError("game_state.hero must be a dict.")
        self._require_keys(hero, ["name", "position", "hole_cards", "stack"], "game_state.hero")
        if not isinstance(hero["name"], str) or not hero["name"].strip():
            raise ValueError("game_state.hero.name must be a non-empty string.")
        if not isinstance(hero["position"], str) or not hero["position"].strip():
            raise ValueError("game_state.hero.position must be a non-empty string.")
        if not isinstance(hero["stack"], (int, float)):
            raise ValueError("game_state.hero.stack must be numeric.")
        if not isinstance(hero["hole_cards"], list) or len(hero["hole_cards"]) != 2:
            raise ValueError("game_state.hero.hole_cards must be a 2-item list.")
        if any(not isinstance(card, str) or not card.strip() for card in hero["hole_cards"]):
            raise ValueError("game_state.hero.hole_cards must contain non-empty card strings.")

        villains = game_state["villains"]
        if not isinstance(villains, list):
            raise ValueError("game_state.villains must be a list.")
        for idx, villain in enumerate(villains):
            if not isinstance(villain, dict):
                raise ValueError(f"game_state.villains[{idx}] must be a dict.")
            self._require_keys(villain, ["name", "position", "stack"], f"game_state.villains[{idx}]")
            if not isinstance(villain["name"], str) or not villain["name"].strip():
                raise ValueError(f"game_state.villains[{idx}].name must be a non-empty string.")
            if not isinstance(villain["position"], str) or not villain["position"].strip():
                raise ValueError(f"game_state.villains[{idx}].position must be a non-empty string.")
            if not isinstance(villain["stack"], (int, float)):
                raise ValueError(f"game_state.villains[{idx}].stack must be numeric.")

        board_cards = game_state["board_cards"]
        if not isinstance(board_cards, list):
            raise ValueError("game_state.board_cards must be a list.")
        if len(board_cards) > 5:
            raise ValueError("game_state.board_cards cannot contain more than 5 cards.")
        if any(not isinstance(card, str) or not card.strip() for card in board_cards):
            raise ValueError("game_state.board_cards must contain non-empty card strings.")

        action_history = game_state["action_history"]
        if not isinstance(action_history, list):
            raise ValueError("game_state.action_history must be a list.")
        for idx, action in enumerate(action_history):
            if not isinstance(action, dict):
                raise ValueError(f"game_state.action_history[{idx}] must be a dict.")
            self._require_keys(action, ["street", "actor", "action"], f"game_state.action_history[{idx}]")
            if not isinstance(action["street"], str) or not action["street"].strip():
                raise ValueError(f"game_state.action_history[{idx}].street must be a non-empty string.")
            if not isinstance(action["actor"], str) or not action["actor"].strip():
                raise ValueError(f"game_state.action_history[{idx}].actor must be a non-empty string.")
            if not isinstance(action["action"], str) or not action["action"].strip():
                raise ValueError(f"game_state.action_history[{idx}].action must be a non-empty string.")
            if "size" in action and action["size"] is not None and not isinstance(action["size"], (int, float)):
                raise ValueError(f"game_state.action_history[{idx}].size must be numeric when provided.")

    def _validate_user_action(self, user_action: Dict[str, Any]) -> None:
        if not isinstance(user_action, dict):
            raise ValueError("user_action must be a dict.")
        self._require_keys(user_action, ["action", "reasoning"], "user_action")
        if not isinstance(user_action["action"], str) or not user_action["action"].strip():
            raise ValueError("user_action.action must be a non-empty string.")
        if not isinstance(user_action["reasoning"], str) or not user_action["reasoning"].strip():
            raise ValueError("user_action.reasoning must be a non-empty string.")
        if "amount" in user_action and user_action["amount"] is not None and not isinstance(user_action["amount"], (int, float)):
            raise ValueError("user_action.amount must be numeric when provided.")

    @staticmethod
    def _require_keys(obj: Dict[str, Any], required_keys: list[str], path: str) -> None:
        missing = [key for key in required_keys if key not in obj]
        if missing:
            raise ValueError(f"{path} is missing required key(s): {', '.join(missing)}.")
