"""One real 48-candidate interface probe, not a game or a rating observation."""
import json,os
from pathlib import Path
import chess
from chessbench.game import observe
from chessbench.jev import JevPlayer
from chessbench.store import Store
from chessbench.worker import load_env,ROOT
load_env(ROOT/'.env')
directory=Path(os.environ['BENCH_DATA_DIR']);directory.mkdir(parents=True,exist_ok=True)
store=Store(directory/'benchmark.sqlite')
board=chess.Board('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1')
observation=observe(board)
assert len(observation['legal_moves'])==48
plan={'kind':'interface_probe_not_game','max_attempts':1,'spending_ceiling_usd':0.002,'candidate_count':48,'purpose':'Confirm full candidate support on a legal high-mobility position'}
(directory/'interface-probe-plan.json').write_text(json.dumps(plan,indent=2))
player=JevPlayer(reserve=lambda amount:store.reserve('interface-probe','interface-probe',amount,.002),max_attempts=1)
result=player.choose(observation)
record={**plan,**result}
(directory/'interface-probe.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'kind':plan['kind'],'candidate_count':48,'selected':result['move'],'latency_ms':result['latency_ms'],'usage':result['attempts'][0]['usage'],'observed_cost_usd':result['attempts'][0]['observed_cost_usd']}))
