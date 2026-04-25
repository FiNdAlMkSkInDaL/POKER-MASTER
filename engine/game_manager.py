from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import random

from pypokerengine.api.emulator import Emulator
from pypokerengine.players import BasePokerPlayer


STREETS = ("preflop", "flop", "turn", "river")
FORCED_NATIVE_ACTIONS = {"SMALLBLIND", "BIGBLIND", "ANTE"}
NATIVE_TO_CUSTOM_ACTION = {
    "SMALLBLIND": "small_blind",
    "BIGBLIND": "big_blind",
    "ANTE": "ante",
    "FOLD": "fold",
    "CALL": "call",
    "CHECK": "check",
    "RAISE": "raise",
    "BET": "bet",
    "ALLIN": "all_in",
}

LOGGER = logging.getLogger(__name__)


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class PlayerConfig:
    player_id: str
    name: str
    seat: int
    stack: int
    is_hero: bool = False


class ManualHeroPlayer(BasePokerPlayer):
    """Registered for seat ownership, but actions are injected via GameManager.apply_action."""

    def declare_action(self, valid_actions, hole_card, round_state):
        raise RuntimeError("Hero action must be provided through GameManager.apply_action.")

    def receive_game_start_message(self, game_info):
        return None

    def receive_round_start_message(self, round_count, hole_card, seats):
        return None

    def receive_street_start_message(self, street, round_state):
        return None

    def receive_game_update_message(self, action, round_state):
        return None

    def receive_round_result_message(self, winners, hand_info, round_state):
        return None


class RandomHeuristicBot(BasePokerPlayer):
    """Baseline bot with lightweight weighting for smoother hand progression."""

    def declare_action(self, valid_actions, hole_card, round_state):
        weighted_actions: List[Dict[str, Any]] = []
        for action in valid_actions:
            name = action["action"]
            if name == "call":
                weighted_actions.extend([action] * 5)
            elif name == "raise":
                weighted_actions.extend([action] * 2)
            else:
                weighted_actions.append(action)

        choice = random.choice(weighted_actions)
        action_name = choice["action"]
        if action_name == "raise":
            amount_range = choice.get("amount", {})
            min_amount = int(amount_range.get("min", 0))
            max_amount = int(amount_range.get("max", min_amount))
            raise_to = min_amount if max_amount <= min_amount else random.randint(min_amount, max_amount)
            return "raise", raise_to
        return action_name, int(choice.get("amount", 0))

    def receive_game_start_message(self, game_info):
        return None

    def receive_round_start_message(self, round_count, hole_card, seats):
        return None

    def receive_street_start_message(self, street, round_state):
        return None

    def receive_game_update_message(self, action, round_state):
        return None

    def receive_round_result_message(self, winners, hand_info, round_state):
        return None


