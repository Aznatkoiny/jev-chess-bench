(() => {
  'use strict';
  const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const SYMBOLS = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };
  const RUN_END = new Set(['completed', 'stopped', 'failed', 'cancelled']);
  const GAME_END = new Set(['completed', 'censored', 'failed']);
  const params = new URLSearchParams(location.search);
  const pace = Math.max(200, Math.min(3000, Number(params.get('pace')) || 750));
  const $ = id => document.getElementById(id);
  const set = (id, value) => { $(id).textContent = value; };
  const human = value => String(value || '').replaceAll('_', ' ').replace(/^./, character => character.toUpperCase());
  const state = window.recordingState = { runId: null, gameIndex: 0, ply: 0, phase: 'waiting', displayedGames: 0, displayedPlies: 0, errors: [], frames: [], paceMs: pace, paused: false };
  let run = null, started = params.get('autoplay') === '1', deadline = 0, fetching = false, generation = 0, finalizing = false;
  let counts = { wins: 0, draws: 0, losses: 0, failed: 0, censored: 0 };
  const current = () => run?.games?.[state.gameIndex];
  const planned = () => Number(run?.config?.game_count) || 9;
  const terminal = () => RUN_END.has(run?.status);
  const gameEnded = game => GAME_END.has(game?.status) || (terminal() && game);
  const time = value => Number.isFinite(Number(value)) && value !== null ? Number(value) < 1000 ? `${Math.round(value)} ms` : `${(Number(value) / 1000).toFixed(2)} s` : '—';

  function resize() {
    const scale = Math.min(innerWidth / 1280, innerHeight / 720);
    $('stage').style.transform = `translateX(-50%) scale(${scale})`;
    $('stage').style.top = `${Math.max(0, (innerHeight - 720 * scale) / 2)}px`;
  }

  function board(fen, move) {
    const ranks = String(fen).split(' ')[0].split('/');
    const cells = [];
    for (let row = 0; row < 8; row++) {
      let file = 0;
      for (const item of ranks[row] || '') {
        if (/^[1-8]$/.test(item)) {
          for (let blank = 0; blank < Number(item); blank++) cells.push({ square: `${'abcdefgh'[file++]}${8 - row}`, piece: '' });
        } else if (SYMBOLS[item.toLowerCase()]) cells.push({ square: `${'abcdefgh'[file++]}${8 - row}`, piece: item });
      }
    }
    if (cells.length !== 64) throw new Error('Recorded position does not contain 64 squares.');
    const highlight = move?.uci ? [move.uci.slice(0, 2), move.uci.slice(2, 4)] : [];
    $('board').innerHTML = cells.map((cell, index) => {
      const dark = ('abcdefgh'.indexOf(cell.square[0]) + Number(cell.square[1])) % 2 === 0;
      const white = cell.piece === cell.piece.toUpperCase();
      return `<span class="square${dark ? ' dark' : ''}${highlight.includes(cell.square) ? ' last-move' : ''}" data-square="${cell.square}">${index % 8 === 0 ? `<span class="coordinate rank">${cell.square[1]}</span>` : ''}${index >= 56 ? `<span class="coordinate file">${cell.square[0]}</span>` : ''}${cell.piece ? `<span class="piece ${white ? 'white' : 'black'}">${SYMBOLS[cell.piece.toLowerCase()]}</span>` : ''}</span>`;
    }).join('');
    $('board').setAttribute('aria-label', `Game ${state.gameIndex + 1}, ply ${state.ply}. ${move?.san || 'Starting position'}. FEN: ${fen}`);
    state.frames.push({ gameIndex: state.gameIndex, ply: state.ply, phase: state.phase, fen, at: Date.now() });
  }

  function renderCapture() {
    set('capture-status', !state.runId ? 'READY TO CAPTURE' : `${terminal() ? 'RECORDED RUN' : 'LIVE CAPTURE'} · moves paced for viewing`);
    $('capture-dot').parentElement.classList.toggle('stopped', terminal());
    $('app-link').href = state.runId ? `/?run=${encodeURIComponent(state.runId)}` : '/';
    const opponent = run?.config?.opponent;
    if (opponent && typeof opponent === 'object') set('opponent-config', `Stockfish engine · Skill ${opponent.skill_level ?? '—'} · depth ${opponent.depth ?? '—'}`);
  }

  function renderPosition() {
    const game = current();
    const move = state.ply ? game?.moves?.[state.ply - 1] : null;
    const fen = move?.fen || game?.initial_fen || START;
    const jevWhite = game?.jev_color !== 'black';
    const active = String(fen).split(' ')[1] === 'b' ? 'black' : 'white';
    const end = state.phase === 'game_end' || state.phase === 'finished';
    board(fen, move);
    set('game-number', `Game ${state.gameIndex + 1} / ${planned()}`);
    set('side-label', game ? `Jev plays ${jevWhite ? 'white' : 'black'}` : 'Waiting to play');
    set('opening', game?.opening_name || 'Nine new games. Every move on screen.');
    set('black-player', jevWhite ? 'Stockfish 16' : 'Jev');
    set('white-player', jevWhite ? 'Jev' : 'Stockfish 16');
    set('black-state', game && !end && active === 'black' ? 'To move' : '');
    set('white-state', game && !end && active === 'white' ? 'To move' : '');
    set('move-player', move ? `${move.player === 'jev' ? 'Jev' : 'Stockfish 16'} played` : 'Starting position');
    set('move-number', `Ply ${state.ply}`);
    set('move-san', move?.san || move?.uci || '—');
    set('move-status', end ? human(game?.termination || game?.status) : move?.san?.includes('#') ? 'Checkmate' : move?.san?.includes('+') ? 'Check' : game ? `${active === (jevWhite ? 'white' : 'black') ? 'Jev' : 'Stockfish'} to move` : 'Ready');
    $('move-status').classList.toggle('ended', end || Boolean(move?.san?.includes('#')));
    const jevMoves = (game?.moves || []).slice(0, state.ply).filter(item => item.player === 'jev');
    set('jev-latency', time(jevMoves.at(-1)?.latency_ms ?? null));
    renderCapture();
  }

  function score() {
    for (const key of ['wins', 'draws', 'losses']) set(key, counts[key]);
    set('completed-label', `${state.displayedGames} ${state.displayedGames === 1 ? 'game' : 'games'} shown`);
    state.counts = { ...counts };
  }

  function message(value, error = false) {
    set('game-message', value);
    $('game-message').classList.toggle('error', error);
  }

  function intro() {
    state.phase = 'intro';
    state.ply = 0;
    deadline = performance.now() + 1000;
    renderPosition();
    message('Every recorded move plays in order.');
  }

  function commitGame() {
    const game = current();
    if (game.status === 'completed' && ['1-0', '0-1', '1/2-1/2'].includes(game.result)) {
      if (game.result === '1/2-1/2') counts.draws++;
      else if ((game.result === '1-0') === (game.jev_color === 'white')) counts.wins++;
      else counts.losses++;
    } else if (game.status === 'censored') counts.censored++;
    else counts.failed++;
    state.displayedGames++;
    state.phase = 'game_end';
    deadline = performance.now() + 2000;
    renderPosition();
    score();
    const outcome = game.result === '1/2-1/2' ? 'Draw' : game.status === 'completed' ? ((game.result === '1-0') === (game.jev_color === 'white') ? 'Jev wins' : 'Stockfish wins') : game.status === 'censored' ? 'Game reached its limit' : 'Game stopped';
    message(`${outcome} · ${human(game.termination || game.status)}.`, game.status === 'failed');
  }

  function finale() {
    if (finalizing) return;
    finalizing = true;
    state.phase = 'game_end';
    deadline = performance.now() + 4000;
    const allPlayed = state.displayedGames === planned();
    set('finale-title', allPlayed ? `${state.displayedGames} games. Every move recorded.` : `Run stopped after ${state.displayedGames} of ${planned()} games.`);
    set('finale-record', `${counts.wins} wins · ${counts.draws} draws · ${counts.losses} losses`);
    set('finale-detail', `${state.displayedPlies} moves shown${counts.failed ? ` · ${counts.failed} failed` : ''}${counts.censored ? ` · ${counts.censored} reached a limit` : ''}${!allPlayed ? ` · ${run?.stop_reason || human(run?.status)}` : ''}`);
    $('finale').hidden = false;
    state.stopReason = !allPlayed ? run?.stop_reason || run?.status : null;
  }

  function tick() {
    if (!started || state.paused || state.phase === 'finished' || !run || performance.now() < deadline) return;
    if (finalizing) { state.phase = 'finished'; return; }
    const game = current();
    if (!game) {
      if (terminal()) finale();
      else { state.phase = 'waiting'; message(state.displayedGames ? 'Waiting for the next game.' : 'Waiting for the first position.'); }
      return;
    }
    if (state.phase === 'waiting') { intro(); return; }
    if (state.phase === 'game_end') {
      if (state.displayedGames >= planned()) { finale(); return; }
      state.gameIndex++;
      state.ply = 0;
      state.phase = 'waiting';
      if (current()) intro();
      else if (terminal()) finale();
      return;
    }
    if (state.ply < (game.moves || []).length) {
      state.phase = 'playing';
      state.ply++;
      state.displayedPlies++;
      deadline = performance.now() + pace;
      renderPosition();
      message('Real model moves · paced for viewing.');
      return;
    }
    if (gameEnded(game)) commitGame();
    else { state.phase = 'playing'; message('Caught up. Waiting for the next recorded move.'); }
  }

  async function refresh() {
    if (fetching || !state.runId || state.phase === 'finished') return;
    fetching = true;
    const version = generation;
    try {
      const response = await fetch(`/api/runs?id=${encodeURIComponent(state.runId)}`, { cache: 'no-store', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error(`Run request returned HTTP ${response.status}.`);
      const next = await response.json();
      if (version !== generation) return;
      if (next.id !== state.runId || !Array.isArray(next.games)) throw new Error('Run data was not readable.');
      // Preserve already observed prefixes if an older publication arrives.
      next.games = next.games.map((game, index) => {
        const previous = run?.games?.[index];
        return previous && ((previous.moves || []).length > (game.moves || []).length || GAME_END.has(previous.status) && !GAME_END.has(game.status)) ? previous : game;
      });
      if (run && next.games.length < run.games.length) next.games = run.games;
      if (terminal() && !RUN_END.has(next.status)) next.status = run.status;
      run = next;
      state.serverStatus = run.status;
      state.availablePlies = run.games.reduce((total, game) => total + (game.moves || []).length, 0);
      state.plannedGames = planned();
      renderCapture();
      tick();
    } catch (error) {
      if (version !== generation) return;
      state.errors.push({ message: error.message, at: Date.now() });
      message('Connection interrupted. Retrying; no moves are skipped.', true);
    } finally { fetching = false; }
  }

  function start() {
    started = true;
    state.paused = false;
    $('controls').hidden = true;
    tick();
  }

  window.setRecordingRun = id => {
    if (!/^[a-f0-9-]{36}$/.test(String(id))) throw new Error('A valid run ID is required.');
    generation++;
    run = null;
    finalizing = false;
    deadline = 0;
    counts = { wins: 0, draws: 0, losses: 0, failed: 0, censored: 0 };
    Object.assign(state, { runId: id, gameIndex: 0, ply: 0, phase: 'waiting', displayedGames: 0, displayedPlies: 0, errors: [], frames: [], paused: false, stopReason: null });
    $('finale').hidden = true;
    const url = new URL(location.href);
    url.searchParams.set('run', id);
    history.replaceState(null, '', url);
    score();
    renderPosition();
    message('Waiting for the first position.');
    start();
    refresh();
  };
  $('start-button').addEventListener('click', start);
  document.addEventListener('keydown', event => {
    if (event.code !== 'Space' || event.target.closest('button, a, input')) return;
    event.preventDefault();
    if (!started) start();
    else { state.paused = !state.paused; message(state.paused ? 'Paused · press Space to continue.' : 'Real model moves · paced for viewing.'); }
  });
  addEventListener('resize', resize);
  resize();
  set('pace-label', `${(pace / 1000).toFixed(2).replace(/0$/, '')} s`);
  $('controls').hidden = started;
  board(START);
  score();
  if (params.get('run')) {
    const auto = started;
    window.setRecordingRun(params.get('run'));
    started = auto;
    $('controls').hidden = auto;
  }
  setInterval(refresh, 2000);
  setInterval(() => {
    try { tick(); }
    catch (error) { state.errors.push({ message: error.message, at: Date.now() }); state.paused = true; message('Playback stopped: recorded position is unreadable.', true); }
  }, 30);
})();
