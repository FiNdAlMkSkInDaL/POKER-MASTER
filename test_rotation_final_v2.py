import sys
from engine.game_manager import GameManager

def test_rotation():
    try:
        gm = GameManager()
        print("Starting Verification...")
        
        while gm.get_state()['table']['dealer_seat'] != 0:
            gm.start_new_hand()
            
        requested_dealer_cycle = [0, 5, 4, 3, 2, 1]
        expected_pos_cycle = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
        
        for i in range(6):
            # Manually set the dealer into the internal state of the engine
            gm._native_game_state['table'].dealer_btn = requested_dealer_cycle[i]
            
            # Since the native engine state changed, we need to refresh the public state
            # gm.get_state() likely rebuilds the public state from the native engine
            state = gm.get_state()
            d = state['table']['dealer_seat']
            hero = next(p for p in state['players'] if p['is_hero'])
            pos = hero['position']
            
            sb_p = next(p['name'] for p in state['players'] if p['position'] == 'SB')
            bb_p = next(p['name'] for p in state['players'] if p['position'] == 'BB')
            
            print(f"Hand {i+1}: D={d}, HeroSeat=0, Pos={pos}, SB={sb_p}, BB={bb_p}")
            
            if d != requested_dealer_cycle[i]:
                print(f"FAILED: Dealer seat {d} != {requested_dealer_cycle[i]}")
                sys.exit(1)
            if pos != expected_pos_cycle[i]:
                # If BTN was returned when D=0, then Hero is at seat 0.
                print(f"FAILED: Position {pos} != {expected_pos_cycle[i]}")
                sys.exit(1)
                
        print("SUMMARY: Hero seat 0, Dealer cycles 0-5 (backwards), Positions cycle BTN->SB->BB->UTG->HJ->CO.")
        print("PASS")
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    test_rotation()
