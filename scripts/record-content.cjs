/* Real browser viewport recording. One explicit paid content run, or an existing run. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');

(async()=>{
  const base=process.env.BENCH_BASE_URL||'https://jev-chess-bench.vercel.app';
  assert(base.startsWith('https://')||base.startsWith('http://127.0.0.1:'));
  const out=path.resolve(process.env.BENCH_VIDEO_DIR||'output/video');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
  const context=await browser.newContext({viewport:{width:1280,height:720},deviceScaleFactor:1,recordVideo:{dir:path.join(out,'raw'),size:{width:1280,height:720}}});
  const page=await context.newPage(),video=page.video(),captureStart=Date.now();
  const errors=[],timeline=[];let job,finalState,endedCleanly=false;
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(base+'/record.html?autoplay=1&pace=750',{waitUntil:'networkidle'});
    await page.waitForFunction(()=>typeof window.setRecordingRun==='function');
    if(process.env.BENCH_EXISTING_RUN_ID){
      const response=await fetch(base+'/api/runs?id='+encodeURIComponent(process.env.BENCH_EXISTING_RUN_ID),{redirect:'error'});
      assert(response.ok);job=await response.json();
    }else{
      assert(process.env.BENCH_OPERATOR_TOKEN_FILE,'A private operator token file is required to queue a paid run');
      let token=fs.readFileSync(process.env.BENCH_OPERATOR_TOKEN_FILE,'utf8').trim();
      const response=await fetch(base+'/api/runs',{method:'POST',redirect:'error',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({kind:'content'})});
      token='';assert.equal(response.status,202,'Content run was not queued; no automatic retry');job=await response.json();
      assert.equal(job.config.game_count,9);assert.equal(job.config.spending_ceiling_usd,2.5);
    }
    fs.writeFileSync(path.join(out,'run-plan.json'),JSON.stringify(job,null,2));
    console.log(JSON.stringify({event:'recording_started',run_id:job.id,planned_games:job.config.game_count,ceiling_usd:job.config.spending_ceiling_usd}));
    await page.evaluate(id=>window.setRecordingRun(id),job.id);
    let previous='',lastLog=0;
    while(Date.now()-captureStart<45*60*1000){
      const state=await page.evaluate(()=>{const {frames,...compact}=window.recordingState;return {...compact,renderedFrames:frames.length};});
      const key=JSON.stringify([state.gameIndex,state.ply,state.phase]);
      if(key!==previous){timeline.push({seconds:(Date.now()-captureStart)/1000,...state});previous=key;}
      if(Date.now()-lastLog>25000||state.phase==='game_end'||state.phase==='finished'){
        if(Date.now()-lastLog>1000){console.log(JSON.stringify({event:'progress',seconds:Math.round((Date.now()-captureStart)/1000),...state}));lastLog=Date.now();}
      }
      fs.writeFileSync(path.join(out,'capture-timeline.json'),JSON.stringify({run_id:job.id,capture_start:new Date(captureStart).toISOString(),timeline,errors},null,2));
      if(state.phase==='finished'){
        finalState=await page.evaluate(()=>window.recordingState);
        assert.equal(finalState.displayedGames,job.config.game_count,'Not all planned games were displayed');
        const response=await fetch(base+'/api/runs?id='+encodeURIComponent(job.id),{redirect:'error'});
        assert(response.ok);const saved=await response.json();
        assert.equal(saved.status,'completed','Run did not finish');
        assert.equal(saved.games.length,job.config.game_count);
        assert.equal(finalState.displayedPlies,saved.games.reduce((n,g)=>n+g.moves.length,0));
        for(const game of saved.games){
          const frames=finalState.frames.filter(f=>f.gameIndex===game.index&&f.phase==='playing');
          assert.deepEqual(frames.map(f=>f.fen),game.moves.map(m=>m.fen),'Every real move must appear exactly once');
        }
        fs.writeFileSync(path.join(out,'completed-run.json'),JSON.stringify(saved,null,2));
        endedCleanly=true;await page.waitForTimeout(3000);break;
      }
      await page.waitForTimeout(150);
    }
    assert(endedCleanly,'Recording exceeded its time limit');
    assert.equal(errors.length,0,'Browser had runtime errors');
    await page.screenshot({path:path.join(out,'final-screen.png')});
  }finally{
    await context.close();await video.saveAs(path.join(out,'jev-nine-games-capture.webm'));await browser.close();
    fs.writeFileSync(path.join(out,'capture-verification.json'),JSON.stringify({run_id:job?.id,ended_cleanly:endedCleanly,final_state:finalState,page_errors:errors,viewport:{width:1280,height:720},presentation_ms_per_ply:750,recording_type:'actual browser viewport; inference unaltered; display paced'},null,2));
  }
  console.log(JSON.stringify({event:'recording_saved',run_id:job.id,path:path.join(out,'jev-nine-games-capture.webm'),games:finalState.displayedGames,plies:finalState.displayedPlies}));
})().catch(e=>{console.error('Recording stopped: '+e.message);process.exitCode=1});
