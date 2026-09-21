import { send,guard,read,validId,latest } from '../server/shared.mjs';
import { validGameIndex } from '../server/game-bounds.mjs';
export default guard(async(req,res)=>{
  if(req.method!=='GET') return send(res,405,{error:'Method not allowed'});
  const q=new URL(req.url,'http://local').searchParams,id=q.get('id'),game=Number(q.get('game'));
  if(!validId(id)||!Number.isInteger(game)||game<0) return send(res,400,{error:'Invalid game'});
  const job=await read(`jobs/${id}.json`);
  if(!job) return send(res,404,{error:'Unknown queued run'});
  if(!validGameIndex(job,game)) return send(res,400,{error:'Invalid game'});
  const archive=await read(`artifacts/${id}/game-${game}.json`);
  const g=archive||((await latest(id))?.games||[])[game];
  if(!g?.pgn) return send(res,404,{error:'PGN not yet available'});
  res.setHeader('Content-Type','application/x-chess-pgn');res.setHeader('Cache-Control','no-store');
  res.setHeader('Content-Disposition',`attachment; filename="${id}-game-${game+1}.pgn"`);res.end(g.pgn);
});
