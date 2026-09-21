import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
const port=Number(process.env.PORT||4328);
http.createServer(async(req,res)=>{
  try {
    const pathname=new URL(req.url,'http://localhost').pathname;
    if(pathname.startsWith('/api/')) {
      if(!/^\/api\/(runs|worker|artifact|pgn)$/.test(pathname)) {res.statusCode=404;return res.end();}
      const {default:handler}=await import(`..${pathname}.mjs`); return await handler(req,res);
    }
    const file=pathname==='/'?'index.html':pathname.slice(1);
    if(!/^[a-zA-Z0-9_.-]+$/.test(file)) {res.statusCode=404;return res.end();}
    res.setHeader('Content-Type',{'html':'text/html','js':'text/javascript','css':'text/css'}[path.extname(file).slice(1)]||'application/octet-stream');
    res.end(await readFile(new URL(`../public/${file}`,import.meta.url)));
  } catch {res.statusCode=404;res.end('Not found');}
}).listen(port,'127.0.0.1',()=>console.log(`Chess Lab: http://127.0.0.1:${port}`));
