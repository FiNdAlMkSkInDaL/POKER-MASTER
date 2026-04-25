from datetime import datetime
import streamlit as st

def handle_user_action(action: str, amount: float, reasoning: str) -> None:
    gs = st.session_state.get("current_game_state", {})
    table = gs.get("table", {})
    to_call = float(table.get("current_bet_to_call", 0.0))
    hero_player_id = gs.get("hero_player_id", "p0")

    st.session_state.pending_action = {
        "action": action,
        "amount": round(amount, 2),
        "reasoning": reasoning.strip(),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state.is_waiting_for_ai = True

    # Speech bubble for hero seat
    if action == "Raise":
        bubble_text = f"Hero raises to ${amount:.0f}"
    elif action == "Call":
        bubble_text = f"Hero calls ${to_call:.0f}"
    elif action == "Check":
        bubble_text = "Hero checks"
    else:
        bubble_text = "Hero folds"
    if "action_labels" not in st.session_state:
        st.session_state.action_labels = {}
    st.session_state.action_labels[hero_player_id] = bubble_text

    user_line = f"Action: {action}"
    if action == "Raise":
        user_line += f" to ${amount:.2f}"
    elif action == "Call":
        user_line += f" ${to_call:.2f}"

    user_line += f" | Reasoning: {reasoning.strip()}"

    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []

    st.session_state.ai_chat_history.append(
        {
            "role": "user",
            "content": user_line,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    )

_TABLE_CSS = """
<style>
  /* ── Card chips ───────────────────────────────────────── */
  .card-chip {
    display: inline-block;
    margin: 2px 3px;
    padding: 7px 10px;
    border-radius: 9px;
    background: linear-gradient(180deg, #ffffff 0%, #f0f0f0 100%);
    border: 1px solid #cccccc;
    font-size: 0.95rem;
    font-weight: 800;
    min-width: 42px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.18);
    letter-spacing: 0.02em;
  }
  .card-red  { color: #c62828; }
  .card-black { color: #111111; }
  .card-hidden {
    color: #aaaaaa;
    background: linear-gradient(180deg, #d0d0d0 0%, #b8b8b8 100%);
    border-color: #999;
  }
  /* ── Player seats ─────────────────────────────────────── */
  .player-seat {
    border-radius: 14px;
    padding: 10px 8px;
    text-align: center;
    background: #1a2535;
    border: 2px solid #2d3f55;
    color: #dde8f8;
    min-height: 118px;
  }
  .player-seat.acting {
    border-color: #ffd700;
    background: #1e2d12;
    box-shadow: 0 0 14px rgba(255, 215, 0, 0.55);
  }
  .player-seat.hero {
    border-color: #4fc3f7;
    background: #0d2136;
  }
  .player-seat.acting.hero {
    border-color: #ffd700;
    background: #0d2e12;
    box-shadow: 0 0 14px rgba(255, 215, 0, 0.55);
  }
  .player-seat.folded {
    opacity: 0.38;
    filter: grayscale(60%);
  }
  .player-seat.empty {
    opacity: 0.12;
    background: #111820;
    border-style: dashed;
    border-color: #333;
  }
  .seat-name  { font-weight: 700; font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .seat-pos   { font-size: 0.92rem; color: #e1f5fe; margin: 2px 0 4px; font-weight: 800; letter-spacing: 0.1em; }
    .seat-pos.dealer { color: #ffd54f; }
    .dealer-badge {
        display: inline-block;
        margin-left: 5px;
        padding: 1px 6px;
        border-radius: 999px;
        font-size: 0.62rem;
        font-weight: 800;
        color: #1c1200;
        background: linear-gradient(135deg, #ffd54f 0%, #ffb300 100%);
        border: 1px solid #9e7300;
        vertical-align: middle;
    }
    .seat-name  { font-weight: 600; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .seat-stack { font-size: 1rem; font-weight: 700; color: #a5d6a7; }
  .seat-cards { margin: 5px 0 3px; min-height: 28px; }
  .seat-status { font-size: 0.68rem; margin-top: 4px; }
  .status-folded { color: #ef9a9a; }
  .status-allin  { color: #ffcc80; }
  .status-active { color: #c8e6c9; }
  .acting-label { font-size: 0.68rem; color: #ffd700; font-weight: 700; letter-spacing: 0.05em; margin-top: 3px; }
  /* ── Board / pot zone ─────────────────────────────────── */
  .board-zone {
    border-radius: 18px;
    padding: 14px 10px;
    background: radial-gradient(ellipse at 50% 40%, #1f6f4a 0%, #0b3e28 75%);
    border: 2px solid #2e7d52;
    text-align: center;
    color: white;
    min-height: 118px;
  }
  .board-street {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #a3c4b5;
    margin-bottom: 6px;
  }
  .board-pot {
    font-size: 1.25rem;
    font-weight: 800;
    color: #ffd54f;
    margin-bottom: 6px;
  }
  .board-call {
    font-size: 0.78rem;
    color: #b2dfdb;
    margin-top: 6px;
  }
    .board-last-action {
        margin: 0 auto 8px;
        max-width: 85%;
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(0, 0, 0, 0.35);
        border: 1px solid #80cbc4;
        color: #e0f7fa;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
  /* ── Bet chips (money in front of player) ─────────────── */
  .bet-chip {
    display: inline-block;
    margin: 3px auto 0;
    padding: 2px 8px;
    border-radius: 999px;
    background: linear-gradient(135deg, #ffd700 0%, #f0a500 100%);
    border: 1px solid #c88000;
    color: #1a1000;
    font-size: 0.7rem;
    font-weight: 800;
    box-shadow: 0 1px 4px rgba(0,0,0,0.35);
    letter-spacing: 0.03em;
    white-space: nowrap;
    position: relative;
    z-index: 100;
  }
  .bet-chip-wrap {
    text-align: center;
    min-height: 20px;
    margin: 2px 0;
    position: relative;
    z-index: 100;
  }
  /* ── Action tag (last action label) ──────────────────────── */
  .action-tag {
    display: inline-block;
    margin-top: 3px;
    padding: 2px 6px;
    background: #263238;
    color: #80cbc4;
    border: 1px solid #37474f;
    border-radius: 5px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    white-space: nowrap;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* ── Action speech bubbles ────────────────────────────── */
  @keyframes bubble-fade {
    0%, 70% { opacity: 1; transform: translateY(0); }
    100%    { opacity: 0; transform: translateY(-5px); }
  }
  .speech-bubble {
    display: inline-block;
    margin-top: 5px;
    padding: 3px 7px;
    background: #fffde7;
    color: #1a1a1a;
    border-radius: 8px;
    font-size: 0.68rem;
    font-weight: 700;
    border: 1px solid #f9a825;
    box-shadow: 0 1px 4px rgba(0,0,0,0.25);
    animation: bubble-fade 3s ease forwards;
    white-space: nowrap;
    max-width: 130px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
"""


def _bet_chip_html(amount: int) -> str:
    """Gold pill showing the player's street contribution. Returns empty string for $0."""
    if amount <= 0:
        return ""
    return f"<div class='bet-chip-wrap'><span class='bet-chip'>${amount}</span></div>"


def _card_html(card: str) -> str:
    """Render one card chip, coloring hearts/diamonds red and clubs/spades black."""
    suit = card[-1].lower() if card else ""
    color_cls = "card-red" if suit in ("h", "d") else "card-black"
    return f"<span class='card-chip {color_cls}'>{card}</span>"


def _seat_html(
    player: dict,
    is_acting: bool,
    bubble_text: str = "",
    action_tag: str = "",
    is_dealer: bool = False,
) -> str:
    """Render one player seat box as an HTML string."""
    name = player.get("name", "Player")
    position = player.get("position", "-")
    stack = int(player.get("stack", 0))
    is_hero = player.get("is_hero", False)
    has_folded = player.get("has_folded", False)
    is_all_in = player.get("is_all_in", False)

    # Seat class
    classes = ["player-seat"]
    if is_acting:
        classes.append("acting")
    if is_hero:
        classes.append("hero")
    if has_folded:
        classes.append("folded")
    seat_cls = " ".join(classes)

    # Status label
    if has_folded:
        status_text, status_cls = "Folded", "status-folded"
    elif is_all_in:
        status_text, status_cls = "All-In", "status-allin"
    else:
        status_text, status_cls = "Active", "status-active"

    # Cards
    if is_hero:
        cards = player.get("hole_cards", [])
        cards_html = "".join(_card_html(c) for c in cards) if cards else (
            "<span class='card-chip card-hidden'>?</span>"
            "<span class='card-chip card-hidden'>?</span>"
        )
    else:
        cards_html = (
            "<span class='card-chip card-hidden'>🂠</span>"
            "<span class='card-chip card-hidden'>🂠</span>"
        ) if not has_folded else ""

    acting_label = "<div class='acting-label'>▶ TO ACT</div>" if is_acting else ""
    bubble_html = f"<div class='speech-bubble'>{bubble_text}</div>" if bubble_text else ""
    tag_html = f"<div class='action-tag'>{action_tag}</div>" if action_tag else ""
    dealer_badge = "<span class='dealer-badge'>D</span>" if is_dealer else ""
    pos_cls = "seat-pos dealer" if is_dealer else "seat-pos"

    return (
        f"<div class='{seat_cls}'>"
        f"  <div class='{pos_cls}'>{position}{dealer_badge}</div>"
        f"  <div class='seat-name'>{name}</div>"
        f"  <div class='seat-stack'>${stack}</div>"
        f"  <div class='seat-cards'>{cards_html}</div>"
        f"  <div class='seat-status {status_cls}'>{status_text}</div>"
        f"  {acting_label}"
        f"  {tag_html}"
        f"  {bubble_html}"
        f"</div>"
    )


def _empty_seat_html() -> str:
    return "<div class='player-seat empty' style='min-height:118px;'></div>"


def render_poker_table() -> None:
    gs = st.session_state.get("current_game_state", {})
    waiting_to_start = st.session_state.get("app_state") == "WAITING_TO_START"

    table = gs.get("table", {})
    players = gs.get("players", [])

    acting_id = table.get("action_on_player_id", "")
    last_action = table.get("last_action") or {}
    last_actor_id = last_action.get("player_id", "")
    last_description = table.get("last_action_description", "")
    players_by_position: dict = {str(p.get("position", "")).upper(): p for p in players}
    dealer_seat = table.get("dealer_seat", None)
    action_labels: dict = st.session_state.get("action_labels", {})

    def seat_by_pos(pos: str) -> dict:
        return players_by_position.get(pos.upper(), {})

    def is_acting(p: dict) -> bool:
        return bool(p) and p.get("player_id", "") == acting_id

    def bubble(p: dict) -> str:
        return action_labels.get(p.get("player_id", ""), "") if p else ""

    def bet_chip(p: dict) -> str:
        if not p:
            return ""
        contrib = int(p.get("contribution_this_street", 0))
        return _bet_chip_html(contrib)

    def action_tag(p: dict) -> str:
        if not p:
            return ""
        return last_description if p.get("player_id", "") == last_actor_id else ""

    def has_button(p: dict) -> bool:
        if not p:
            return False
        if dealer_seat is not None and p.get("seat") == dealer_seat:
            return True
        return str(p.get("position", "")).upper() == "BTN"

    st.markdown(_TABLE_CSS, unsafe_allow_html=True)
    st.subheader("Poker Table")
    if gs:
        st.caption(f"Street: {table.get('street', '-').capitalize()}")
    else:
        st.caption("Live table view loading...")

    # ── Row 1: [UTG] [HJ] ────────────────────────────────────────────────
    _, col_utg, col_hj, _ = st.columns([1, 1, 1, 1], gap="small")
    with col_utg:
        p_utg = seat_by_pos("UTG")
        st.markdown(
            _seat_html(p_utg, is_acting(p_utg), bubble(p_utg), action_tag(p_utg), has_button(p_utg))
            if p_utg
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )
        st.markdown(bet_chip(p_utg), unsafe_allow_html=True)
    with col_hj:
        p_hj = seat_by_pos("HJ")
        st.markdown(
            _seat_html(p_hj, is_acting(p_hj), bubble(p_hj), action_tag(p_hj), has_button(p_hj))
            if p_hj
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )
        st.markdown(bet_chip(p_hj), unsafe_allow_html=True)

    # ── Row 2: [BB] | [Board/Pot] | [CO] ─────────────────────────────────
    col_bb, col_board, col_co = st.columns([1, 2, 1], gap="small")
    with col_bb:
        p_bb = seat_by_pos("BB")
        st.markdown(
            _seat_html(p_bb, is_acting(p_bb), bubble(p_bb), action_tag(p_bb), has_button(p_bb))
            if p_bb
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )
        st.markdown(bet_chip(p_bb), unsafe_allow_html=True)

    with col_board:
        if waiting_to_start:
            # ── Start screen: prominent button replaces board content ────
            st.markdown(
                "<div class='board-zone' style='display:flex;align-items:center;justify-content:center;'>"
                "  <div style='text-align:center;'>"
                "    <div class='board-street'>POKER MASTER</div>"
                "    <div style='color:#a3c4b5;font-size:0.9rem;margin:8px 0 14px;'>Ready to play?</div>"
                "  </div>"
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button("▶ Start New Hand", use_container_width=True, type="primary"):
                st.session_state.action_labels = {}
                st.session_state.app_state = "ENGINE_STEP"
                st.rerun()
        else:
            board_cards = table.get("board_cards", [])
            pot = int(table.get("pot_total", 0))
            to_call = int(table.get("current_bet_to_call", 0))
            last_action_html = (
                f"<div class='board-last-action'>{last_description}</div>"
                if last_description
                else ""
            )
            cards_html = (
                "".join(_card_html(c) for c in board_cards)
                if board_cards
                else "<i style='color:#a3c4b5; font-size:0.85rem;'>Preflop — no board yet</i>"
            )
            call_line = (
                f"<div class='board-call'>To call: ${to_call}</div>" if to_call > 0 else ""
            )
            st.markdown(
                f"<div class='board-zone'>"
                f"  {last_action_html}"
                f"  <div class='board-street'>{table.get('street', 'preflop').upper()}</div>"
                f"  <div class='board-pot'>Pot ${pot}</div>"
                f"  <div>{cards_html}</div>"
                f"  {call_line}"
                f"</div>",
                unsafe_allow_html=True,
            )

    with col_co:
        p_co = seat_by_pos("CO")
        st.markdown(
            _seat_html(p_co, is_acting(p_co), bubble(p_co), action_tag(p_co), has_button(p_co))
            if p_co
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )
        st.markdown(bet_chip(p_co), unsafe_allow_html=True)

    # ── Row 3: [SB] [BTN/Hero] ───────────────────────────────────────────
    # Chips go ABOVE the seat for bottom-row players (pushed toward the board)
    _, col_sb, col_btn, _ = st.columns([1, 1, 1, 1], gap="small")
    with col_sb:
        p_sb = seat_by_pos("SB")
        chip_sb = bet_chip(p_sb)
        if chip_sb:
            st.markdown(chip_sb, unsafe_allow_html=True)
        st.markdown(
            _seat_html(p_sb, is_acting(p_sb), bubble(p_sb), action_tag(p_sb), has_button(p_sb))
            if p_sb
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )
    with col_btn:
        p_btn = seat_by_pos("BTN")
        chip_btn = bet_chip(p_btn)
        if chip_btn:
            st.markdown(chip_btn, unsafe_allow_html=True)
        st.markdown(
            _seat_html(p_btn, is_acting(p_btn), bubble(p_btn), action_tag(p_btn), has_button(p_btn))
            if p_btn
            else _empty_seat_html(),
            unsafe_allow_html=True,
        )

def render_action_panel() -> None:
    gs = st.session_state.get("current_game_state", {})
    app_state = st.session_state.get("app_state", "")
    is_engine_step = app_state == "ENGINE_STEP"
    table = gs.get("table", {})
    players = gs.get("players", [])
    hero = next((p for p in players if p.get("is_hero")), {})
    legal_actions = gs.get("legal_actions", [])
    
    chat_history = st.session_state.get("ai_chat_history", [])
    is_waiting_for_ai = bool(st.session_state.get("is_waiting_for_ai", False))
    controls_disabled = is_waiting_for_ai or is_engine_step

    st.subheader("Action Panel")
    st.caption("Choose your move and explain your reasoning before submitting.")

    legal_action_names = {
        str(action.get("action", "")).lower()
        for action in legal_actions
        if isinstance(action, dict)
    }
    if not legal_action_names:
        legal_action_names = {"fold", "check", "call", "raise"}

    can_raise = "raise" in legal_action_names
    action_options = ["Fold", "Check", "Call"]
    if can_raise:
        action_options.append("Raise")

    if "call" in legal_action_names and "Call" in action_options:
        default_action = "Call"
    elif "check" in legal_action_names and "Check" in action_options:
        default_action = "Check"
    else:
        default_action = action_options[0]

    action = st.radio(
        "Select Action",
        action_options,
        horizontal=True,
        index=action_options.index(default_action),
        disabled=controls_disabled,
    )
    if not can_raise:
        st.caption("Raise is not a legal action in this spot.")

    min_raise_to = float(table.get("min_raise_to", 0.0))
    max_raise_to = float(hero.get("stack", 0.0)) + float(table.get("current_bet_to_call", 0.0))
    if max_raise_to < min_raise_to:
        max_raise_to = min_raise_to if min_raise_to > 0 else 1.0

    to_call = float(table.get("current_bet_to_call", 0.0))
    default_raise = max(min_raise_to, min(to_call * 2.5, max_raise_to))
    raise_amount = 0.0

    if can_raise and max_raise_to > min_raise_to:
        raise_amount = st.slider(
            "Raise To ($)",
            min_value=float(min_raise_to),
            max_value=float(max_raise_to),
            value=float(default_raise),
            step=1.0,
            disabled=action != "Raise" or controls_disabled,
        )
    else:
        st.caption("No further raises possible (All-in situation).")
        # Keep a stable disabled widget when Raise is selected in an edge state.
        if action == "Raise":
            safe_min = float(min_raise_to)
            safe_max = float(min_raise_to + 0.01)
            raise_amount = st.slider(
                "Raise To ($)",
                min_value=safe_min,
                max_value=safe_max,
                value=safe_min,
                step=0.01,
                disabled=True,
            )

    reasoning = st.text_area(
        "Reasoning (Required)",
        placeholder=(
            "Example: I call because villain can still have draws on this texture, "
            "and my hand blocks strong value combos."
        ),
        height=140,
        disabled=controls_disabled,
    )

    if is_engine_step:
        st.info("Bot is acting...", icon="⏳")
    elif st.button("Submit Action", use_container_width=True, type="primary", disabled=is_waiting_for_ai):
        if not reasoning.strip():
            st.warning("Please enter your reasoning before submitting.")
        else:
            amount = raise_amount if action == "Raise" else 0.0
            handle_user_action(action=action, amount=amount, reasoning=reasoning)
            st.success("Action submitted. Waiting for AI response.")

    if is_waiting_for_ai:
        st.info("Waiting for AI...", icon="⏳")


# ── Colour palette for action types ─────────────────────────────────────────
_ACTION_COLORS: dict = {
    "fold":   "#888888",  # grey
    "check":  "#aaaaaa",  # light grey
    "call":   "#4caf50",  # green
    "raise":  "#ff9800",  # orange
    "cbet":   "#ff9800",  # treat cbet as raise-style aggression
    "bet":    "#ff9800",  # open bet — same orange
    "all-in": "#f44336",  # red
    "allin":  "#f44336",
}

_STREET_LABELS: dict = {
    "preflop": "PRE-FLOP",
    "flop":    "FLOP",
    "turn":    "TURN",
    "river":   "RIVER",
}


def render_hand_history_sidebar() -> None:
    """Render a grouped, colour-coded hand history in the Streamlit sidebar."""
    st.sidebar.title("Hand History")

    gs = st.session_state.get("current_game_state", {})
    players = gs.get("players", [])
    # Build a quick id→name lookup from the live game state.
    _name_map: dict = {p["player_id"]: p.get("name", p["player_id"]) for p in players}

    action_history: dict = gs.get("action_history", {})

    # Collect any streets that actually have entries (in canonical street order).
    populated_streets = [
        s for s in ("preflop", "flop", "turn", "river")
        if action_history.get(s)
    ]

    if not populated_streets:
        st.sidebar.caption("No actions yet this hand.")
        return

    for street in populated_streets:
        label = _STREET_LABELS.get(street, street.upper())
        st.sidebar.markdown(
            f"<div style='text-align:center; color:#cccccc; margin:6px 0 2px;'>"
            f"<small>── {label} ──</small></div>",
            unsafe_allow_html=True,
        )

        for entry in action_history[street]:
            if entry.get("is_forced"):
                # Show blind/ante posts in a subdued style.
                pid   = entry.get("player_id", "?")
                name  = _name_map.get(pid, pid)
                amt   = entry.get("amount", 0)
                st.sidebar.markdown(
                    f"<span style='color:#666666; font-size:0.82em'>"
                    f"{name} posts ${amt}</span>",
                    unsafe_allow_html=True,
                )
                continue

            pid    = entry.get("player_id", "?")
            name   = _name_map.get(pid, pid)
            action = entry.get("action", "")
            amount = entry.get("amount", 0)

            color   = _ACTION_COLORS.get(action.lower(), "#dddddd")
            amt_str = f" <b>${amount}</b>" if amount else ""
            hero_p  = next((p for p in players if p.get("player_id") == pid), {})
            bold_open  = "<b>" if hero_p.get("is_hero") else ""
            bold_close = "</b>" if hero_p.get("is_hero") else ""

            st.sidebar.markdown(
                f"<div style='margin:1px 0; font-size:0.9em'>"
                f"{bold_open}{name}{bold_close} "
                f"<span style='color:{color}'>{action.upper()}</span>"
                f"{amt_str}"
                f"</div>",
                unsafe_allow_html=True,
            )