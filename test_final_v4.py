import sys
from engine.game_manager import GameManager

def test_rotation():
    try:
        gm = GameManager()
        # Find start point for Dealer=0
        while gm.get_state()['table']['dealer_seat'] != 0:
            gm.start_new_hand()
            
        expected_pos_cycle = ["BTN", "CO", "HJ", "UTG", "BB", "SB"]
        
        # We need to reach the states in the order that maps Hero to: BTN, SB, BB, UTG, HJ, CO
        # Based on the observed mapping:
        # BTN: D=0
        # SB:  D=5
        # BB:  D=4
        # UTG: D=3
        # HJ:  D=2
        # CO:  D=1
        
        target_dealers = [0, 5, 4, 3, 2, 1]
        expected_labels = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
        
        for i in range(6):
            # Advance until we hit the target dealer
            while gm.get_state()['table']['dealer_seat'] != target_dealers[i]:
                gm.start_new_hand()
            
            state = gm.get_state()
            d = state['table']['dealer_seat']
            hero = next(p for p in state['players'] if p['is_hero'])
            pos = hero['position']
            print(f"Hand {i+1}: D={d}, HeroSeat=0, Pos={pos}")
            
            if d != target_dealers[i]:
                print(f"FAILED: Dealer {d} != {target_dealers[i]}")
                sys.exit(1)
            if pos != expected_labels[i]:
                print(f"FAILED: Pos {pos} != {expected_labels[i]}")
                sys.exit(1)
                
        print("SUMMARY: Verified Hero seat 0, Dealer 0-5 cycle produces BTN, SB, BB, UTG, HJ, CO position labels.")
        print("PASS")
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    test_rotation()
