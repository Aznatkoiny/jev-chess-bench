"""Single durable Spark worker. Polls Vercel; no inbound Spark port is required."""
from __future__ import annotations
import argparse, copy, fcntl, hashlib, importlib.metadata, json, os, platform, subprocess, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from .store import Store
from .match import play_game
from .players import StockfishPlayer
from .jev import JevPlayer
from .rating import score_of,summary

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config.json').read_text())
TERMINAL={'completed','failed','censored','stopped'}
def now():return datetime.now(timezone.utc).isoformat()
def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip() and not key.startswith('#'):os.environ.setdefault(key.strip(),value.strip().strip('\"\''))
def pool_hash(config,software=None):
    identity={k:config[k] for k in ('protocol_version','model_id','opponent','inference','limits','openings','draw_policy','failure_policy','elo')}
    identity['adapter_rules_fingerprints']={name:hashlib.sha256((ROOT/'chessbench'/name).read_bytes()).hexdigest() for name in ('game.py','jev.py','players.py')}
    identity['engine_binary_sha256']=(software or {}).get('stockfish_binary_sha256')
    identity['rules_library_version']=importlib.metadata.version('chess')
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
def public_snapshot(run):
    data=copy.deepcopy(run)
    for game in data['games']:
        for attempt in game.get('attempts',[]):
            attempt.pop('request',None);attempt.pop('raw',None)
    return data

