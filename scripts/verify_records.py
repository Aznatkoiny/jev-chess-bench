"""Independently replay archived real games and audit complete candidate delivery."""
import argparse,io,json,math
from pathlib import Path
import chess,chess.pgn
parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
totals={'games':0,'attempts':0,'legal_candidates':0,'max_candidates':0}
for path in sorted(args.directory.glob('*/game-*.json')):
    game=json.loads(path.read_text());record=chess.pgn.read_game(io.StringIO(game['pgn']))
    assert not record.errors,(path,record.errors)
    board=record.end().board()
    assert board.fen()==game['final_fen'],(path,'PGN/FEN mismatch')
    if game['status']=='completed':assert board.result(claim_draw=True)==game['result'],(path,'Outcome mismatch')
    else:assert game['result']=='*'
    played=chess.Board(game['initial_fen'])
    for move in game['moves']:
        parsed=chess.Move.from_uci(move['uci']);assert parsed in played.legal_moves
        assert played.san(parsed)==move['san'];played.push(parsed);assert played.fen()==move['fen']
    assert played.fen()==game['final_fen']
    successful=[]
    for attempt in game['attempts']:
        request=attempt['request'];state=request['state'];position=chess.Board(state['initial_fen'])
        for uci in state['history_uci']:position.push_uci(uci)
        assert position.fen()==state['fen']
        legal=sorted(m.uci() for m in position.legal_moves)
        assert legal==state['legal_moves']==sorted(request['questions']['move']['criteria'])
        assert request['model']=='typesafe-ai/jev'
        assert request['providerOptions']['gateway']=={'only':['typesafe-ai'],'disallowPromptTraining':True}
        assert not ({'engine_evaluation','opponent_recommendation','bestmove'} & state.keys())
        totals['attempts']+=1;totals['legal_candidates']+=len(legal);totals['max_candidates']=max(totals['max_candidates'],len(legal))
        if attempt['status']=='ok':
            answer=attempt['raw']['answers']['move'];assert answer['choice'] in legal;successful.append(answer['choice'])
    assert successful==[m['uci'] for m in game['moves'] if m['player']=='jev'],(path,'Selected move not executed exactly')
    totals['games']+=1
print(json.dumps({'verified':True,**totals}))
