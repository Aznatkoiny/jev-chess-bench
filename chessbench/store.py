"""SQLite owns durable execution, attempt reservations and the rating history."""
import json, math, sqlite3, time
from pathlib import Path
from .players import PlayerError
from .rating import update

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, body TEXT NOT NULL, sequence INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY,run_id TEXT,game_id TEXT,usd REAL,at REAL);
          CREATE TABLE IF NOT EXISTS ratings(game_id TEXT PRIMARY KEY,pool TEXT,rating REAL,score REAL,at REAL);
        ''')
    def load(self,id):
        row=self.db.execute('SELECT body FROM runs WHERE id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None
    def save(self,run):
        self.db.execute('INSERT INTO runs(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(run['id'],json.dumps(run,allow_nan=False)))
    def sequence(self,id):
        self.db.execute('UPDATE runs SET sequence=sequence+1 WHERE id=?',(id,))
        return self.db.execute('SELECT sequence FROM runs WHERE id=?',(id,)).fetchone()[0]
    def reserved(self,id=None):
        query='SELECT COALESCE(SUM(usd),0) FROM reservations'
        return self.db.execute(query+(' WHERE run_id=?' if id else ''),(id,) if id else ()).fetchone()[0]
    def reserve(self,run_id,game_id,amount,run_limit,lifetime_limit=5):
        if type(amount) not in (int,float) or not math.isfinite(amount) or amount<=0:
            raise ValueError('Reservation amount must be finite and positive')
        if any(type(limit) not in (int,float) or not math.isfinite(limit) or limit<0 for limit in (run_limit,lifetime_limit)):
            raise ValueError('Spending limits must be finite and nonnegative')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.reserved()+amount>lifetime_limit+1e-9 or self.reserved(run_id)+amount>run_limit+1e-9:
                raise PlayerError('budget','Conservative spending reservation ceiling reached')
            self.db.execute('INSERT INTO reservations(run_id,game_id,usd,at) VALUES(?,?,?,?)',(run_id,game_id,amount,time.time()))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK');raise
    def rate(self,game_id,pool,score):
        if self.db.execute('SELECT 1 FROM ratings WHERE game_id=?',(game_id,)).fetchone():return
        latest=self.db.execute('SELECT rating FROM ratings WHERE pool=? ORDER BY at DESC,rowid DESC LIMIT 1',(pool,)).fetchone()
        rating=update(latest[0] if latest else 1000,score)
        self.db.execute('INSERT INTO ratings VALUES(?,?,?,?,?)',(game_id,pool,rating,score,time.time()))
    def history(self,pool):
        return [{'game_id':r[0],'rating':r[1],'score':r[2],'at':r[3],'n':i+1} for i,r in enumerate(self.db.execute('SELECT game_id,rating,score,at FROM ratings WHERE pool=? ORDER BY at,rowid',(pool,)))]
