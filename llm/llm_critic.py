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

    def _normalize_game_state(
        self,
        game_state: Dict[str, Any],
        user_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Produce a canonical prompt payload from either schema type.

        Engine schema is detected by the presence of a nested 'table' key.
        Legacy mock schema uses flat top-level keys.

        Also annotates the action_history so the LLM always knows:
        - Which street each action belongs to, in sequence order.
        - Which single action is the DECISION UNDER REVIEW (the hero's
          most recent action on the current street, or the submitted
          user_action if it has not yet been committed to history).
        """

        if "table" in game_state:
            # ── Engine schema ────────────────────────────────────────────────
            table = game_state["table"]
            current_street = str(table.get("street", "preflop")).lower()
            if current_street == "finished":
                current_street = "river"

            hero_id = game_state.get("hero_player_id", "")
            players = game_state.get("players", [])
            hero_record = next(
                (p for p in players if p.get("player_id") == hero_id or p.get("is_hero")),
                {},
            )
            villain_records = [
                {
                    "name": p.get("name", p.get("player_id", "?")),
                    "position": p.get("position", "?"),
                    "stack": p.get("stack", 0),
                    "has_folded": p.get("has_folded", False),
                    "is_all_in": p.get("is_all_in", False),
                }
                for p in players
                if not (p.get("player_id") == hero_id or p.get("is_hero"))
            ]

            hero_view = {
                "name": hero_record.get("name", "Hero"),
                "position": hero_record.get("position", "?"),
                "hole_cards": hero_record.get("hole_cards", []),
                "stack": hero_record.get("stack", 0),
                "contribution_this_street": hero_record.get("contribution_this_street", 0),
            }

            raw_history: Dict[str, list] = game_state.get("action_history", {})
            small_blind = table.get("small_blind", 0)
            big_blind = table.get("big_blind", 0)

            canonical = {
                "hand_id": game_state.get("hand_id"),
                "format": "No-Limit Texas Hold'em",
                "stakes": f"${small_blind}/${big_blind}",
                "small_blind": small_blind,
                "big_blind": big_blind,
                "current_street": current_street,
                "board_cards": table.get("board_cards", []),
                "pot_total": table.get("pot_total", 0),
                "current_bet_to_call": table.get("current_bet_to_call", 0),
                "effective_stack": hero_view["stack"],
                "hero": hero_view,
                "villains": villain_records,
                "reads": game_state.get("reads", []),
            }

        else:
            # ── Legacy mock schema ───────────────────────────────────────────
            blinds = game_state.get("blinds", {})
            current_street = str(game_state.get("street", "preflop")).lower()
            raw_history = game_state.get("action_history", [])
            # Normalise flat list → dict-by-street so history rendering is shared.
            if isinstance(raw_history, list):
                hist_by_street: Dict[str, list] = {}
                for act in raw_history:
                    s = act.get("street", "preflop")
                    hist_by_street.setdefault(s, []).append(act)
                raw_history = hist_by_street

            canonical = {
                "hand_id": game_state.get("hand_id"),
                "format": game_state.get("format", "No-Limit Texas Hold'em"),
                "stakes": game_state.get("stakes"),
                "small_blind": blinds.get("small_blind", 0),
                "big_blind": blinds.get("big_blind", 0),
                "current_street": current_street,
                "board_cards": game_state.get("board_cards", []),
                "pot_total": game_state.get("pot_size", 0),
                "current_bet_to_call": game_state.get("current_bet_to_call", 0),
                "effective_stack": game_state.get("effective_stack", 0),
                "hero": game_state.get("hero", {}),
                "villains": game_state.get("villains", []),
                "reads": game_state.get("reads", []),
            }

        # ── Build ordered action history for the prompt ──────────────────────
        street_order = ["preflop", "flop", "turn", "river"]
        ordered_history: Dict[str, Any] = {}
        all_actions_flat: list = []

        for st in street_order:
            actions = raw_history.get(st, [])
            if not actions:
                continue
            # Sort by sequence number when available; preserve insertion order otherwise.
            sorted_actions = sorted(actions, key=lambda a: a.get("sequence", 0))
            labeled: list = []
            for act in sorted_actions:
                labeled.append({
                    "seq": act.get("sequence"),
                    "player": act.get("player_id") or act.get("actor") or "?",
                    "action": act.get("action"),
                    "amount": act.get("amount"),
                    "reasoning": act.get("reasoning") or None,
                    "is_forced": act.get("is_forced", False),
                })
            ordered_history[st] = labeled
            all_actions_flat.extend(labeled)

        # The DECISION UNDER REVIEW is always the submitted user_action.
        # History entries on the current street are prior context only
        # (e.g. hero checked, BTN bet, and now hero is responding — the
        # check is context; the response is the decision under review).
        hero_name = canonical.get("hero", {}).get("name", "Hero")
        hero_id_or_name = (
            game_state.get("hero_player_id")
            or canonical.get("hero", {}).get("name", "Hero")
        )

        decision_action = {
            "player": hero_name,
            "action": user_action.get("action"),
            "amount": user_action.get("amount"),
            "reasoning": user_action.get("reasoning"),
        }

        # Provide the most recent committed hero action on this street as
        # additional context so the LLM understands the sequence of events.
        prior_hero_action = None
        current_street_actions = ordered_history.get(current_street, [])
        for act in reversed(current_street_actions):
            player_matches = (act["player"] == hero_id_or_name) or (act["player"] == hero_name)
            if player_matches and not act.get("is_forced"):
                prior_hero_action = act
                break
        canonical["prior_hero_action_this_street"] = prior_hero_action

        canonical["ordered_action_history"] = ordered_history
        canonical["decision_under_review"] = decision_action

        return canonical

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
            "Action history reading rules:\n"
            "- 'ordered_action_history' lists every action in sequence order, grouped by street.\n"
            "- 'decision_under_review' is the SINGLE action you must evaluate. Do NOT critique other actions.\n"
            "- The current street is in 'current_street'. Prior street history is context only.\n\n"
            "Output format (strict):\n"
            "1) VERDICT: one sentence (Good / Marginal / Mistake + confidence 0-100).\n"
            "2) FACT CHECK: bullet list of table facts used.\n"
            "3) LEAKS: up to 3 strategic errors ranked by impact.\n"
            "4) MATH: pot odds/equity threshold with shown arithmetic.\n"
            "5) BETTER LINE: preferred action and why (GTO baseline + exploit adjustment).\n"
            "6) TRAINING DRILL: one concrete rule-of-thumb for next similar spot."
        )

        canonical = self._normalize_game_state(game_state, user_action)

        normalized_action = {
            "action": user_action.get("action"),
            "reasoning": user_action.get("reasoning"),
            "amount": user_action.get("amount"),
        }

        user_prompt = (
            "Evaluate this poker decision.\n\n"
            "GAME STATE JSON:\n"
            f"{self._pretty_json(canonical)}\n\n"
            "USER ACTION (DECISION UNDER REVIEW):\n"
            f"{self._pretty_json(normalized_action)}\n\n"
            "SOLVER CONTEXT JSON (OPTIONAL):\n"
            f"{self._pretty_json(solver_context or {})}\n\n"
            "Instruction: Focus your critique ONLY on the 'decision_under_review' action. "
            "Use the strict output format. "
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

        # Detect schema type by presence of nested 'table' key (engine schema)
        # vs top-level 'street' key (legacy mock schema used in dev/tests).
        if "table" in game_state:
            self._validate_state_engine_schema(game_state)
        else:
            self._validate_state_legacy_schema(game_state)

    def _validate_state_engine_schema(self, game_state: Dict[str, Any]) -> None:
        """Validate the live engine GameState produced by Agent 1's GameManager."""

        self._require_keys(
            game_state,
            ["table", "players", "action_history", "hero_player_id"],
            "game_state",
        )

        table = game_state["table"]
        if not isinstance(table, dict):
            raise ValueError("game_state.table must be a dict.")
        self._require_keys(table, ["street", "board_cards", "pot_total", "small_blind", "big_blind"], "game_state.table")

        if table["street"] not in {"preflop", "flop", "turn", "river", "showdown", "finished"}:
            raise ValueError("game_state.table.street must be a valid street name.")
        if not isinstance(table["pot_total"], (int, float)):
            raise ValueError("game_state.table.pot_total must be numeric.")
        if not isinstance(table["board_cards"], list) or len(table["board_cards"]) > 5:
            raise ValueError("game_state.table.board_cards must be a list of up to 5 cards.")

        players = game_state["players"]
        if not isinstance(players, list) or len(players) == 0:
            raise ValueError("game_state.players must be a non-empty list.")
        hero_id = game_state["hero_player_id"]
        hero_records = [p for p in players if p.get("player_id") == hero_id or p.get("is_hero")]
        if not hero_records:
            raise ValueError("game_state.players must contain at least one hero entry (is_hero=True or matching hero_player_id).")
        hero = hero_records[0]
        if not isinstance(hero.get("hole_cards"), list) or len(hero["hole_cards"]) != 2:
            raise ValueError("Hero player must have exactly 2 hole_cards.")

        action_history = game_state["action_history"]
        if not isinstance(action_history, dict):
            raise ValueError("game_state.action_history must be a dict keyed by street.")
        for street, actions in action_history.items():
            if not isinstance(actions, list):
                raise ValueError(f"game_state.action_history['{street}'] must be a list.")
            for idx, action in enumerate(actions):
                if not isinstance(action, dict):
                    raise ValueError(f"game_state.action_history['{street}'][{idx}] must be a dict.")
                self._require_keys(action, ["player_id", "action", "street"], f"game_state.action_history['{street}'][{idx}]")
                if "amount" in action and action["amount"] is not None and not isinstance(action["amount"], (int, float)):
                    raise ValueError(f"game_state.action_history['{street}'][{idx}].amount must be numeric.")

    def _validate_state_legacy_schema(self, game_state: Dict[str, Any]) -> None:
        """Validate the flat mock/test GameState schema used in dev and unit tests."""

        self._require_keys(
            game_state,
            ["format", "blinds", "street", "hero", "villains", "board_cards",
             "pot_size", "effective_stack", "action_history"],
            "game_state",
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
        if not isinstance(hero["hole_cards"], list) or len(hero["hole_cards"]) != 2:
            raise ValueError("game_state.hero.hole_cards must be a 2-item list.")

        board_cards = game_state["board_cards"]
        if not isinstance(board_cards, list) or len(board_cards) > 5:
            raise ValueError("game_state.board_cards must be a list of up to 5 cards.")

        action_history = game_state["action_history"]
        if isinstance(action_history, list):
            for idx, action in enumerate(action_history):
                if not isinstance(action, dict):
                    raise ValueError(f"game_state.action_history[{idx}] must be a dict.")
                self._require_keys(action, ["street", "actor", "action"], f"game_state.action_history[{idx}]")
        elif isinstance(action_history, dict):
            pass  # Also accept dict-by-street in legacy mode
        else:
            raise ValueError("game_state.action_history must be a list or dict.")

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
