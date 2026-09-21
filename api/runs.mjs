import { authorized,send,guard,body,blobs,read,write,latest,validId,makeJob } from '../server/shared.mjs';
export default guard(async(req,res)=>{
  if(req.method==='GET') {
    const id=new URL(req.url,'http://local').searchParams.get('id');
    if(id) { if(!validId(id)) return send(res,400,{error:'Invalid run ID'}); const r=await latest(id); return send(res,r?200:404,r||{error:'Run not found'}); }
    const jobs=await blobs('jobs/'); jobs.sort((a,b)=>new Date(b.uploadedAt)-new Date(a.uploadedAt));
    const runs=await Promise.all(jobs.slice(0,50).map(j=>latest(j.pathname.split('/')[1].replace('.json',''))));
    const worker=await read('worker/health.json');
    return send(res,200,{runs:runs.filter(Boolean),worker,history_limit:50});
  }
  if(req.method!=='POST') return send(res,405,{error:'Method not allowed'});
  if(!authorized(req,'ADMIN_TOKEN')) return send(res,401,{error:'A valid operator token is required. Public viewing is free.'});
  const data=await body(req);
  if(Object.keys(data).some(k=>k!=='kind')) return send(res,400,{error:'Only a fixed benchmark kind is accepted'});
  const existing=await blobs('jobs/');
  if(existing.length>=100) return send(res,429,{error:'Project run quota reached'});
  const job=makeJob(data.kind);
  await write(`jobs/${job.id}.json`,job);
  return send(res,202,job);
});
