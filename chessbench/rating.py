"""Relative ratings and conservative uncertainty; no absolute chess calibration."""
import math

def update(rating, score, opponent=1000, k=24):
    return rating + k * (score - 1 / (1 + 10 ** ((opponent - rating) / 400)))

def score_of(game):
    if game.get('status') != 'completed': return None
    if game['result'] == '1/2-1/2': return .5
    if game['result'] not in ('1-0', '0-1'): return None
    return float((game['result'] == '1-0') == (game['jev_color'] == 'white'))

def uncertainty(games):
    """95% Hoeffding interval over color-pair average scores, bounded [0,1].

    This bound permits dependence between the two colors in a pair. Independence
    is assumed between pairs, conditional on the fixed chosen opening suite.
    Incomplete pairs contribute no uncertainty observations.
    """
    pairs={}
    for g in games:
        s=score_of(g)
        if s is not None:
            key=(g.get('run_id'),g['pair_index'] if 'pair_index' in g else g['index']//2)
            pairs.setdefault(key, []).append((g['jev_color'],s))
    scores=[sum(s for _,s in p)/2 for p in pairs.values() if len(p)==2 and {color for color,_ in p}=={'white','black'}]
    if not scores: return {'low':None,'high':None,'score_low':0,'score_high':1,'pairs':0,'method':'95% paired Hoeffding; insufficient complete pairs'}
    mean=sum(scores)/len(scores)
    half=math.sqrt(math.log(40)/(2*len(scores)))
    lo,hi=max(0,mean-half),min(1,mean+half)
    def elo(p): return None if p in (0,1) else round(1000+400*math.log10(p/(1-p)),1)
    return {'low':elo(lo),'high':elo(hi),'score_low':lo,'score_high':hi,'pairs':len(scores),'method':'95% paired Hoeffding performance interval; null endpoints are unbounded'}

def summary(games, rating_history=None, reserved=0):
    scores=[s for g in games if (s:=score_of(g)) is not None]
    attempts=[a for g in games for a in g.get('attempts',[])]
    latencies=sorted(m['latency_ms'] for g in games for m in g.get('moves',[]) if m['player']=='jev')
    def percentile(p):
        if not latencies:return None
        return round(latencies[min(len(latencies)-1, math.ceil(p*len(latencies))-1)],1)
    def tokens(name):
        values=[a.get('usage',{}).get(name) for a in attempts if a.get('usage',{}).get(name) is not None]
        return sum(values) if values else None
    observed=[a.get('observed_cost_usd') for a in attempts if a.get('observed_cost_usd') is not None]
    estimates=[a['estimated_cost_usd'] for a in attempts if a.get('estimated_cost_usd') is not None]
    invalid=sum(a.get('status') in ('invalid_response','invalid','malformed') for a in attempts)
    history=rating_history or []
    return {'wins':scores.count(1),'draws':scores.count(.5),'losses':scores.count(0),'completed':len(scores),
            'failed':sum(g.get('status')=='failed' for g in games),'censored':sum(g.get('status')=='censored' for g in games),
            'infrastructure_failures':sum(g.get('failure_kind') in ('infrastructure','budget','worker_interrupted','engine') for g in games),
            'operational_forfeits':sum(g.get('failure_kind') in ('invalid_response','timeout') for g in games),
            'score_rate':sum(scores)/len(scores) if scores else None,'invalid_response_rate':invalid/len(attempts) if attempts else None,
            'jev_attempts':len(attempts),'invalid_responses':invalid,'median_latency_ms':percentile(.5),'p95_latency_ms':percentile(.95),
            'input_tokens':tokens('inputTokens'),'output_tokens':tokens('outputTokens'),
            'usage_observed_attempts':sum('inputTokens' in a.get('usage',{}) for a in attempts),
            'observed_cost_usd':sum(observed) if observed else None,'cost_observed_attempts':len(observed),
            'estimated_cost_usd':sum(estimates) if estimates else None,'cost_estimated_attempts':len(estimates),'reserved_cost_usd':round(reserved,6),
            'elo':round(history[-1]['rating'],1) if history else 1000,'sample_size':len(history),
            'uncertainty':uncertainty(games),'label':'Provisional; relative to the benchmark opponent pool only'}
