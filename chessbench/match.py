"""A match executor sees game rules; adapters receive only their observation."""
import time
import chess
from .game import new_board,observe,outcome,pgn
from .players import PlayerError

def play_game(record, players, limits, checkpoint=lambda record:None):
    board=new_board(record['opening_moves'])
    record.update(status='running',initial_fen=board.fen(),moves=[],attempts=[],failures=[],result='*')
    start=time.monotonic()
    checkpoint(record)
    try:
        while True:
            terminal=outcome(board)
            if terminal:
                record.update(status='completed',result=terminal['result'],termination=terminal['termination']);break
            if len(record['moves'])>=limits['max_plies'] or time.monotonic()-start>=limits['game_seconds']:
                record.update(status='censored',termination='ply_limit' if len(record['moves'])>=limits['max_plies'] else 'game_time_limit');break
            color='white' if board.turn==chess.WHITE else 'black'
            player_name='jev' if color==record['jev_color'] else 'opponent'
            observation=observe(board)
            legal_moves=frozenset(move.uci() for move in board.legal_moves)
            try:
                selected=players[color].choose(observation)
                if not isinstance(selected,dict):
                    raise PlayerError('invalid_response','Adapter did not return a move response')
                record['attempts'].extend(selected.get('attempts',[]) if player_name=='jev' else [])
                if time.monotonic()-start>=limits['game_seconds']:
                    record.update(status='censored',termination='game_time_limit');break
                move=selected.get('move')
                if not isinstance(move,str) or move not in legal_moves:
                    raise PlayerError('invalid_response','Adapter returned an unlisted move')
                parsed=chess.Move.from_uci(move);san=board.san(parsed);board.push(parsed)
                record['moves'].append({'uci':move,'san':san,'fen':board.fen(),'player':player_name,'latency_ms':selected['latency_ms']})
            except PlayerError as e:
                if player_name=='jev':record['attempts'].extend(e.attempts)
                kind=e.kind if player_name=='jev' else 'engine'
                record.update(status='failed',failure_kind=kind,termination=kind)
                record['failures'].append({'kind':kind,'player':player_name,'message':str(e),'ply':len(record['moves'])})
                break
            checkpoint(record)
    finally:
        record['elapsed_seconds']=round(time.monotonic()-start,3)
        record['final_fen']=board.fen()
        record['pgn']=pgn(board,{'Event':'Jev Chess Benchmark','White':'Jev' if record['jev_color']=='white' else 'Stockfish 16','Black':'Jev' if record['jev_color']=='black' else 'Stockfish 16','Result':record.get('result','*'),'Termination':record.get('termination','interrupted'),'RunId':record['run_id'],'GameId':record['id']})
        for player in players.values():
            if hasattr(player,'close'):player.close()
        checkpoint(record)
    return record
