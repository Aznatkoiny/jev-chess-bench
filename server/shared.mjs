import { list, get, put } from '@vercel/blob';
import { timingSafeEqual, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

export const config = JSON.parse(await readFile(new URL('../config.json', import.meta.url), 'utf8'));
export const validId = id => typeof id === 'string' && /^[a-f0-9-]{36}$/.test(id);
export function authorized(req, name) {
  const key = process.env[name];
  const supplied = req.headers.authorization;
  if (!key || key.length < 32 || typeof supplied !== 'string') return false;
  const a = Buffer.from(supplied), b = Buffer.from(`Bearer ${key}`);
  return a.length === b.length && timingSafeEqual(a, b);
}
export function send(res, code, body) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Type', 'application/json');
  res.statusCode = code;
  res.end(JSON.stringify(body));
}
export function guard(handler) {
  return async (req, res) => { try { await handler(req,res); } catch (e) {
    // Never return provider or credential-bearing error objects.
    send(res, e.statusCode || 503, {error: e.publicMessage || 'Storage unavailable. Retry safely; saved games remain on the worker.'});
  }};
}
export async function body(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  let raw = typeof req.body === 'string' ? req.body : '';
  if (!raw) for await (const chunk of req) { raw += chunk; if (Buffer.byteLength(raw)>3_500_000) throw {statusCode:413,publicMessage:'Request too large'}; }
  try { return JSON.parse(raw); } catch { throw {statusCode:400,publicMessage:'Invalid JSON'}; }
}
export async function blobs(prefix) {
  const all=[]; let cursor;
  do { const page=await list({prefix,limit:1000,cursor}); all.push(...page.blobs); cursor=page.hasMore?page.cursor:undefined; } while(cursor);
  return all;
}
export async function read(path) {
  const r=await get(path,{access:'private'});
  if (!r) return null;
  return JSON.parse(await new Response(r.stream).text());
}
export async function write(path,data,overwrite=false) {
  return put(path,JSON.stringify(data),{access:'private',addRandomSuffix:false,allowOverwrite:overwrite,contentType:'application/json'});
}
export async function latest(id) {
  const files=await blobs(`snapshots/${id}/`);
  files.sort((a,b)=>b.pathname.localeCompare(a.pathname));
  return files.length ? read(files[0].url) : read(`jobs/${id}.json`);
}
export function makeJob(kind,id=randomUUID()) {
  if (!['smoke','tournament','content'].includes(kind)) throw {statusCode:400,publicMessage:'Choose smoke, tournament, or content'};
  return {id,created_at:new Date().toISOString(),status:'queued',kind,config:{...config,...config[kind]},games:[],summary:null,rating_history:[]};
}
