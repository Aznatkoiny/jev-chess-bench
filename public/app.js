(() => {
  'use strict';
  const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const PIECES = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟', K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟' };
  const PIECE_NAMES = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' };
  const $ = (id) => document.getElementById(id);
  const state = { runs: [], runId: null, gameIndex: 0, ply: 0, flipped: false, followLive: true, playing: null, fetching: false, worker: null };
  const run = () => state.runs.find((item) => item.id === state.runId);
  const game = () => run()?.games?.[state.gameIndex];
  const moves = () => game()?.moves || [];
  const finite = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  const num = (value, digits = 0) => finite(value) ? Number(value).toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
  const percent = (value) => finite(value) ? `${(Number(value) * 100).toFixed(1)}%` : '—';
  const latency = (value) => finite(value) ? Number(value) < 1000 ? `${num(value)} ms` : `${num(Number(value) / 1000, 2)} s` : '—';
  const money = (value) => finite(value) ? `$${Number(value).toFixed(4)}` : 'Unavailable';
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const titleCase = (value) => String(value || 'unknown').replace(/[_-]/g, ' ').replace(/^./, (character) => character.toUpperCase());
  const kindName = (kind) => ({ tournament: 'Tournament', smoke: 'Gateway smoke', content: 'Content recording · unrated', synthetic: 'Synthetic validation', validation: 'Synthetic validation' }[kind] || titleCase(kind));
  const isSynthetic = (item) => ['synthetic', 'validation', 'deterministic'].includes(item?.kind);
  const shortDate = (value) => { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); };
  const text = (id, value) => { $(id).textContent = value; };

  function stopPlayback() {
    if (state.playing) clearInterval(state.playing);
    state.playing = null;
    $('play-button').innerHTML = '<span aria-hidden="true">▶</span> Play';
    $('play-button').setAttribute('aria-label', 'Play replay');
  }

  function selectRun(id) {
    stopPlayback();
    state.runId = id;
    state.gameIndex = 0;
    state.followLive = true;
    state.ply = moves().length;
    render();
  }

  function selectGame(index, focus = false) {
    stopPlayback();
    state.gameIndex = index;
    state.followLive = true;
    state.ply = moves().length;
    render();
    if (focus) { $('match-viewer').scrollIntoView({ behavior: 'smooth', block: 'start' }); $('match-viewer').focus({ preventScroll: true }); }
  }

  function seek(ply, follow = false) {
    stopPlayback();
    state.followLive = follow;
    state.ply = Math.max(0, Math.min(moves().length, ply));
    renderGame();
  }

  function renderRuns() {
    const list = $('run-list');
    if (!state.runs.length) {
      list.innerHTML = '<p class="empty-copy">No runs yet. Once a benchmark starts, its games and results will appear here.</p>';
      return;
    }
    list.innerHTML = state.runs.map((item) => {
      const summary = item.summary || {};
      const record = [summary.wins, summary.draws, summary.losses].every(finite) ? `${num(summary.wins)} W · ${num(summary.draws)} D · ${num(summary.losses)} L` : `${item.games?.length || 0} recorded games`;
      return `<button class="run-item ${item.id === state.runId ? 'selected' : ''}" data-run="${escape(item.id)}" aria-current="${item.id === state.runId ? 'true' : 'false'}"><span class="run-item-top"><span class="run-item-name">${escape(kindName(item.kind))}</span></span><span class="run-item-date">${escape(shortDate(item.created_at))}</span><span class="run-item-bottom"><span>${escape(titleCase(item.status))}</span><span class="run-item-record">${escape(record)}</span></span></button>`;
    }).join('');
  }

  function boardPosition(fen) {
    const ranks = String(fen || START_FEN).split(' ')[0].split('/');
    const cells = [];
    ranks.forEach((rank, row) => {
      let file = 0;
      for (const character of rank) {
        if (/^[1-8]$/.test(character)) {
          for (let blank = 0; blank < Number(character); blank++) cells.push({ square: `${'abcdefgh'[file++]}${8 - row}`, piece: '' });
        } else if (PIECES[character]) cells.push({ square: `${'abcdefgh'[file++]}${8 - row}`, piece: character });
      }
    });
    return cells.length === 64 ? cells : boardPosition(START_FEN);
  }

  function renderBoard() {
    const currentGame = game();
    const currentMove = state.ply ? moves()[state.ply - 1] : null;
    const fen = currentMove?.fen || currentGame?.initial_fen || START_FEN;
    const cells = boardPosition(fen);
    if (state.flipped) cells.reverse();
    const lastSquares = currentMove?.uci ? [currentMove.uci.slice(0, 2), currentMove.uci.slice(2, 4)] : [];
    $('board').innerHTML = cells.map((cell, index) => {
      const color = cell.piece && cell.piece === cell.piece.toUpperCase() ? 'white' : 'black';
      const description = cell.piece ? `${color} ${PIECE_NAMES[cell.piece.toLowerCase()]}` : 'empty';
      const dark = ('abcdefgh'.indexOf(cell.square[0]) + Number(cell.square[1])) % 2 === 0;
      return `<span class="square ${dark ? 'dark' : ''} ${lastSquares.includes(cell.square) ? 'last-move' : ''}" title="${escape(`${cell.square}: ${description}`)}">${index % 8 === 0 ? `<span class="coordinate rank-coordinate" aria-hidden="true">${cell.square[1]}</span>` : ''}${index >= 56 ? `<span class="coordinate file-coordinate" aria-hidden="true">${cell.square[0]}</span>` : ''}${cell.piece ? `<span class="piece ${color}" aria-hidden="true">${PIECES[cell.piece]}</span>` : ''}</span>`;
    }).join('');
    $('board').setAttribute('aria-label', currentGame ? `Position ${state.ply} of ${moves().length} plies. ${currentMove ? `Last move ${currentMove.san || currentMove.uci}. ` : ''}FEN: ${fen}` : 'Chessboard in its initial position. No game selected.');
    const jevWhite = currentGame?.jev_color === 'white' || currentGame?.jev_color === 'w';
    const bottomColor = state.flipped ? 'black' : 'white';
    const topColor = state.flipped ? 'white' : 'black';
    const opponent = run()?.config?.opponent;
    const opponentName = typeof opponent === 'string' ? opponent : opponent?.name || opponent?.engine || run()?.config?.opponent_name || 'Chess opponent';
    const model = run()?.config?.model_id || run()?.config?.model || run()?.config?.jev_model || 'Vercel AI Gateway';
    const activeColor = String(fen).split(' ')[1] === 'b' ? 'black' : 'white';
    for (const [location, color] of [['top', topColor], ['bottom', bottomColor]]) {
      const isJev = currentGame ? (color === 'white') === jevWhite : location === 'bottom';
      text(`${location}-player`, isJev ? 'Jev' : opponentName);
      text(`${location}-detail`, currentGame ? `${titleCase(color)} pieces · ${isJev ? model : 'Open-source opponent'}` : isJev ? 'Inference through Vercel AI Gateway' : 'Waiting for a match');
      text(`${location}-avatar`, color === 'white' ? '♔' : '♚');
      $(`${location}-turn`).hidden = !currentGame || (state.ply === moves().length && currentGame.result && currentGame.result !== '*') || activeColor !== color;
    }
  }

  function renderMoves() {
    const recordedMoves = moves();
    const initial = String(game()?.initial_fen || START_FEN).split(' ');
    const startsBlack = initial[1] === 'b';
    const firstNumber = Number(initial[5]) || 1;
    const rows = [];
    recordedMoves.forEach((move, index) => {
      const adjusted = index + (startsBlack ? 1 : 0);
      const row = Math.floor(adjusted / 2);
      rows[row] ||= { number: firstNumber + row, white: '', black: '' };
      const selected = state.ply === index + 1;
      rows[row][adjusted % 2 === 0 ? 'white' : 'black'] = `<button class="move-button ${selected ? 'active' : ''}" data-ply="${index + 1}" aria-pressed="${selected}" title="${escape(move.uci || '')}">${escape(move.san || move.uci || '?')}</button>`;
    });
    const list = $('move-list');
    const oldScroll = list.scrollTop;
    list.innerHTML = rows.length ? rows.map((row) => `<div class="move-row"><span class="move-number">${row.number}.</span><span>${row.white}</span><span>${row.black}</span></div>`).join('') : '<p class="empty-copy">No moves recorded in this game yet.</p>';
    list.scrollTop = oldScroll;
    const active = list.querySelector('.active');
    if (active) {
      const offset = active.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
      if (offset < list.scrollTop || offset + active.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = Math.max(0, offset - list.clientHeight / 2);
    }
    const selected = state.ply ? recordedMoves[state.ply - 1] : null;
    text('move-detail', selected ? `${selected.player || 'Player'} selected ${selected.uci || selected.san}. Recorded move latency: ${latency(selected.latency_ms)}.` : 'Starting position. Select a move to inspect its recorded latency.');
    text('move-count', `${recordedMoves.length} ${recordedMoves.length === 1 ? 'ply' : 'plies'}`);
  }

  function renderGame() {
    const currentRun = run();
    const currentGame = game();
    const recordedMoves = moves();
    state.ply = Math.min(state.ply, recordedMoves.length);
    text('match-title', currentGame ? currentGame.opening_name || `Game ${state.gameIndex + 1}` : currentRun ? 'Waiting for the first game.' : 'The next move starts here.');
    text('run-kind', currentRun ? kindName(currentRun.kind) : 'No run selected');
    $('run-kind').className = `tag ${currentRun ? escape(isSynthetic(currentRun) ? 'synthetic' : currentRun.kind) : ''}`;
    text('run-status', currentRun ? titleCase(currentRun.status) : '');
    const selector = $('game-select');
    selector.disabled = !currentRun?.games?.length;
    selector.innerHTML = currentRun?.games?.length ? currentRun.games.map((item, index) => `<option value="${index}" ${index === state.gameIndex ? 'selected' : ''}>${index + 1}. ${escape(item.opening_name || 'Starting position')} · Jev ${escape(titleCase(item.jev_color))}</option>`).join('') : '<option>No recorded games</option>';
    text('game-result', currentGame?.result && currentGame.result !== '*' ? currentGame.result : currentGame ? titleCase(currentGame.status || 'Pending') : '—');
    const failures = currentGame?.failures;
    const failureCount = Array.isArray(failures) ? failures.length : finite(failures) ? Number(failures) : 0;
    $('game-context').innerHTML = currentGame ? `<p><strong>${escape(titleCase(currentGame.status))}</strong>${currentGame.termination ? ` · ${escape(titleCase(currentGame.termination))}` : ''}</p><p>Jev plays <strong>${escape(titleCase(currentGame.jev_color))}</strong>. ${escape(currentGame.opening_name || 'Recorded starting position')}.</p>${failureCount ? `<p class="failure-copy">${failureCount} recorded ${failureCount === 1 ? 'failure' : 'failures'}. Inspect run JSON for details.</p>` : ''}` : '<p>Select a run to inspect its games. Jev receives the position and every legal move on each turn.</p>';
    renderBoard();
    renderMoves();
    text('move-position', `Ply ${state.ply} / ${recordedMoves.length}`);
    text('position-description', !currentGame ? 'The board will show a game as soon as one is recorded.' : state.ply === 0 ? 'Starting position' : `${recordedMoves[state.ply - 1]?.san || recordedMoves[state.ply - 1]?.uci || ''} · ${state.ply === recordedMoves.length ? 'Latest recorded position' : 'Replay position'}`);
    $('follow-live').checked = state.followLive;
    $('first-button').disabled = $('previous-button').disabled = !state.ply;
    $('next-button').disabled = $('last-button').disabled = state.ply >= recordedMoves.length;
    $('play-button').disabled = !recordedMoves.length;
    const pgn = $('pgn-download');
    pgn.setAttribute('aria-disabled', String(!currentGame));
    if (currentGame) { pgn.href = `/api/pgn?id=${encodeURIComponent(currentRun.id)}&game=${state.gameIndex}`; pgn.download = `jev-${currentRun.id}-game-${state.gameIndex + 1}.pgn`; }
    else pgn.removeAttribute('href');
    const raw = $('raw-download');
    raw.setAttribute('aria-disabled', String(!currentGame));
    if (currentGame) { raw.href = `/api/artifact?id=${encodeURIComponent(currentRun.id)}&game=${state.gameIndex}`; raw.download = `jev-${currentRun.id}-game-${state.gameIndex + 1}.json`; }
    else raw.removeAttribute('href');
    $('json-download').disabled = !currentRun;
  }

  function renderRating(currentRun) {
    const history = (currentRun?.rating_history || []).filter((point) => finite(point.rating));
    const chart = $('rating-chart');
    text('rating-sample', history.length ? `${num(currentRun?.summary?.sample_size ?? history.at(-1)?.n ?? history.length)} rated games` : 'No rated games');
    if (!history.length || isSynthetic(currentRun)) {
      chart.innerHTML = `<p class="empty-copy">${isSynthetic(currentRun) ? 'Synthetic games do not measure Jev’s playing strength.' : 'A rating history will appear after measured games are completed.'}</p>`;
      return;
    }
    const width = 600, height = 195, left = 42, right = 16, top = 17, bottom = 28;
    const values = history.map((point) => Number(point.rating));
    const low = Math.floor((Math.min(...values) - 25) / 25) * 25;
    const high = Math.ceil((Math.max(...values) + 25) / 25) * 25;
    const x = (index) => left + (history.length === 1 ? .5 : index / (history.length - 1)) * (width - left - right);
    const y = (value) => top + (high - value) / (high - low) * (height - top - bottom);
    const line = history.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.rating).toFixed(1)}`).join(' ');
    const ticks = [low, (low + high) / 2, high];
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Provisional pool Elo: ${history.map((point, index) => `game ${point.n ?? index + 1}, rating ${Math.round(point.rating)}`).join('; ')}"><title>Provisional Elo history for this run</title>${ticks.map((value) => `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#384239" stroke-width="1"/><text x="${left - 8}" y="${y(value) + 4}" fill="#a3afa5" font-size="10" text-anchor="end">${Math.round(value)}</text>`).join('')}<path d="${line}" fill="none" stroke="#a9c5a2" stroke-width="2.5" stroke-linejoin="round"/>${history.map((point, index) => `<circle cx="${x(index)}" cy="${y(point.rating)}" r="${index === history.length - 1 ? 4 : 2.5}" fill="#a9c5a2"><title>Game ${point.n ?? index + 1}: ${Math.round(point.rating)}</title></circle>`).join('')}<text x="${left}" y="${height - 7}" fill="#a3afa5" font-size="10">Game ${history[0].n ?? 1}</text><text x="${width - right}" y="${height - 7}" fill="#a3afa5" font-size="10" text-anchor="end">${history.length > 1 ? `Game ${history.at(-1).n ?? history.length}` : 'One rated game'}</text></svg>`;
  }

  function renderResults() {
    const currentRun = run();
    const summary = currentRun?.summary || {};
    const synthetic = isSynthetic(currentRun);
    text('results-context', currentRun ? `${kindName(currentRun.kind)} · ${shortDate(currentRun.created_at)} · ${currentRun.id.slice(0, 8)}` : 'Select a recorded run to view measured outcomes.');
    $('validation-note').hidden = !currentRun?.validation_note;
    text('validation-note', currentRun?.validation_note || '');
    text('results-type', currentRun ? synthetic ? 'Synthetic • not Jev results' : currentRun.kind === 'smoke' ? 'Integration smoke run' : currentRun.kind === 'content' ? 'Content recording • unrated' : 'Measured tournament' : 'No results yet');
    $('results-type').className = `tag ${synthetic ? 'synthetic' : currentRun?.kind || ''}`;
    text('score-label', synthetic ? 'Harness score rate' : 'Jev score rate');
    text('score-value', percent(summary.score_rate));
    text('score-detail', synthetic ? 'Synthetic harness validation only' : '(Wins + ½ draws) / completed');
    text('record-value', `${num(summary.wins)} / ${num(summary.draws)} / ${num(summary.losses)}`);
    text('completion-detail', finite(summary.completed) ? `${num(summary.completed)} completed · ${num(summary.failed ?? 0)} failed · ${num(summary.censored ?? 0)} censored` : 'No completed games');
    text('elo-value', synthetic ? 'Unrated' : num(summary.elo));
    const interval = summary.uncertainty;
    text('elo-detail', synthetic ? 'Not measured Jev performance' : currentRun?.kind === 'content' ? 'Unrated content games; rating retained from earlier tournaments' : finite(summary.elo) ? Number(summary.sample_size) === 0 ? 'Initialized · 0 rated tournament games' : `${num(summary.sample_size)} rated tournament games in this pool` : 'Rating requires measured games');
    text('performance-interval', synthetic ? 'Synthetic runs do not support a Jev performance estimate.' : interval ? `Run performance: 95% paired interval ${interval.low === null ? '−∞' : num(interval.low)} to ${interval.high === null ? '+∞' : num(interval.high)}; ${num(interval.pairs)} complete color pairs. ${Number(interval.pairs) === 0 ? 'Insufficient complete pairs to constrain playing strength.' : 'Conditional on the fixed opening suite.'}` : 'The run’s performance interval will appear when results are available.');
    text('latency-value', latency(summary.median_latency_ms));
    text('latency-detail', synthetic ? 'Synthetic timing only' : 'Successful Jev moves, including retries');
    text('quality-completion', `${num(summary.completed)} / ${num(summary.failed)} / ${num(summary.censored)}`);
    text('quality-failures', `${num(summary.infrastructure_failures)} / ${num(summary.operational_forfeits)}`);
    text('quality-invalid', percent(summary.invalid_response_rate));
    text('quality-p95', latency(summary.p95_latency_ms));
    text('quality-tokens', `${num(summary.input_tokens)} / ${num(summary.output_tokens)}`);
    const observedCost = summary.observed_cost_usd ?? summary.actual_cost_usd;
    text('quality-cost-label', finite(observedCost) ? 'Observed API cost' : 'Estimated API cost');
    text('quality-cost', money(finite(observedCost) ? observedCost : summary.estimated_cost_usd));
    text('cost-coverage', finite(observedCost) ? `Observed cost covers ${num(summary.cost_observed_attempts)} of ${num(summary.jev_attempts)} Jev API attempts. Estimated total: ${money(summary.estimated_cost_usd)}.` : 'API cost is estimated from recorded token usage and the configured rate; it is not a billing statement.');
    text('quality-reserved', money(summary.reserved_cost_usd));
    text('run-config', currentRun ? JSON.stringify(currentRun.config || {}, null, 2) : 'No run selected.');
    renderRating(currentRun);
    const games = currentRun?.games || [];
    text('games-record-count', `${games.length} ${games.length === 1 ? 'game' : 'games'}`);
    $('games-table-body').innerHTML = games.length ? games.map((item, index) => `<tr class="${index === state.gameIndex ? 'selected' : ''}"><td>${index + 1}</td><td>${escape(item.opening_name || 'Recorded position')}</td><td>${escape(titleCase(item.jev_color))}</td><td>${escape(item.result || '*')}</td><td>${escape(titleCase(item.status))}</td><td>${escape(item.termination ? titleCase(item.termination) : '—')}</td><td><button class="text-button" data-game="${index}" aria-label="Replay game ${index + 1}">Watch game</button></td></tr>`).join('') : '<tr><td colspan="7" class="empty-table">No games have been recorded.</td></tr>';
  }

  function renderWorker() {
    const worker = state.worker;
    const timestamp = worker?.last_seen;
    const elapsed = timestamp ? Date.now() - new Date(timestamp).getTime() : Infinity;
    const online = Number.isFinite(elapsed) && elapsed >= -60000 && elapsed < 120000;
    $('worker-status').parentElement.classList.toggle('online', online);
    text('worker-status', online ? 'Match worker connected. New moves refresh every 5 seconds.' : timestamp ? `Worker last seen ${shortDate(timestamp)}. Recorded games remain available.` : 'No active match worker reported. Recorded games remain available.');
  }

  function render() { renderRuns(); renderGame(); renderResults(); renderWorker(); }

  async function refresh() {
    if (state.fetching) return;
    state.fetching = true;
    $('refresh-button').disabled = true;
    try {
      const response = await fetch('/api/runs', { headers: { Accept: 'application/json' }, cache: 'no-store', signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error(`Run history is unavailable (HTTP ${response.status}).`);
      const data = await response.json();
      if (!Array.isArray(data.runs)) throw new Error('The server returned an unreadable run history.');
      state.runs = data.runs;
      state.worker = data.worker || null;
      if (!state.runs.some((item) => item.id === state.runId)) {
        const requested = new URLSearchParams(location.search).get('run');
        state.runId = state.runs.find(item => item.id === requested)?.id
          || state.runs.find(item => item.status === 'running')?.id
          || state.runs.find(item => item.kind === 'tournament')?.id
          || state.runs[0]?.id || null;
        state.gameIndex = 0;
      }
      state.gameIndex = Math.min(state.gameIndex, Math.max(0, (run()?.games?.length || 1) - 1));
      if (state.followLive) state.ply = moves().length;
      text('connection-status', 'Records connected');
      $('connection-status').prepend(Object.assign(document.createElement('span'), { className: 'status-dot' }));
      $('connection-status').className = 'connection-status connected';
      $('notice').hidden = true;
      text('last-updated', `Updated ${new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`);
      render();
    } catch (error) {
      text('connection-status', 'Connection interrupted');
      $('connection-status').prepend(Object.assign(document.createElement('span'), { className: 'status-dot' }));
      $('connection-status').className = 'connection-status failed';
      $('notice').hidden = false;
      $('notice').className = 'notice error';
      text('notice', `${error.name === 'TimeoutError' ? 'The run history request timed out.' : error.message} Retrying automatically. Any previously loaded records remain visible.`);
      if (!state.runs.length) $('run-list').innerHTML = '<p class="empty-copy">Run history could not be loaded. Use refresh to retry.</p>';
    } finally { state.fetching = false; $('refresh-button').disabled = false; }
  }

  $('run-list').addEventListener('click', (event) => { const button = event.target.closest('[data-run]'); if (button) selectRun(button.dataset.run); });
  $('game-select').addEventListener('change', (event) => selectGame(Number(event.target.value)));
  $('move-list').addEventListener('click', (event) => { const button = event.target.closest('[data-ply]'); if (button) seek(Number(button.dataset.ply)); });
  $('games-table-body').addEventListener('click', (event) => { const button = event.target.closest('[data-game]'); if (button) selectGame(Number(button.dataset.game), true); });
  $('first-button').addEventListener('click', () => seek(0));
  $('previous-button').addEventListener('click', () => seek(state.ply - 1));
  $('next-button').addEventListener('click', () => seek(state.ply + 1));
  $('last-button').addEventListener('click', () => seek(moves().length, true));
  $('flip-button').addEventListener('click', () => { state.flipped = !state.flipped; renderBoard(); });
  $('refresh-button').addEventListener('click', refresh);
  $('follow-live').addEventListener('change', (event) => { state.followLive = event.target.checked; if (state.followLive) { stopPlayback(); state.ply = moves().length; } renderGame(); });
  $('play-button').addEventListener('click', () => {
    if (state.playing) { stopPlayback(); return; }
    state.followLive = false;
    if (state.ply >= moves().length) state.ply = 0;
    renderGame();
    $('play-button').innerHTML = '<span aria-hidden="true">Ⅱ</span> Pause';
    $('play-button').setAttribute('aria-label', 'Pause replay');
    state.playing = setInterval(() => { state.ply = Math.min(state.ply + 1, moves().length); renderGame(); if (state.ply >= moves().length) stopPlayback(); }, 900);
  });
  $('match-viewer').addEventListener('keydown', (event) => {
    if (['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(event.target.tagName)) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); seek(state.ply - 1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); seek(state.ply + 1); }
    if (event.key === 'Home') { event.preventDefault(); seek(0); }
    if (event.key === 'End') { event.preventDefault(); seek(moves().length, true); }
  });
  $('json-download').addEventListener('click', () => {
    const currentRun = run();
    if (!currentRun) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(currentRun, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `jev-chess-${currentRun.id}.json`; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('run-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    let token = $('admin-token').value.trim();
    if (!token) { text('run-form-status', 'Enter the operator token to queue a benchmark.'); return; }
    $('admin-token').value = '';
    $('start-run-button').disabled = true;
    text('run-form-status', 'Requesting a benchmark run…');
    try {
      const response = await fetch('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ kind: $('run-kind-select').value }), signal: AbortSignal.timeout(30000) });
      token = '';
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'The operator token was not accepted.' : data.error || `The run could not be queued (HTTP ${response.status}).`);
      text('run-form-status', 'Benchmark queued. Its recorded games will appear in run history.');
      await refresh();
      const id = data.id || data.run?.id || data.run_id;
      if (id && state.runs.some((item) => item.id === id)) selectRun(id);
    } catch (error) { text('run-form-status', error.name === 'TimeoutError' ? 'The request timed out. Refresh run history before retrying to avoid a duplicate run.' : error.message); }
    finally { token = ''; $('start-run-button').disabled = false; }
  });
  renderBoard();
  renderGame();
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
