import sys
import json
from engine.game_manager import GameManager

def test_rotation():
    try:
        gm = GameManager()
        num_players = len(gm._native_game_state['table'].seats.players)
        if num_players != 6:
            print(f"FAILED: Expected 6 players, found {num_players}")
            sys.exit(1)

        expected_positions = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
        
        for i in range(6):
            state = gm.get_state()
            table = state['table']
            players = state['players']
            
            hand_num = i + 1
            dealer_seat = table['dealer_btn']
            hero = next(p for p in players if p['is_hero'])
            
            hero_seat = [idx for idx, p in enumerate(players) if p['is_hero']][0]
            hero_pos = hero['position']
            sb_p = next((p['name'] for p in players if p['position'] == 'SB'), 'N/A')
            bb_p = next((p['name'] for p in players if p['position'] == 'BB'), 'N/A')
            
            print(f"Hand {hand_num}: Dealer={dealer_seat}, HeroSeat={hero_seat}, HeroPos={hero_pos}, SB={sb_p}, BB={bb_p}")
            
            if hero_seat != 0:
                 print(f"FAILED: Hero seat is {hero_seat}, expected 0")
                 sys.exit(1)
            
            if dealer_seat != i:
                print(f"FAILED: Dealer seat is {dealer_seat}, expected {i}")
                sys.exit(1)
                
            if hero_pos != expected_positions[i]:
                print(f"FAILED: Hero position is {hero_pos}, expected {expected_positions[i]}")
                sys.exit(1)
            
            gm.start_new_hand()
            
        print("PASS: Rotation verified.")
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    test_rotation()
