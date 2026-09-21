import test from 'node:test';
import assert from 'node:assert/strict';
import {authorized,makeJob,validId} from '../server/shared.mjs';
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
  const smoke=makeJob('smoke'),tournament=makeJob('tournament');
  assert.equal(smoke.config.game_count,2);assert.equal(tournament.config.game_count,8);
  assert.equal(tournament.config.spending_ceiling_usd,2);assert.equal(tournament.config.limits.lifetime_ceiling_usd,5);
  assert.equal(tournament.config.inference.max_attempts,2);assert.ok(validId(smoke.id));
  assert.throws(()=>makeJob('arbitrary'));assert.equal(validId('../secret'),false);
});
