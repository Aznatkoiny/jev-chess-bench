import { send,guard,read,validId } from '../server/shared.mjs';
export default guard(async(req,res)=>{
  if(req.method!=='GET') return send(res,405,{error:'Method not allowed'});
  const q=new URL(req.url,'http://local').searchParams,id=q.get('id'),game=Number(q.get('game'));
  if(!validId(id)||!Number.isInteger(game)||game<0||game>=8) return send(res,400,{error:'Invalid game'});
  const record=await read(`artifacts/${id}/game-${game}.json`);
  return send(res,record?200:404,record||{error:'Archive not yet available'});
});
