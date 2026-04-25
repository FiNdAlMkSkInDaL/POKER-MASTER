from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict

import streamlit as st

from engine.game_manager import GameManager
from frontend.poker_ui import render_action_panel, render_hand_history_sidebar, render_poker_table
from llm.llm_critic import LLMCritic
from solver.gto_solver_stub import GTOSolverStub


# ── App state constants ───────────────────────────────────────────────────────
WAITING_TO_START   = "WAITING_TO_START"   # lobby — awaits "Start Hand" click
INIT               = "INIT"               # deals cards, headless
ENGINE_STEP        = "ENGINE_STEP"        # one bot action per rerun (tick)
WAITING_FOR_USER   = "WAITING_FOR_USER"   # hero's turn — renders full UI
PROCESSING_CRITIQUE = "PROCESSING_CRITIQUE"  # LLM + GTO stub running


# ── Session initialisation ────────────────────────────────────────────────────

def _init_session_objects() -> None:
    if "game_manager" not in st.session_state:
        st.session_state.game_manager = GameManager()
    if "llm_critic" not in st.session_state:
        st.session_state.llm_critic = LLMCritic()
    if "gto_solver" not in st.session_state:
        st.session_state.gto_solver = GTOSolverStub(host="127.0.0.1", port=55143, enabled=False)

    # State machine
    if "app_state" not in st.session_state:
        st.session_state.app_state = WAITING_TO_START

    # game_state: raw engine dict; current_game_state: Agent 2's render key
    if "game_state" not in st.session_state:
        st.session_state.game_state = {}
    if "current_game_state" not in st.session_state:
        st.session_state.current_game_state = {}

    # Action pipeline
    if "pending_action" not in st.session_state:
        st.session_state.pending_action = None
    if "is_waiting_for_ai" not in st.session_state:
        st.session_state.is_waiting_for_ai = False

    # Chat logs — two keys: orchestrator log + Agent 2's render contract
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []

    # Dealer button position (persists across hands for UI display)
    if "dealer_seat" not in st.session_state:
        st.session_state.dealer_seat = 0

    # Hand action log — cleared at the start of each new hand
    if "hand_history" not in st.session_state:
        st.session_state.hand_history = []


# ── Engine wrappers ───────────────────────────────────────────────────────────

def _engine_start_new_hand(gm: GameManager) -> Dict[str, Any]:
    return gm.start_new_hand() if hasattr(gm, "start_new_hand") else gm.get_public_state()


def _engine_step_one_bot(gm: GameManager) -> Dict[str, Any]:
    """Tick: process exactly one bot action."""
    if hasattr(gm, "step_one_bot_action"):
        return gm.step_one_bot_action()
    # Fallback for stubs that only have the bulk version.
    return gm.get_public_state()


def _engine_get_state(gm: GameManager) -> Dict[str, Any]:
    return gm.get_state() if hasattr(gm, "get_state") else gm.get_public_state()


def _engine_is_hand_over(gm: GameManager) -> bool:
    return bool(gm.is_hand_over()) if hasattr(gm, "is_hand_over") else False


def _is_hero_turn(game_state: Dict[str, Any], hero_id: str) -> bool:
    action_on = game_state.get("action_on_player_id")
    if action_on is None and isinstance(game_state.get("table"), dict):
        action_on = game_state["table"].get("action_on_player_id")
    if action_on is not None:
        return action_on == hero_id
    return True  # safe fallback for placeholder engines


def _acting_player_name(game_state: Dict[str, Any]) -> str:
    """Return the display name of whichever player is currently acting."""
    table = game_state.get("table", {})
    acting_id = table.get("action_on_player_id", "")
    for p in game_state.get("players", []):
        if p.get("player_id") == acting_id:
            return p.get("name", acting_id)
    return acting_id or "Bot"


def _sync_hand_history(game_state: Dict[str, Any]) -> None:
    """Flatten action_history from game_state into st.session_state.hand_history."""
    action_history = game_state.get("action_history", {})
    flat: list = []
    for street in ("preflop", "flop", "turn", "river"):
        flat.extend(action_history.get(street, []))
    st.session_state.hand_history = flat


def _last_action_description(game_state: Dict[str, Any]) -> str:
    """One-line summary of the most recent action for the tick display."""
    table = game_state.get("table", {})
    desc = table.get("last_action_description")
    if desc:
        return desc
    last = table.get("last_action")
    if last:
        return f"{last.get('player_id', '?')} → {last.get('action', '?')} ${last.get('amount', 0)}"
    return ""


# ── Critique runner ───────────────────────────────────────────────────────────

