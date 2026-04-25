from pypokerengine.api.emulator import Emulator
from pypokerengine.players import BasePokerPlayer

class CallPlayer(BasePokerPlayer):
    def declare_action(self, valid_actions, hole_card, round_state):
        return 'call', 0
    def receive_game_start_message(self, game_info): pass
    def receive_round_start_message(self, round_count, hole_card, seats): pass
    def receive_street_start_message(self, street, round_state): pass
    def receive_action_message(self, action, round_state): pass
    def receive_round_result_message(self, winners, hand_info, round_state): pass

emu = Emulator()
emu.set_game_rule(2, 10, 20, 0)
players_info = {
    '1': {'name': 'p1', 'stack': 1000},
    '2': {'name': 'p2', 'stack': 1000}
}
for uuid, info in players_info.items():
    emu.register_player(uuid, CallPlayer())

gs = emu.generate_initial_game_state(players_info)
gs, events = emu.start_new_round(gs)

for event in events:
    if event['type'] == 'event_ask_player':
        rs = event['round_state']
        print('POT_INFO:', rs['pot'])
        print('COMMUNITY_CARDS:', rs['community_card'])
        print('SEATS_SAMPLE:', rs['seats'][0])
        break
