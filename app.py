from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from engine.game_manager import GameManager
from frontend.poker_ui import render_action_panel, render_poker_table
from llm.llm_critic import LLMCritic
from solver.gto_solver_stub import GTOSolverStub


INIT = "INIT"
ENGINE_STEP = "ENGINE_STEP"
WAITING_FOR_USER = "WAITING_FOR_USER"
PROCESSING_CRITIQUE = "PROCESSING_CRITIQUE"


def _init_session_objects() -> None:
    if "game_manager" not in st.session_state:
        st.session_state.game_manager = GameManager()
    if "llm_critic" not in st.session_state:
        st.session_state.llm_critic = LLMCritic()
    if "gto_solver" not in st.session_state:
        st.session_state.gto_solver = GTOSolverStub(host="127.0.0.1", port=55143, enabled=False)

    if "app_state" not in st.session_state:
        st.session_state.app_state = INIT
    if "game_state" not in st.session_state:
        st.session_state.game_state = None
    if "current_game_state" not in st.session_state:
        st.session_state.current_game_state = None
    if "pending_action" not in st.session_state:
        st.session_state.pending_action = None
    if "is_waiting_for_ai" not in st.session_state:
        st.session_state.is_waiting_for_ai = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []


def _engine_start_new_hand(game_manager: GameManager) -> Dict[str, Any]:
    if hasattr(game_manager, "start_new_hand"):
        return game_manager.start_new_hand()
    return game_manager.get_public_state()


def _engine_step_bots_until_hero(game_manager: GameManager) -> Dict[str, Any]:
    if hasattr(game_manager, "step_bots_until_hero"):
        return game_manager.step_bots_until_hero()
    return game_manager.get_public_state()


def _engine_get_state(game_manager: GameManager) -> Dict[str, Any]:
    if hasattr(game_manager, "get_state"):
        return game_manager.get_state()
    return game_manager.get_public_state()


def _engine_is_hand_over(game_manager: GameManager) -> bool:
    if hasattr(game_manager, "is_hand_over"):
        return bool(game_manager.is_hand_over())
    return False


def _is_hero_turn(game_state: Dict[str, Any]) -> bool:
    action_on = game_state.get("action_on_player_id")
    hero_id = game_state.get("hero_player_id")

    if action_on is None and isinstance(game_state.get("table"), dict):
        action_on = game_state["table"].get("action_on_player_id")

    if hero_id is None and isinstance(game_state.get("table"), dict):
        hero_id = game_state["table"].get("hero_player_id")

    if action_on is not None and hero_id is not None:
        return action_on == hero_id

    # Fallback for placeholder engines where turn ownership is not exposed.
    return True


def _run_processing_critique(
    game_manager: GameManager,
    llm_critic: LLMCritic,
    gto_solver: GTOSolverStub,
) -> None:
    game_state = _engine_get_state(game_manager)
    user_action = st.session_state.pending_action

    if user_action is None:
        st.session_state.app_state = WAITING_FOR_USER
        st.rerun()

    solver_context = gto_solver.analyze(game_state)

    if hasattr(llm_critic, "generate_critique"):
        critique = llm_critic.generate_critique(
            game_state=game_state,
            user_action=user_action,
            solver_context=solver_context,
        )
    else:
        critique = {"summary": "LLM critic unavailable."}

    if hasattr(game_manager, "record_player_action"):
        game_manager.record_player_action(user_action)

    st.session_state.chat_history.append(
        {
            "role": "user",
            "content": (
                f"Action={user_action['action']} amount={user_action['amount']} "
                f"reasoning={user_action['reasoning']}"
            ),
        }
    )
    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": critique.get("summary", "No critique summary returned."),
        }
    )

    st.session_state.pending_action = None
    st.session_state.is_waiting_for_ai = False
    st.session_state.app_state = ENGINE_STEP
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Poker Master", page_icon="♠", layout="wide")
    st.title("Poker Master - Streamlit Orchestrator")

    _init_session_objects()
    game_manager: GameManager = st.session_state.game_manager
    llm_critic: LLMCritic = st.session_state.llm_critic
    gto_solver: GTOSolverStub = st.session_state.gto_solver

    state = st.session_state.app_state

    if state == INIT:
        st.session_state.game_state = _engine_start_new_hand(game_manager)
        st.session_state.app_state = ENGINE_STEP
        st.rerun()

    if state == ENGINE_STEP:
        stepped_state = _engine_step_bots_until_hero(game_manager)
        st.session_state.game_state = stepped_state

        if _engine_is_hand_over(game_manager):
            st.success("Hand complete. Initializing next hand.")
            st.session_state.app_state = INIT
            st.rerun()

        if _is_hero_turn(stepped_state):
            st.session_state.app_state = WAITING_FOR_USER
            st.rerun()

        st.info("Engine processed bot actions. Waiting for next rerun.")

    if state == WAITING_FOR_USER:
        game_state = st.session_state.game_state or _engine_get_state(game_manager)
        st.session_state.current_game_state = game_state

        left, right = st.columns([1.7, 1], gap="large")
        with left:
            render_poker_table()
        with right:
            render_action_panel()

        if st.session_state.pending_action is not None:
            st.session_state.app_state = PROCESSING_CRITIQUE
            st.rerun()

    if state == PROCESSING_CRITIQUE:
        _run_processing_critique(game_manager, llm_critic, gto_solver)


if __name__ == "__main__":
    main()