def _run_processing_critique(
    gm: GameManager,
    llm_critic: LLMCritic,
    gto_solver: GTOSolverStub,
) -> None:
    # Hard state guard: this function must only run in PROCESSING_CRITIQUE.
    # A mid-rerun state transition (e.g. Streamlit double-fire) could call this
    # from an unexpected state; bail safely rather than issuing a stale critique.
    if st.session_state.app_state != PROCESSING_CRITIQUE:
        return

    game_state = _engine_get_state(gm)
    user_action = st.session_state.pending_action

    if user_action is None:
        # pending_action was cleared by a concurrent rerun — nothing to critique.
        st.session_state.app_state = WAITING_FOR_USER
        st.rerun()

    solver_context = gto_solver.analyze(game_state)

    if hasattr(llm_critic, "generate_critique"):
        summary = llm_critic.generate_critique(
            game_state=game_state,
            user_action=user_action,
            solver_context=solver_context,
        )
    else:
        summary = "LLM critic unavailable."

    if hasattr(gm, "record_player_action"):
        gm.record_player_action(user_action)
    timestamp = datetime.now().strftime("%H:%M:%S")

    st.session_state.chat_history.append(
        {"role": "user", "content": (
            f"Action={user_action['action']} amount={user_action['amount']} "
            f"reasoning={user_action['reasoning']}"
        )}
    )
    st.session_state.chat_history.append({"role": "assistant", "content": summary})
    # Mirror into Agent 2's chat key so the action panel can display it.
    st.session_state.ai_chat_history.append(
        {"role": "assistant", "content": summary, "timestamp": timestamp}
    )

    st.session_state.pending_action = None
    st.session_state.is_waiting_for_ai = False
    st.session_state.app_state = ENGINE_STEP
    st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Poker Master", page_icon="♠", layout="wide")

    # Seed all keys first — no-ops on every subsequent run.
    _init_session_objects()
    gm: GameManager       = st.session_state.game_manager
    llm_critic: LLMCritic = st.session_state.llm_critic
    gto_solver            = st.session_state.gto_solver

    # ── SIDEBAR: hand history (always rendered) ────────────────────────────────
    # Fetch fresh engine state first so the sidebar and table are always in sync.
    current_state = _engine_get_state(gm)
    st.session_state.current_game_state = current_state

    render_hand_history_sidebar()

    # ── PERSISTENT UI LAYER (always rendered before state logic) ──────────────
    st.title("Poker Master")
    
    # Two-column layout: table on left, action panel on right
    left, right = st.columns([1.7, 1], gap="large")
    
    with left:
        render_poker_table()
    
    with right:
        # Right panel adapts based on app state
        state = st.session_state.app_state
        
        if state == WAITING_TO_START:
            # Lobby: start a new hand or continue
            if current_state:
                st.subheader("Hand Complete")
                if st.button("▶ Start Next Hand", type="primary", use_container_width=True):
                    st.session_state.app_state = INIT
                    st.rerun()
            else:
                st.subheader("Welcome to Poker Master")
                st.write("Press **Start Hand** to begin coaching.")
                if st.button("▶ Start Hand", type="primary", use_container_width=True):
                    st.session_state.app_state = INIT
                    st.rerun()
        
        elif state == ENGINE_STEP and not _is_hero_turn(current_state, gm.hero_player_id):
            # Bot is acting: show thinking status
            actor = _acting_player_name(current_state)
            with st.status(f"⏳ {actor} is thinking…", expanded=True):
                st.write("Waiting for bot decision…")
        
        elif state == WAITING_FOR_USER:
            # Hero's turn: show decision controls
            render_action_panel()
        
        elif state == PROCESSING_CRITIQUE:
            # LLM analyzing: show spinner zone (UI frozen)
            render_action_panel()  # Frozen with disabled=True
    
    # ── STATE MACHINE: runs after UI is fully rendered ────────────────────────
    # Any st.rerun() calls here happen AFTER the user sees the UI above
    
    state = st.session_state.app_state
    
    if state == INIT:
        # Clear history ghost from the previous hand
        st.session_state.hand_history = []

        # Headless: rotate dealer button BEFORE dealing cards
        new_dealer_seat = gm.rotate_dealer()
        st.session_state.dealer_seat = new_dealer_seat
        
        # Now deal the new hand
        new_hand = _engine_start_new_hand(gm)
        st.session_state.game_state = new_hand
        st.session_state.current_game_state = new_hand
        st.session_state.app_state = ENGINE_STEP
        st.rerun()
    
    if state == ENGINE_STEP:
        # Headless: check terminal conditions, advance one bot tick
        if _engine_is_hand_over(gm):
            # Hand finished → return to lobby
            st.session_state.game_state = current_state
            st.session_state.app_state = WAITING_TO_START
            st.rerun()
        
        if _is_hero_turn(current_state, gm.hero_player_id):
            # Hero's turn → switch to WAITING_FOR_USER
            st.session_state.game_state = current_state
            st.session_state.app_state = WAITING_FOR_USER
            st.rerun()
        
        # ── BOT TICK: one action per rerun cycle ────────────────────────────
        # UI has already rendered (status message in right column)
        # Now advance the bot and re-query engine for the authoritative
        # post-action state (including fresh contribution_this_street values).
        time.sleep(0.7)
        
        _engine_step_one_bot(gm)
        stepped = _engine_get_state(gm)  # authoritative post-action state
        st.session_state.game_state = stepped
        st.session_state.current_game_state = stepped
        _sync_hand_history(stepped)
        st.rerun()
    
    if state == WAITING_FOR_USER:
        # User may have submitted an action (set by Agent 2's render_action_panel)
        if st.session_state.pending_action is not None:
            st.session_state.app_state = PROCESSING_CRITIQUE
            st.rerun()
    
    if state == PROCESSING_CRITIQUE:
        # Run LLM critique (UI already displayed above, frozen during spinner)
        with st.spinner("AI Coach is analyzing your play…"):
            _run_processing_critique(gm, llm_critic, gto_solver)


if __name__ == "__main__":
    main()