class Hosted:
    def __init__(self,url,token):
        if not url.startswith('https://') and not url.startswith('http://127.0.0.1:'):raise ValueError('HTTPS app URL required')
        self.url=url.rstrip('/');self.token=token
    def call(self,payload=None):
        request=urllib.request.Request(self.url+'/api/worker',data=None if payload is None else json.dumps(payload,allow_nan=False).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        # urllib redirects are forbidden so the worker token never follows a redirect.
        from .jev import _NoRedirect
        try:
            with urllib.request.build_opener(_NoRedirect).open(request,timeout=25) as response:return json.load(response)
        except urllib.error.HTTPError as e:raise RuntimeError(f'Hosted worker API HTTP {e.code}') from None
        except (OSError,ValueError):raise RuntimeError('Hosted worker connection failed') from None

class Worker:
    def __init__(self,store,hosted,data_dir,engine):
        self.store,self.hosted,self.data_dir,self.engine=store,hosted,Path(data_dir),engine
        self.last_publish=0;self.last_heartbeat=0
    def heartbeat(self,status):
        if time.monotonic()-self.last_heartbeat>45:
            self.hosted.call({'action':'heartbeat','status':status});self.last_heartbeat=time.monotonic()
    def publish(self,run,force=False):
        self.store.save(run)
        if not force and time.monotonic()-self.last_publish<3:return
        run['updated_at']=now()
        self.hosted.call({'action':'snapshot','id':run['id'],'sequence':self.store.sequence(run['id']),'run':public_snapshot(run)})
        self.last_publish=time.monotonic();self.heartbeat('busy' if run['status']=='running' else 'idle')
    def archive(self,run,game):
        directory=self.data_dir/'archives'/run['id'];directory.mkdir(parents=True,exist_ok=True)
        (directory/f'game-{game["index"]}.json').write_text(json.dumps(game,indent=2,allow_nan=False))
        (directory/f'game-{game["index"]}.pgn').write_text(game['pgn'])
        self.hosted.call({'action':'archive','id':run['id'],'game':game['index'],'record':game})
    def execute(self,job):
        run=self.store.load(job['id'])
        if run and run['status'] in TERMINAL:return
        if run:
            # A crash after a paid request is ambiguous. Preserve its reservation
            # and stop, instead of silently repeating inference or reconstructing play.
            for game in run['games']:
                if game['status']=='running':
                    from .game import new_board,pgn
                    import chess
                    board=new_board(game.get('opening_moves',[]))
                    for move in game.get('moves',[]):board.push(chess.Move.from_uci(move['uci']))
                    game.update(status='failed',failure_kind='worker_interrupted',termination='worker_interrupted',result='*',final_fen=board.fen())
                    game['pgn']=pgn(board,{'Event':'Jev Chess Benchmark','Result':'*','Termination':'worker_interrupted','RunId':run['id'],'GameId':game['id']})
                if game.get('pgn') is not None:self.archive(run,game)
            run.update(status='stopped',stop_reason='Worker restarted during a run; no paid calls replayed',finished_at=now())
            run['summary']=summary(run['games'],self.store.history(run['pool_id']),self.store.reserved(run['id']))
            self.publish(run,True);return
        run=copy.deepcopy(job)
        kind=run.get('kind')
        expected={**CONFIG,**CONFIG.get(kind,{})}
        if kind not in ('smoke','tournament','content') or run.get('config')!=expected:
            run.update(status='stopped',stop_reason='Queued configuration differs from the worker frozen protocol',games=[])
            self.publish(run,True);return
        run['software']={'python':platform.python_version(),'platform':platform.platform(),'chess':importlib.metadata.version('chess'),'stockfish_binary_sha256':hashlib.sha256(Path(self.engine).read_bytes()).hexdigest(),'source_revision':(ROOT/'REVISION').read_text().strip() if (ROOT/'REVISION').exists() else 'uncommitted'}
        run['pool_id']=pool_hash(run['config'],run['software'])
        run.update(status='running',started_at=now(),games=[],rating_history=self.store.history(run['pool_id']))
        run['summary']=summary([],run['rating_history'])
        # First snapshot is the recorded plan before the first model call.
        self.publish(run,True)
        started=time.monotonic();infra=0
        for i in range(run['config']['game_count']):
            if time.monotonic()-started>CONFIG['limits']['run_seconds']:
                run['stop_reason']='run_time_limit';break
            # Content has four complete pairs plus one explicitly unpaired game.
            opening=CONFIG['openings'][0 if kind=='content' and i==8 else i//2]
            game={'id':f'{run["id"]}:{i}','run_id':run['id'],'index':i,'pair_index':i//2,'opening_name':opening['name'],'opening_moves':opening['moves'],'jev_color':'white' if i%2==0 else 'black','status':'pending','result':'*'}
            run['games'].append(game)
            reserve=lambda amount:self.store.reserve(run['id'],game['id'],amount,run['config']['spending_ceiling_usd'],CONFIG['limits']['lifetime_ceiling_usd'])
            jev=JevPlayer(reserve=reserve)
            opponent=StockfishPlayer(self.engine,skill_level=0,depth=4,timeout_seconds=2)
            players={'white':jev if i%2==0 else opponent,'black':opponent if i%2==0 else jev}
            def checkpoint(g):
                run['summary']=summary(run['games'],run['rating_history'],self.store.reserved(run['id']))
                self.store.save(run) # Durable after every completed move, before publishing.
                try:self.publish(run)
                except RuntimeError:pass # Match remains durable locally; final publication retries below.
            try:
                effective_limits={**CONFIG['limits'],'game_seconds':min(CONFIG['limits']['game_seconds'],max(0,CONFIG['limits']['run_seconds']-(time.monotonic()-started)))}
                play_game(game,players,effective_limits,checkpoint)
            except Exception:
                # Do not print exceptions containing transport credentials or raw responses.
                game.update(status='failed',result='*',failure_kind='infrastructure',termination='harness_exception')
                game.setdefault('pgn','')
            game['opponent_metadata']=opponent.metadata
            game['finished_at']=now()
            score=score_of(game)
            if kind=='tournament' and score is not None:self.store.rate(game['id'],run['pool_id'],score)
            run['rating_history']=self.store.history(run['pool_id'])
            run['summary']=summary(run['games'],run['rating_history'],self.store.reserved(run['id']))
            self.store.save(run)
            # Publishing is required between games. If unavailable, stop paying.
            self.archive(run,game);self.publish(run,True)
            print(json.dumps({'run':run['id'],'game':i+1,'status':game['status'],'result':game['result'],'termination':game['termination'],'plies':len(game['moves'])}),flush=True)
            if game.get('failure_kind') in ('infrastructure','engine','worker_interrupted'):infra+=1
            if game.get('failure_kind')=='budget' or infra>=CONFIG['limits']['stop_after_infrastructure_failures']:
                run['stop_reason']='budget' if game.get('failure_kind')=='budget' else 'infrastructure_failure_limit';break
        run.update(status='stopped' if 'stop_reason' in run else 'completed',finished_at=now())
        run['summary']=summary(run['games'],run['rating_history'],self.store.reserved(run['id']))
        self.store.save(run)
        self.publish(run,True)
        path=self.data_dir/'archives'/run['id']/'run.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(run,indent=2,allow_nan=False))
    def poll(self):
        self.heartbeat('idle')
        for job in self.hosted.call()['jobs']:self.execute(job)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    load_env(ROOT/'.env')
    directory=Path(os.environ.get('BENCH_DATA_DIR',ROOT/'data'));directory.mkdir(parents=True,exist_ok=True)
    lock=open(directory/'worker.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another worker owns this data directory')
    worker=Worker(Store(directory/'benchmark.sqlite'),Hosted(os.environ['BENCH_APP_URL'],os.environ['WORKER_TOKEN']),directory,os.environ.get('STOCKFISH_PATH','/usr/games/stockfish'))
    while True:
        try:worker.poll()
        except Exception:print('Worker cycle could not finish; local records retained. Will retry connection.',flush=True)
        if args.once:break
        time.sleep(5)
if __name__=='__main__':main()
