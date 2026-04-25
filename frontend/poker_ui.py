from __future__ import annotations

from typing import Any, Dict


class PokerUI:
    """Agent 2 contract placeholder.

    Swap this class with the real Streamlit/Gradio adapter. Methods are kept
    small and explicit so the orchestrator can stay stable.
    """

    def render_state(self, game_state: Dict[str, Any]) -> None:
        print(f"[UI] Hand {game_state['hand_id']} | Street: {game_state['street']}")

    def capture_user_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        street = game_state["street"]
        return {
            "action": "check" if street != "preflop" else "call",
            "amount": 0,
            "reasoning": "Mock reasoning from UI input fields.",
        }

    def show_critique(self, critique: Dict[str, Any]) -> None:
        print(f"[LLM] {critique['summary']}")

    def show_solver_note(self, solver_result: Dict[str, Any]) -> None:
        print(f"[Solver] {solver_result['message']}")

    def show_transition(self, next_state: Dict[str, Any]) -> None:
        print(f"[Engine] Advanced to: {next_state['street']}")
