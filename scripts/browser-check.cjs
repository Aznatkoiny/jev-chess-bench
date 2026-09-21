#!/usr/bin/env node
/**
 * Verify real, anonymous hosted records. No fixtures or paid API calls.
 * PLAYWRIGHT_MODULE=/path/to/node_modules/playwright \
 * BROWSER_CHANNEL=chrome BENCH_BASE_URL=https://jev-chess-bench.vercel.app \
 * BENCH_RUN_ID=<optional-run-id> node scripts/browser-check.cjs
 * Optional: BENCH_QA_OUTPUT=/path/to/output-directory.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const baseURL = (process.env.BENCH_BASE_URL || 'https://jev-chess-bench.vercel.app').replace(/\/$/, '');
const output = process.env.BENCH_QA_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'jev-browser-check-'));
const totalPlies = run => (run.games || []).reduce((sum, game) => sum + (game.moves || []).length, 0);

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    assert.equal(await page.title(), 'Jev Chess Lab');
    const initialResponse = await context.request.get(`${baseURL}/api/runs`);
    assert(initialResponse.ok(), 'anonymous run history responds');
    const data = await initialResponse.json();
    let run = process.env.BENCH_RUN_ID
      ? data.runs.find(item => item.id === process.env.BENCH_RUN_ID)
      : data.runs.find(item => item.kind === 'tournament') || data.runs.find(item => item.kind === 'smoke');
    assert(run, 'a real smoke or tournament run is available');
    assert(['smoke', 'tournament'].includes(run.kind), 'this check uses measured records only');
    const runId = run.id;
    await page.locator(`[data-run="${runId}"]`).click();
    assert.equal(await page.locator('.square').count(), 64);
    assert.equal(await page.locator('#notice').isVisible(), false);
    const liveGame = run.games.find(game => game.status === 'running' && game.moves.length)
      || [...run.games].reverse().find(game => game.moves.length);
    assert(liveGame, 'the real run contains recorded moves');
    await page.locator('#game-select').selectOption(String(liveGame.index));
    const polls = [{ at: new Date().toISOString(), status: run.status, totalPlies: totalPlies(run), renderedPosition: await page.locator('#move-position').innerText() }];
    // Observe two actual automatic refreshes, normally five seconds apart.
    for (let index = 0; index < 2; index++) {
      const response = await page.waitForResponse(response => {
        const request = response.request();
        return new URL(response.url()).pathname === '/api/runs' && request.method() === 'GET' && response.ok();
      }, { timeout: 18000 });
      const refreshed = await response.json();
      run = refreshed.runs.find(item => item.id === runId);
      assert(run, 'the run remains in history after polling');
      await page.waitForTimeout(100);
      polls.push({ at: new Date().toISOString(), status: run.status, totalPlies: totalPlies(run), renderedPosition: await page.locator('#move-position').innerText() });
    }
    const advanced = polls.at(-1).totalPlies > polls[0].totalPlies;
    const renderedAdvance = polls.at(-1).renderedPosition !== polls[0].renderedPosition;
    // Finished runs are valid checks too. An unchanged live snapshot is reported
    // honestly instead of assuming that a model always responds within 10 sec.
    const recorded = run.games.find(game => game.status === 'completed' && game.moves.length >= 3)
      || run.games.find(game => game.moves.length >= 3);
    assert(recorded, 'a game has enough recorded moves for replay checks');
    await page.locator('#game-select').selectOption(String(recorded.index));
    await page.getByRole('button', { name: 'Go to starting position' }).click();
    assert((await page.locator('#board').getAttribute('aria-label')).includes(recorded.initial_fen));
    await page.getByRole('button', { name: 'Next move', exact: true }).click();
    assert((await page.locator('#board').getAttribute('aria-label')).includes(recorded.moves[0].fen));
    assert((await page.locator('#move-detail').innerText()).includes(recorded.moves[0].uci));
    await page.locator('[data-ply="3"]').click();
    assert((await page.locator('#board').getAttribute('aria-label')).includes(recorded.moves[2].fen));
    await page.getByRole('button', { name: 'Previous move', exact: true }).click();
    assert((await page.locator('#board').getAttribute('aria-label')).includes(recorded.moves[1].fen));
    await page.locator('#match-viewer').focus();
    await page.keyboard.press('Home');
    assert((await page.locator('#move-position').innerText()).startsWith('Ply 0 /'));
    await page.getByRole('button', { name: 'Play replay', exact: true }).click();
    await page.waitForTimeout(1000);
    await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
    assert((await page.locator('#move-position').innerText()).startsWith('Ply 1 /'));
    await page.getByLabel('Follow live').check();
    await page.getByRole('button', { name: 'Flip board' }).click();
    assert((await page.locator('.square').first().getAttribute('title')).startsWith('h1:'));
    await page.getByRole('button', { name: 'Flip board' }).click();

    const downloads = {};
    for (const [name, selector] of [['pgn', '#pgn-download'], ['raw', '#raw-download']]) {
      const href = await page.locator(selector).getAttribute('href');
      assert(href, `${name} download link is present`);
      const response = await context.request.get(new URL(href, baseURL).href);
      downloads[`${name}Status`] = response.status();
      if (recorded.status === 'completed') {
        assert(response.ok(), `completed game ${name} artifact is persisted`);
        if (name === 'pgn') assert((await response.text()).includes(recorded.moves[0].san));
        else {
          const archive = await response.json();
          assert.equal(archive.id, recorded.id);
          assert.equal(archive.moves.length, recorded.moves.length);
          assert(Array.isArray(archive.attempts));
          downloads.rawAttemptCount = archive.attempts.length;
        }
      }
    }
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Run JSON', exact: true }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), `jev-chess-${runId}.json`);
    const downloadedRun = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
    assert.equal(downloadedRun.id, runId);

    await page.reload({ waitUntil: 'networkidle' });
    await page.locator(`[data-run="${runId}"]`).click();
    await page.locator('#game-select').selectOption(String(recorded.index));
    assert((await page.locator('#move-list').innerText()).includes(recorded.moves[0].san));
    const rating = {
      displayed: await page.locator('#elo-value').innerText(),
      sample: await page.locator('#elo-detail').innerText(),
      performanceInterval: await page.locator('#performance-interval').innerText(),
      plotted: await page.locator('#rating-chart svg').count() === 1,
    };
    if (run.kind === 'tournament' && run.summary.sample_size > 0) assert(rating.plotted, 'rated games produce an Elo plot');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 1440);
    await page.locator('h1').click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
    assert.deepEqual(errors, [], 'no uncaught page errors');
    const report = {
      baseURL, runId, kind: run.kind, status: run.status, checkedAt: new Date().toISOString(),
      fixtures: false, paidExecutionRequested: false, polls, liveDataAdvanced: advanced, liveBoardAdvanced: renderedAdvance,
      replayedGame: { index: recorded.index, status: recorded.status, plies: recorded.moves.length, result: recorded.result },
      downloads, rating, persistedAfterReload: true, mobileWidth: 390, horizontalOverflow: false, errors,
      screenshots: { desktop: path.join(output, 'desktop.png'), mobile: path.join(output, 'mobile.png') },
    };
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
