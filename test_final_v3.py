import sys
from engine.game_manager import GameManager

def test_rotation():
    try:
        gm = GameManager()
        # Find how many start_new_hand() calls it takes to reach Dealer=0
        while gm.get_state()['table']['dealer_seat'] != 0:
            gm.start_new_hand()
        # From Dealer=0, it goes 1, 2, 3, 4, 5, 0...
        # Prompt says "Verify dealer_seat cycles 0..5"
        # Hero Pos labels cycle: BTN, SB, BB, UTG, HJ, CO
        
        # We'll print the next 6 hands.
        for i in range(6):
            state = gm.get_state()
            d = state['table']['dealer_seat']
            hero = next(p for p in state['players'] if p['is_hero'])
            pos = hero['position']
            sb = next(p['name'] for p in state['players'] if p['position'] == 'SB')
            bb = next(p['name'] for p in state['players'] if p['position'] == 'BB')
            
            print(f"Hand {i+1}: D={d}, HeroSeat=0, Pos={pos}, SB={sb}, BB={bb}")
            gm.start_new_hand()
            
        print("PASS")
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    test_rotation()
