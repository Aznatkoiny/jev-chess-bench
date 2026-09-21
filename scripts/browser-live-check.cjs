// Explicit paid verification: queues exactly one fixed two-game smoke run.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
  assert(process.env.BENCH_OPERATOR_TOKEN_FILE,'Provide a private token file to authorize this paid smoke check');
  const token=fs.readFileSync(process.env.BENCH_OPERATOR_TOKEN_FILE,'utf8').trim();
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const url=process.env.BENCH_BASE_URL||'https://jev-chess-bench.vercel.app';
  await page.goto(url,{waitUntil:'networkidle'});
  await page.locator('#execution-panel summary').click();
  await page.getByLabel('Operator token').fill(token);
  await page.getByLabel('Run type').selectOption('smoke');
  const queued=page.waitForResponse(r=>r.url().endsWith('/api/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Queue benchmark',exact:true}).click();
  const response=await queued;assert.equal(response.status(),202);const job=await response.json();
  assert.equal(job.config.game_count,2);assert.equal(job.config.spending_ceiling_usd,.6);
  await page.waitForFunction(()=>document.querySelector('#admin-token').value==='');
  assert.equal(await page.evaluate(t=>JSON.stringify({...localStorage,...sessionStorage}).includes(t),token),false);
  console.log(JSON.stringify({queued_run:job.id,kind:job.kind,game_count:2,reservation_ceiling_usd:.6}));
  await page.waitForFunction(id=>document.querySelector(`[data-run="${id}"][aria-current="true"]`) && /^Ply [1-9]/.test(document.querySelector('#move-position').innerText),job.id,{timeout:45000});
  const frames=[];
  for(let i=0;i<3;i++){
    frames.push({at:new Date().toISOString(),position:await page.locator('#move-position').innerText(),board:await page.locator('#board').getAttribute('aria-label')});
    if(i<2)await page.waitForTimeout(5500);
  }
  assert(new Set(frames.map(f=>f.board)).size>1,'Actual live board must advance across polling refreshes');
  assert.equal(errors.length,0);
  const out=process.env.BENCH_QA_OUTPUT||'output/live-browser';fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:out+'/live.png',fullPage:true});
  const report={verified:true,run_id:job.id,frames,live_board_advanced:true,operator_token_cleared:true,browser_storage_empty_of_token:true,page_errors:errors};
  fs.writeFileSync(out+'/report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
