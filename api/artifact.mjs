import { send,guard,read,validId } from '../server/shared.mjs';
import { validGameIndex } from '../server/game-bounds.mjs';
export default guard(async(req,res)=>{
  if(req.method!=='GET') return send(res,405,{error:'Method not allowed'});
  const q=new URL(req.url,'http://local').searchParams,id=q.get('id'),game=Number(q.get('game'));
  if(!validId(id)||!Number.isInteger(game)||game<0) return send(res,400,{error:'Invalid game'});
  const job=await read(`jobs/${id}.json`);
  if(!job) return send(res,404,{error:'Unknown queued run'});
  if(!validGameIndex(job,game)) return send(res,400,{error:'Invalid game'});
  const record=await read(`artifacts/${id}/game-${game}.json`);
  return send(res,record?200:404,record||{error:'Archive not yet available'});
});