class GameManager:
    """Deterministic, headless NLHE manager backed by PyPokerEngine Emulator."""

    SCHEMA_VERSION = "1.0.0"

    def __init__(
        self,
        hero_name: str = "Hero",
        bot_count: int = 5,
        initial_stack: int = 200,
        small_blind: int = 1,
        big_blind: int = 2,
    ) -> None:
        if bot_count != 5:
            raise ValueError("This GameManager currently targets 6-max (1 hero + 5 bots).")

        self.max_players = 6
        self.initial_stack = initial_stack
        self.small_blind = small_blind
        self.big_blind = big_blind

        self.hand_id = 0
        self.round_index = 0
        self.hero_player_id = "p0"
        self._dealer_seat = 0  # Track and rotate dealer button position

        self.players: List[PlayerConfig] = [
            PlayerConfig(player_id="p0", name=hero_name, seat=0, stack=initial_stack, is_hero=True)
        ]
        for i in range(1, self.max_players):
            self.players.append(PlayerConfig(player_id=f"p{i}", name=f"Bot {i}", seat=i, stack=initial_stack))
        self._player_lookup: Dict[str, PlayerConfig] = {p.player_id: p for p in self.players}

        self._bots: Dict[str, RandomHeuristicBot] = {
            p.player_id: RandomHeuristicBot() for p in self.players if not p.is_hero
        }

        self._emulator = Emulator()
        self._emulator.set_game_rule(
            player_num=self.max_players,
            max_round=10_000,
            small_blind_amount=self.small_blind,
            ante_amount=0,
        )
        self._emulator.register_player(self.hero_player_id, ManualHeroPlayer())
        for player_id, bot in self._bots.items():
            self._emulator.register_player(player_id, bot)

        self._native_game_state: Optional[Dict[str, Any]] = None
        self._native_round_state: Dict[str, Any] = {}
        self._native_valid_actions: List[Dict[str, Any]] = []
        self._hero_hole_cards: List[str] = []
        self._custom_action_history: Dict[str, List[Dict[str, Any]]] = {
            "preflop": [],
            "flop": [],
            "turn": [],
            "river": [],
        }
        self._hand_history: List[Dict[str, Any]] = []
        self._live_contribution_street = "preflop"
        self._live_contribution_by_player: Dict[str, float] = {
            p.player_id: 0.0 for p in self.players
        }
        self._native_action_counts: Dict[str, int] = {street: 0 for street in STREETS}
        self._next_action_sequence = 1
        self._hand_complete = False

        self._state: Dict[str, Any] = {}
        self.start_new_hand()

    def start_new_hand(self) -> Dict[str, Any]:
        """Deal a fresh hand and return translated GameState."""
        if self.hand_id > 0:
            self.rotate_dealer()

        self.hand_id += 1
        self.round_index += 1
        self._hand_complete = False
        self._custom_action_history = {"preflop": [], "flop": [], "turn": [], "river": []}
        self._hand_history = []
        self._live_contribution_street = "preflop"
        self._live_contribution_by_player = {p.player_id: 0.0 for p in self.players}
        self._native_action_counts = {street: 0 for street in STREETS}
        self._next_action_sequence = 1

        players_info = {
            p.player_id: {"name": p.name, "stack": p.stack}
            for p in self.players
        }
        initial_state = self._emulator.generate_initial_game_state(players_info)
        table = initial_state.get("table")
        if table is not None:
            # Keep hero physically at seat 0 while rotating strategic positions by dealer seat.
            table.dealer_btn = self._dealer_seat
            sb_pos = (self._dealer_seat + 1) % self.max_players
            bb_pos = (self._dealer_seat + 2) % self.max_players
            table.set_blind_pos(sb_pos, bb_pos)

        self._native_game_state, events = self._emulator.start_new_round(initial_state)
        self._hero_hole_cards = self._extract_hole_cards(self.hero_player_id)
        self._consume_events(events)
        self._state = self._build_game_state()
        return self._snapshot_state()

    def rotate_dealer(self) -> int:
        """Advance dealer button clockwise by one seat and return the new seat index.

        Seat indices in this engine's table layout increase opposite to clockwise
        table movement, so clockwise rotation is represented by decrementing the
        seat index modulo player count.
        """
        self._dealer_seat = (self._dealer_seat - 1) % self.max_players
        return self._dealer_seat

    def get_state(self) -> Dict[str, Any]:
        return self._snapshot_state()

    def get_legal_actions(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        acting_player = self._get_acting_player_id()
        if player_id is not None and player_id != acting_player:
            return []
        return self._translate_legal_actions(self._native_valid_actions)

    def get_public_state(self) -> Dict[str, Any]:
        return self.get_state()

    def apply_action(
        self,
        player_id: str,
        action_type: str,
        amount: int = 0,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        if self._hand_complete:
            raise ValueError("Cannot apply action: hand is already complete.")

        acting_player = self._get_acting_player_id()
        if player_id != acting_player:
            raise ValueError(f"Not {player_id}'s turn. Current actor is {acting_player}.")

        engine_action, engine_amount = self._normalize_action_for_engine(action_type, amount)
        self._apply_native_action(player_id, engine_action, engine_amount, reasoning)
        return self._snapshot_state()

    def record_player_action(self, action_payload: Dict[str, Any]) -> None:
        player_id = action_payload.get("player_id", self.hero_player_id)
        action = action_payload.get("action") or action_payload.get("action_type")
        if not action:
            raise ValueError("Action payload requires 'action' or 'action_type'.")
        amount = int(action_payload.get("amount", 0))
        reasoning = str(action_payload.get("reasoning", ""))
        self.apply_action(player_id=player_id, action_type=action, amount=amount, reasoning=reasoning)

    def step_one_bot_action(self) -> Dict[str, Any]:
        """Process exactly one bot action and return the updated state.

        Designed for the orchestrator's tick system: call this once per rerun
        so each bot action is visible in the UI before the next one fires.
        Returns the current state unchanged if it is already the hero's turn
        or the hand is complete.
        """
        return self.step_single_bot()

    def step_bots_until_hero(self) -> Dict[str, Any]:
        """Advance emulator by auto-playing bots until hero acts or hand completes."""
        while not self._hand_complete:
            acting_player = self._get_acting_player_id()
            if acting_player == self.hero_player_id:
                break

            bot = self._bots.get(acting_player)
            if bot is None:
                break

            hole_cards = self._extract_hole_cards(acting_player)
            action, amount = bot.declare_action(
                self._native_valid_actions,
                hole_cards,
                self._native_round_state,
            )
            self._apply_native_action(acting_player, action, int(amount), "")
        return self._snapshot_state()

    def step_single_bot(self) -> Dict[str, Any]:
        """Advance emulator by exactly one bot action and return the updated state.

        Returns the current state unchanged if the hand is over or it is already
        the hero's turn.
        """
        if self._hand_complete:
            return self._snapshot_state()

        acting_player = self._get_acting_player_id()
        if acting_player == self.hero_player_id:
            return self._snapshot_state()

        bot = self._bots.get(acting_player)
        if bot is None:
            return self._snapshot_state()

        hole_cards = self._extract_hole_cards(acting_player)
        action, amount = bot.declare_action(
            self._native_valid_actions,
            hole_cards,
            self._native_round_state,
        )
        self._apply_native_action(acting_player, action, int(amount), "")
        return self._snapshot_state()

    def advance_to_next_state(self) -> Dict[str, Any]:
        return self.step_bots_until_hero()

    def is_hand_over(self) -> bool:
        return self._hand_complete

    def _apply_native_action(
        self,
        player_id: str,
        action: str,
        amount: int,
        reasoning: str,
    ) -> None:
        if self._native_game_state is None:
            raise RuntimeError("Native game state is not initialized.")

        acting_player = self._get_acting_player_id()
        if player_id != acting_player:
            raise ValueError(f"Not {player_id}'s turn. Current actor is {acting_player}.")

        self._native_game_state, events = self._emulator.apply_action(
            self._native_game_state,
            action,
            amount,
        )
        self._consume_events(events, hero_reasoning=reasoning if player_id == self.hero_player_id else "")
        self._state = self._build_game_state()

    def _consume_events(self, events: List[Dict[str, Any]], hero_reasoning: str = "") -> None:
        pending_reasoning = hero_reasoning
        for event in events:
            event_type = event.get("type", "")
            if event_type == "event_ask_player":
                self._native_round_state = event["round_state"]
                self._native_valid_actions = event.get("valid_actions", [])
                pending_reasoning = self._sync_action_history(self._native_round_state, pending_reasoning)
            elif "round_state" in event:
                self._native_round_state = event["round_state"]
                pending_reasoning = self._sync_action_history(self._native_round_state, pending_reasoning)
            if event_type in {"event_round_finish", "event_game_finish"}:
                self._hand_complete = True
                self._native_valid_actions = []

        if self._native_round_state:
            self._sync_action_history(self._native_round_state, pending_reasoning)

    def _sync_action_history(self, round_state: Dict[str, Any], hero_reasoning: str) -> str:
        action_histories = round_state.get("action_histories", {})
        dealer_seat = int(round_state.get("dealer_btn", 0))
        seat_by_player_id: Dict[str, int] = {
            seat.get("uuid", ""): idx for idx, seat in enumerate(round_state.get("seats", []))
        }
        name_by_player_id: Dict[str, str] = {
            seat.get("uuid", ""): str(seat.get("name", seat.get("uuid", "")))
            for seat in round_state.get("seats", [])
        }

        for street in STREETS:
            native_items = action_histories.get(street, [])
            seen_count = self._native_action_counts.get(street, 0)
            if len(native_items) <= seen_count:
                continue

            for native_action in native_items[seen_count:]:
                player_id = native_action.get("uuid", "")
                native_name = str(native_action.get("action", "")).upper()
                custom_action = NATIVE_TO_CUSTOM_ACTION.get(native_name, native_name.lower())
                amount = int(native_action.get("amount", 0))
                is_forced = native_name in FORCED_NATIVE_ACTIONS
                reasoning = ""
                if player_id == self.hero_player_id and not is_forced and hero_reasoning:
                    reasoning = hero_reasoning
                    hero_reasoning = ""

                custom_entry = {
                    "sequence": self._next_action_sequence,
                    "street": street,
                    "player_id": player_id,
                    "action": custom_action,
                    "amount": amount,
                    "is_forced": is_forced,
                    "reasoning": reasoning,
                }
                self._custom_action_history[street].append(custom_entry)

                if self._live_contribution_street != street:
                    self._live_contribution_street = street
                    self._live_contribution_by_player = {p.player_id: 0.0 for p in self.players}
                add_amount = float(native_action.get("add_amount", 0.0))
                self._live_contribution_by_player[player_id] = self._live_contribution_by_player.get(player_id, 0.0) + add_amount

                seat_index = seat_by_player_id.get(player_id, self._player_lookup.get(player_id, PlayerConfig(player_id=player_id, name=player_id, seat=0, stack=0)).seat)
                position = self._seat_to_position(seat_index, dealer_seat)
                player_name = name_by_player_id.get(player_id, self._player_lookup.get(player_id, PlayerConfig(player_id=player_id, name=player_id, seat=0, stack=0)).name)
                self._hand_history.append(
                    {
                        "street": street,
                        "position": position,
                        "player_name": player_name,
                        "action": custom_action,
                        "amount": float(amount),
                        "description": self._format_action_description(custom_entry),
                    }
                )
                self._next_action_sequence += 1

            self._native_action_counts[street] = len(native_items)

        return hero_reasoning

    def _build_game_state(self) -> Dict[str, Any]:
        if not self._native_round_state:
            raise RuntimeError("Cannot build GameState without native round_state.")

        round_state = self._native_round_state
        seats = round_state.get("seats", [])
        board_cards = [self._normalize_card(card) for card in round_state.get("community_card", [])]

        street = str(round_state.get("street", "preflop")).lower()
        if street == "finished":
            street = "river"

        translated_legal_actions = self._translate_legal_actions(self._native_valid_actions)
        current_bet_to_call, min_raise_to = self._extract_betting_targets(translated_legal_actions)
        acting_player_id = self._get_acting_player_id(default="")

        contributions_street, contributions_hand = self._compute_contributions(round_state)
        live_contributions = self._compute_live_contributions(round_state, contributions_street)

        players_payload: List[Dict[str, Any]] = []
        dealer_seat = int(round_state.get("dealer_btn", 0))
        for seat_index, seat in enumerate(seats):
            player_id = seat.get("uuid", "")
            state = str(seat.get("state", "")).lower()
            players_payload.append(
                {
                    "player_id": player_id,
                    "name": seat.get("name", player_id),
                    "seat": seat_index,
                    "position": self._seat_to_position(seat_index, dealer_seat),
                    "stack": int(seat.get("stack", 0)),
                    "is_active": state in {"participating", "allin"},
                    "is_all_in": state == "allin",
                    "has_folded": state == "folded",
                    "contribution_this_street": float(live_contributions.get(player_id, 0.0)),
                    "contribution_this_hand": float(contributions_hand.get(player_id, 0)),
                    "hole_cards": self._hero_hole_cards if player_id == self.hero_player_id else [],
                    "is_hero": player_id == self.hero_player_id,
                }
            )

        hand_status = "complete" if self._hand_complete else ("showdown" if street == "showdown" else "in_progress")
        pot_total = int(round_state.get("pot", {}).get("main", {}).get("amount", 0))
        for side_pot in round_state.get("pot", {}).get("side", []):
            pot_total += int(side_pot.get("amount", 0))

        last_action = self._get_last_action()
        last_action_description = self._format_action_description(last_action)

        game_state = {
            "schema_version": self.SCHEMA_VERSION,
            "game_type": "NLHE",
            "hand_id": self.hand_id,
            "round_index": int(round_state.get("round_count", self.round_index)),
            "hand_status": hand_status,
            "last_action_description": last_action_description,
            "hero_player_id": self.hero_player_id,
            "table": {
                "max_players": self.max_players,
                "small_blind": int(round_state.get("small_blind_amount", self.small_blind)),
                "big_blind": int(round_state.get("small_blind_amount", self.small_blind)) * 2,
                "dealer_seat": dealer_seat,
                "street": street,
                "board_cards": board_cards,
                "pot_total": pot_total,
                "current_bet_to_call": current_bet_to_call,
                "min_raise_to": min_raise_to,
                "action_on_player_id": acting_player_id,
                "last_action": last_action if last_action is not None else {},
                "last_action_description": last_action_description,
            },
            "players": players_payload,
            "legal_actions": translated_legal_actions,
            "action_history": deepcopy(self._custom_action_history),
            "hand_history": deepcopy(self._hand_history),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        return self._ensure_render_ready_state(game_state)

    def _snapshot_state(self) -> Dict[str, Any]:
        """Return a deep-copied state that is guaranteed render-ready for UI ticks."""
        if not self._state and self._native_round_state:
            self._state = self._build_game_state()
        return deepcopy(self._ensure_render_ready_state(self._state))

    def _ensure_render_ready_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Guarantee schema shape for every tick, including mid-round transitions."""
        if state is None:
            state = {}

        round_index = int(self._native_round_state.get("round_count", self.round_index)) if self._native_round_state else self.round_index
        state.setdefault("schema_version", self.SCHEMA_VERSION)
        state.setdefault("game_type", "NLHE")
        state.setdefault("hand_id", self.hand_id)
        state.setdefault("round_index", round_index)
        state.setdefault("hand_status", "complete" if self._hand_complete else "in_progress")
        state.setdefault("hero_player_id", self.hero_player_id)
        state.setdefault("legal_actions", [])
        state.setdefault("action_history", deepcopy(self._custom_action_history))
        state.setdefault("hand_history", deepcopy(self._hand_history))
        if not isinstance(state.get("hand_history"), list):
            state["hand_history"] = deepcopy(self._hand_history)
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()

        table = state.get("table")
        if not isinstance(table, dict):
            table = {}
            state["table"] = table

        default_big_blind = self.big_blind
        if self._native_round_state:
            default_big_blind = int(self._native_round_state.get("small_blind_amount", self.small_blind)) * 2

        table.setdefault("max_players", self.max_players)
        table.setdefault("small_blind", self.small_blind)
        table.setdefault("big_blind", default_big_blind)
        table.setdefault("dealer_seat", int(self._native_round_state.get("dealer_btn", 0)) if self._native_round_state else 0)
        table.setdefault("street", str(self._native_round_state.get("street", "preflop")).lower() if self._native_round_state else "preflop")
        table.setdefault("board_cards", [])
        table.setdefault("pot_total", 0)
        table.setdefault("current_bet_to_call", 0)
        table.setdefault("min_raise_to", 0)
        table.setdefault("action_on_player_id", self._get_acting_player_id(default=""))
        table.setdefault("last_action", {})

        last_action = table.get("last_action")
        if not state.get("last_action_description"):
            state["last_action_description"] = self._format_action_description(last_action if isinstance(last_action, dict) else None)
        table["last_action_description"] = state.get("last_action_description", "")

        players_payload = state.get("players")
        if not isinstance(players_payload, list):
            players_payload = []
            state["players"] = players_payload

        players_by_id: Dict[str, Dict[str, Any]] = {
            p.get("player_id", ""): p for p in players_payload if isinstance(p, dict) and p.get("player_id")
        }
        for cfg in self.players:
            payload = players_by_id.get(cfg.player_id)
            if payload is None:
                payload = {
                    "player_id": cfg.player_id,
                    "name": cfg.name,
                    "seat": cfg.seat,
                    "position": self._seat_to_position(cfg.seat, int(table.get("dealer_seat", 0))),
                    "stack": cfg.stack,
                    "is_active": True,
                    "is_all_in": False,
                    "has_folded": False,
                    "contribution_this_street": 0,
                    "contribution_this_hand": 0,
                    "hole_cards": [],
                    "is_hero": cfg.is_hero,
                }
                players_payload.append(payload)

            payload.setdefault("name", cfg.name)
            payload.setdefault("seat", cfg.seat)
            payload.setdefault("position", self._seat_to_position(int(payload.get("seat", cfg.seat)), int(table.get("dealer_seat", 0))))
            payload.setdefault("stack", 0)
            payload.setdefault("is_active", True)
            payload.setdefault("is_all_in", False)
            payload.setdefault("has_folded", False)
            payload.setdefault("contribution_this_street", 0)
            payload.setdefault("contribution_this_hand", 0)
            payload.setdefault("hole_cards", [] if not cfg.is_hero else self._hero_hole_cards)
            payload["is_hero"] = cfg.is_hero

        if self._native_round_state:
            contributions_street, contributions_hand = self._compute_contributions(self._native_round_state)
            live_contributions = self._compute_live_contributions(self._native_round_state, contributions_street)
            for payload in players_payload:
                if not isinstance(payload, dict):
                    continue
                player_id = payload.get("player_id", "")
                payload["contribution_this_street"] = float(live_contributions.get(player_id, 0.0))
                payload["contribution_this_hand"] = float(contributions_hand.get(player_id, payload.get("contribution_this_hand", 0)))

        return state

    def _extract_betting_targets(self, legal_actions: List[Dict[str, Any]]) -> Tuple[int, int]:
        to_call = 0
        min_raise = 0
        for action in legal_actions:
            if action["action"] == "call":
                to_call = int(action.get("amount", 0))
            elif action["action"] == "raise":
                min_raise = int(action.get("min", 0))
        return to_call, min_raise

    def _normalize_action_for_engine(self, action_type: str, amount: int) -> Tuple[str, int]:
        normalized_action = str(action_type).strip().lower()
        try:
            requested = ActionType(normalized_action).value
        except ValueError:
            LOGGER.error(
                "Invalid action_type '%s' (normalized='%s'). Falling back to a legal action.",
                action_type,
                normalized_action,
            )
            if self._find_valid_action("fold") is not None:
                requested = ActionType.FOLD.value
            elif self._find_valid_action("call") is not None:
                call_action = self._find_valid_action("call")
                requested = ActionType.CHECK.value if int(call_action.get("amount", 0)) == 0 else ActionType.CALL.value
            elif self._find_valid_action("raise") is not None:
                requested = ActionType.RAISE.value
            else:
                LOGGER.error("No legal fallback action available from current valid actions.")
                raise ValueError(f"Unknown action '{action_type}' and no legal fallback action available.")

        requested_native = {
            "fold": "fold",
            "call": "call",
            "check": "call",
            "raise": "raise",
            "bet": "raise",
            "all_in": "raise",
        }[requested]

        valid = self._find_valid_action(requested_native)
        if valid is None:
            if requested == "check":
                valid = self._find_valid_action("call")
                if valid and int(valid.get("amount", 0)) == 0:
                    return "call", 0
            raise ValueError(f"Action {requested} is not legal in current state.")

        if requested_native == "raise":
            amount_info = valid.get("amount", {})
            min_amount = int(amount_info.get("min", 0))
            max_amount = int(amount_info.get("max", min_amount))
            if requested == "all_in":
                return "raise", max_amount
            chosen = amount if amount > 0 else min_amount
            return "raise", max(min_amount, min(max_amount, chosen))

        return requested_native, int(valid.get("amount", 0))

    def _find_valid_action(self, action_name: str) -> Optional[Dict[str, Any]]:
        for valid in self._native_valid_actions:
            if valid.get("action") == action_name:
                return valid
        return None

    def _translate_legal_actions(self, native_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        translated: List[Dict[str, Any]] = []
        for native in native_actions:
            action = native.get("action", "")
            amount = native.get("amount", 0)
            if action == "raise" and isinstance(amount, dict):
                translated.append(
                    {
                        "action": "raise",
                        "min": int(amount.get("min", 0)),
                        "max": int(amount.get("max", 0)),
                    }
                )
            elif action == "call" and int(amount) == 0:
                translated.append({"action": "check", "amount": 0})
            else:
                payload = {"action": action}
                if action in {"call", "bet", "all_in"}:
                    payload["amount"] = int(amount)
                translated.append(payload)
        return translated

    def _compute_contributions(self, round_state: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
        by_street: Dict[str, int] = {}
        by_hand: Dict[str, int] = {}
        street = str(round_state.get("street", "preflop")).lower()

        for hist_street in STREETS:
            for action in round_state.get("action_histories", {}).get(hist_street, []):
                player_id = action.get("uuid", "")
                add_amount = int(action.get("add_amount", 0))
                by_hand[player_id] = by_hand.get(player_id, 0) + add_amount
                if hist_street == street:
                    by_street[player_id] = by_street.get(player_id, 0) + add_amount
        return by_street, by_hand

    def _compute_live_contributions(
        self,
        round_state: Dict[str, Any],
        fallback_contributions: Dict[str, int],
    ) -> Dict[str, float]:
        """Return per-player chips currently shown in front of each seat.

        Uses the latest action-tracked street contributions for per-tick UI updates.
        Falls back to round_state-derived street totals when no tracked data exists.
        """
        if self._live_contribution_by_player:
            return {
                player_id: float(self._live_contribution_by_player.get(player_id, 0.0))
                for player_id in [seat.get("uuid", "") for seat in round_state.get("seats", [])]
            }
        return {player_id: float(amount) for player_id, amount in fallback_contributions.items()}

    def _get_acting_player_id(self, default: str = "") -> str:
        seats = self._native_round_state.get("seats", [])
        if not seats:
            return default
        next_idx = int(self._native_round_state.get("next_player", -1))
        if next_idx < 0 or next_idx >= len(seats):
            return default
        return seats[next_idx].get("uuid", default)

    def _get_last_action(self) -> Optional[Dict[str, Any]]:
        last: Optional[Dict[str, Any]] = None
        for street in STREETS:
            if self._custom_action_history[street]:
                last = self._custom_action_history[street][-1]
        return deepcopy(last)

    def _format_action_description(self, action_entry: Optional[Dict[str, Any]]) -> str:
        """Return a human-readable summary string, e.g. 'Bot 2 raises to $12'."""
        if action_entry is None:
            return ""
        player_id = action_entry.get("player_id", "")
        player_cfg = self._player_lookup.get(player_id)
        name = player_cfg.name if player_cfg else player_id
        action = action_entry.get("action", "")
        amount = int(action_entry.get("amount", 0))

        if action == "fold":
            return f"{name} folds"
        if action == "check" or (action == "call" and amount == 0):
            return f"{name} checks"
        if action == "call":
            return f"{name} calls ${amount}"
        if action in ("raise", "bet"):
            return f"{name} raises to ${amount}"
        if action == "all_in":
            return f"{name} goes all-in (${amount})"
        if action == "small_blind":
            return f"{name} posts small blind ${amount}"
        if action == "big_blind":
            return f"{name} posts big blind ${amount}"
        return f"{name} {action}" + (f" ${amount}" if amount else "")

    def _extract_hole_cards(self, player_id: str) -> List[str]:
        if self._native_game_state is None:
            return []

        table = self._native_game_state.get("table")
        if table is None or not hasattr(table, "seats"):
            return []

        for player in getattr(table.seats, "players", []):
            if getattr(player, "uuid", "") != player_id:
                continue
            return [self._normalize_card(str(card)) for card in getattr(player, "hole_card", [])]
        return []

    def _seat_to_position(self, seat_index: int, dealer_seat: int) -> str:
        # Relative labels in 6-max clockwise order from dealer button.
        labels = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
        relative_idx = (seat_index - dealer_seat) % self.max_players
        return labels[relative_idx]

    def _normalize_card(self, card: str) -> str:
        if len(card) < 2:
            return card
        suit = card[0].lower()
        rank = card[1:].upper()
        return f"{rank}{suit}"
