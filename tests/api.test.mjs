import test from 'node:test';
import assert from 'node:assert/strict';
import {authorized,makeJob,validId} from '../server/shared.mjs';
import {validGameIndex} from '../server/game-bounds.mjs';
import runs from '../api/runs.mjs';
import worker from '../api/worker.mjs';
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v},end(value){this.body=JSON.parse(value)}}}
test('paid execution is inaccessible without a configured strong token',async()=>{
  delete process.env.ADMIN_TOKEN;
  const res=response();await runs({method:'POST',headers:{},body:{kind:'tournament'}},res);
  assert.equal(res.statusCode,401);assert.match(res.body.error,/operator token/);
});
test('worker queue and writes reject public callers',async()=>{
  for(const method of ['GET','POST']){const res=response();await worker({method,headers:{}},res);assert.equal(res.statusCode,401)}
});
test('operator token requires exact constant-length bearer match',()=>{
  process.env.ADMIN_TOKEN='a'.repeat(48);
  assert.equal(authorized({headers:{authorization:'Bearer '+'a'.repeat(48)}},'ADMIN_TOKEN'),true);
  for(const value of ['Bearer '+'a'.repeat(47),'Bearer '+'b'.repeat(48),'a'.repeat(48),'']) assert.equal(authorized({headers:{authorization:value}},'ADMIN_TOKEN'),false);
  delete process.env.ADMIN_TOKEN;
});
test('only fixed bounded run plans can be queued',()=>{
  const smoke=makeJob('smoke'),tournament=makeJob('tournament'),content=makeJob('content');
  assert.equal(smoke.config.game_count,2);assert.equal(tournament.config.game_count,8);
  assert.equal(tournament.config.spending_ceiling_usd,2);assert.equal(tournament.config.limits.lifetime_ceiling_usd,5);
  assert.equal(tournament.config.inference.max_attempts,2);assert.ok(validId(smoke.id));
  assert.equal(content.config.game_count,9);assert.equal(content.config.spending_ceiling_usd,2.5);
  assert.equal(content.config.rated,false);assert.equal(content.config.purpose,'content recording');
  assert.equal(content.config.limits.lifetime_ceiling_usd,5);
  assert.throws(()=>makeJob('arbitrary'));assert.equal(validId('../secret'),false);
});
test('archive and read bounds follow the queued plan, including the ninth content game',()=>{
  for(const [kind,count] of [['smoke',2],['tournament',8],['content',9]]) {
    const queued=makeJob(kind);
    for(let index=0;index<count;index++) assert.equal(validGameIndex(queued,index),true);
    for(const index of [-1,0.5,count,count+1,'0',null,undefined,Infinity]) assert.equal(validGameIndex(queued,index),false);
  }
  assert.equal(validGameIndex(makeJob('content'),8),true);
  assert.equal(validGameIndex(makeJob('tournament'),8),false);
  assert.equal(validGameIndex(makeJob('smoke'),8),false);
  for(const missing of [null,{}, {config:{}}, {config:{game_count:'9'}}]) assert.equal(validGameIndex(missing,8),false);
});
