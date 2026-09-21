import { authorized,send,guard,body,blobs,read,write,validId } from '../server/shared.mjs';
import { validGameIndex } from '../server/game-bounds.mjs';
export default guard(async(req,res)=>{
  if(!authorized(req,'WORKER_TOKEN')) return send(res,401,{error:'Unauthorized'});
  if(req.method==='GET') {
    const jobs=await blobs('jobs/'); jobs.sort((a,b)=>new Date(a.uploadedAt)-new Date(b.uploadedAt));
    return send(res,200,{jobs:await Promise.all(jobs.map(j=>read(j.url)))});
  }
  if(req.method!=='POST') return send(res,405,{error:'Method not allowed'});
  const data=await body(req);
  if(data.action==='heartbeat') {
    await write('worker/health.json',{last_seen:new Date().toISOString(),status:data.status==='busy'?'busy':'idle',worker:'DGX Spark CPU worker',protocol_version:1},true);
    return send(res,200,{ok:true});
  }
  if(!validId(data.id)) return send(res,400,{error:'Invalid run ID'});
  const job=await read(`jobs/${data.id}.json`);
  if(!job) return send(res,404,{error:'Unknown queued run'});
  if(data.action==='snapshot' && Number.isSafeInteger(data.sequence) && data.sequence>=0 && data.sequence<1000000 && data.run?.id===data.id) {
    // Immutable versioned names avoid stale overwrite caches. Only the single worker writes snapshots.
    await write(`snapshots/${data.id}/${String(data.sequence).padStart(8,'0')}.json`,data.run);
    return send(res,200,{ok:true});
  }
  if(data.action==='archive' && validGameIndex(job,data.game)) {
    const path=`artifacts/${data.id}/game-${data.game}.json`;
    const existing=await read(path);
    if(existing) {
      if(JSON.stringify(existing)!==JSON.stringify(data.record)) return send(res,409,{error:'Immutable archive already exists with different content'});
      return send(res,200,{ok:true});
    }
    await write(path,data.record);
    return send(res,200,{ok:true});
  }
  return send(res,400,{error:'Invalid worker operation'});
});
