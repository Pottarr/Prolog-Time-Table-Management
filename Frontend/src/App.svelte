<script>
  import { API_BASE } from './config.js';
  import FloorPlan from './lib/FloorPlan.svelte';
  import RoomTimetable from './lib/RoomTimetable.svelte';
  import ScheduleEditor from './lib/ScheduleEditor.svelte';
  import { ROOMS as FLOOR_ROOMS, rowsToCsv } from './lib/schedule.js';

  const PERIODS_PER_WEEK = 14; // 7 days × morning/afternoon
  const SHOWN_MOVED = 2; // moved classes listed in the case strip before "+N more"

  let csvFile = $state(null);
  let configFile = $state(null);
  // The CSV as editable rows (from /api/csv/rows); the editor changes
  // these and every scheduler run sends them back as a CSV.
  let rows = $state(null);
  let editorOpen = $state(false);
  let justUploaded = $state(false);
  let editorError = $state('');
  let maxCases = $state(10);

  let status = $state('idle'); // idle | loading | error | done
  let errorMessage = $state('');
  // The scheduler's answer (/api/schedule/cases): ranked cases, best first,
  // plus the config they were made with so the PDF always matches.
  let result = $state(null);
  let resultConfig = $state(null);
  let selectedRank = $state(1);
  let selectedRoom = $state(null);
  let pdfStatus = $state('idle'); // idle | loading | error
  let pdfError = $state('');

  const cases = $derived(result?.cases ?? []);
  const current = $derived(cases.find((c) => c.rank === selectedRank) ?? cases[0] ?? null);
  const classes = $derived(current?.classes ?? []);
  // Tab groups: OK, then by how many classes didn't get what they asked for.
  const caseGroups = $derived(
    cases.reduce((groups, c) => {
      const label = c.errors === 0 ? 'OK' : `${c.errors} unsatisfied`;
      const last = groups.at(-1);
      if (last?.label === label) last.cases.push(c);
      else groups.push({ label, bad: c.errors > 0, cases: [c] });
      return groups;
    }, []),
  );
  const uncapped = $derived(Number(maxCases) <= 0);
  // Classes the case moved off what they asked for: row index -> message.
  const moved = $derived(new Map(current?.unsatisfied.map((u) => [u.row, u.message]) ?? []));
  const movedRooms = $derived(new Set([...moved.keys()].map((i) => classes[i].room)));

  const rooms = $derived(result?.rooms ?? FLOOR_ROOMS);
  const capacity = $derived(result && selectedRoom ? result.capacities[selectedRoom] : null);
  const roomCount = $derived(selectedRoom ? classes.filter((c) => c.room === selectedRoom).length : 0);
  const fileBase = $derived(
    result ? `classroom-schedule-${result.academic_year}-s${result.semester}-case${current?.rank ?? 1}` : '',
  );
  const canRun = $derived(Boolean(rows && configFile));

  async function errorFromResponse(response) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    return new Error(detail ?? `Request failed with status ${response.status}`);
  }

  const messageOf = (err) => (err instanceof Error ? err.message : String(err));

  // A new CSV: read it into rows and open the editor straight away.
  async function chooseCsv(file) {
    if (!file) return;
    csvFile = file;
    const formData = new FormData();
    formData.append('csv_file', file);
    try {
      const response = await fetch(`${API_BASE}/api/csv/rows`, { method: 'POST', body: formData });
      if (!response.ok) throw await errorFromResponse(response);
      rows = (await response.json()).rows;
      editorError = '';
      justUploaded = true;
      editorOpen = true;
    } catch (err) {
      rows = null;
      status = 'error';
      errorMessage = messageOf(err);
    }
  }

  // 0 or less = no cap (every case, no time limit).
  function clampCases() {
    const n = Math.round(Number(maxCases));
    maxCases = Number.isFinite(n) ? Math.max(0, n) : 10;
  }

  async function runScheduler({ fromEditor = false } = {}) {
    if (!canRun) return;
    clampCases();
    status = 'loading';
    errorMessage = '';
    editorError = '';

    const formData = new FormData();
    formData.append('csv_file', new Blob([rowsToCsv(rows)], { type: 'text/csv' }), csvFile?.name ?? 'schedule.csv');
    formData.append('config_file', configFile);
    formData.append('max_cases', String(maxCases));

    try {
      const response = await fetch(`${API_BASE}/api/schedule/cases`, { method: 'POST', body: formData });
      if (!response.ok) throw await errorFromResponse(response);
      result = await response.json();
      resultConfig = configFile;
      pdfStatus = 'idle';
      pdfError = '';
      selectCase(1);
      status = 'done';
      editorOpen = false;
      justUploaded = false;
    } catch (err) {
      if (fromEditor) {
        editorError = messageOf(err);
        // Keep whatever was on screen before this run.
        status = result ? 'done' : 'idle';
      } else {
        status = 'error';
        errorMessage = messageOf(err);
      }
    }
  }

  function saveEdits(edited) {
    rows = edited;
    if (configFile) runScheduler({ fromEditor: true });
    else {
      editorOpen = false;
      justUploaded = false;
    }
  }

  function selectCase(rank) {
    selectedRank = rank;
    if (pdfStatus === 'error') pdfStatus = 'idle'; // an old case's PDF error
    const shown = cases.find((c) => c.rank === rank)?.classes ?? [];
    // Keep the room the user was looking at; otherwise open on the
    // busiest room so the page never starts with an empty week.
    if (!selectedRoom || !result.rooms.includes(selectedRoom)) {
      const counts = shown.reduce((acc, c) => acc.set(c.room, (acc.get(c.room) ?? 0) + 1), new Map());
      selectedRoom = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? result.rooms[0];
    }
  }

  function selectRoom(room) {
    if (result) selectedRoom = room;
  }

  function saveFile(blob, name) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadCsv() {
    saveFile(new Blob([current.csv], { type: 'text/csv' }), `${fileBase}.csv`);
  }

  async function downloadPdf() {
    pdfStatus = 'loading';
    pdfError = '';
    const formData = new FormData();
    formData.append('csv_file', new Blob([current.csv], { type: 'text/csv' }), 'schedule.csv');
    formData.append('config_file', resultConfig);
    try {
      const response = await fetch(`${API_BASE}/api/schedule/pdf`, { method: 'POST', body: formData });
      if (!response.ok) throw await errorFromResponse(response);
      saveFile(await response.blob(), `${fileBase}.pdf`);
      pdfStatus = 'idle';
    } catch (err) {
      pdfStatus = 'error';
      pdfError = messageOf(err);
    }
  }
</script>

<div class="app">
  <!-- Left rail: inputs, the floor plan -->
  <aside class="rail">
    <div class="brand">
      <div class="logo" aria-hidden="true"><span>8F</span></div>
      <div class="lbl">
        ECC timetable
        <span class="dim">
          {result ? `Semester ${result.semester} · ${result.academic_year}` : '8th floor · 801 – 810'}
        </span>
      </div>
    </div>

    <div class="inputs">
      <div class="step-head">
        <span class="lbl"><span class="n">1</span> Files</span>
        <details class="help">
          <summary class="lbl">Format</summary>
          <div class="pop">
            <p class="lbl">Schedule CSV</p>
            <pre>room,day,start,span,title,prof,students
ECC-804,Mon,9,3,Software Design,Dr. Veera,35
NULL,NULL,13,3,Algorithms,Dr. Visit,100</pre>
            <p>
              <code>day</code> is Mon – Sun · <code>start</code> is 9 (morning) or 13 (afternoon) ·
              <code>span</code> is always 3 · <code>students</code> can't exceed the room's seats. Leave
              <code>room</code>, <code>day</code> or <code>start</code> blank (or <code>NULL</code>) and Prolog
              picks it. The editor opens as soon as you choose a CSV.
            </p>

            <p class="lbl">Config JSON</p>
            <pre>{`{
  "semester": 1,
  "academic_year": 2026,
  "rooms": {
    "ECC-801": 50, "ECC-802": 50, "ECC-803": 50,
    "ECC-804": 50, "ECC-805": 20, "ECC-806": 0,
    "ECC-807": 50, "ECC-808": 100, "ECC-809": 100,
    "ECC-810": 50
  }
}`}</pre>
            <p>Seats for all ten rooms; <code>0</code> = not used for lectures (806 is the co-working space).</p>

            <p class="lbl">Cases</p>
            <p>
              The scheduler returns the first <em>Cases</em> timetables (<code>0</code> = no cap: every case, however
              long it takes). A room, day or start in the CSV is what that class asks for; rooms and professors
              are never double-booked. If every class can get what it asked for, only those (OK) cases are shown.
              Otherwise you get <em>unsatisfied</em> ones — some classes moved to a free spot — fewest moved
              classes first.
            </p>
          </div>
        </details>
      </div>
      <label class="file" class:set={csvFile}>
        <input
          type="file"
          accept=".csv,text/csv"
          onchange={(e) => {
            chooseCsv(e.target.files?.[0] ?? null);
            e.target.value = '';
          }}
        />
        <span class="name">{csvFile?.name ?? 'Choose schedule CSV'}</span>
        <span class="act lbl">{csvFile ? 'Change' : 'Browse'}</span>
      </label>
      <label class="file" class:set={configFile}>
        <input type="file" accept=".json,application/json" onchange={(e) => (configFile = e.target.files?.[0] ?? null)} />
        <span class="name">{configFile?.name ?? 'Choose config JSON'}</span>
        <span class="act lbl">{configFile ? 'Change' : 'Browse'}</span>
      </label>

      <div class="step-head">
        <span class="lbl"><span class="n">2</span> Schedule</span>
      </div>
      <label class="cap-row">
        <span class="lbl">Cases to return <span class="dim">{uncapped ? 'no cap — every case' : '0 = no cap'}</span></span>
        <input class="num" type="number" min="0" bind:value={maxCases} onchange={clampCases} />
      </label>
      <div class="load-row">
        <button class="btn ghost" type="button" disabled={!rows} onclick={() => ((justUploaded = false), (editorOpen = true))}>
          Edit CSV
        </button>
        <button class="btn" type="button" disabled={!canRun || status === 'loading'} onclick={() => runScheduler()}>
          {status === 'loading' ? 'Scheduling…' : 'Run scheduler'}
        </button>
      </div>
    </div>

    <div class="plan">
      <FloorPlan
        {classes}
        capacities={result?.capacities ?? null}
        selectedRoom={result ? selectedRoom : null}
        flaggedRooms={movedRooms}
        onselect={selectRoom}
      />
    </div>
  </aside>

  <!-- Main: the selected room's week in the selected case -->
  <main class="main">
    {#if result && current && selectedRoom}
      <header class="room-head">
        <h1 class="big">{selectedRoom.slice(4)}</h1>
        <div class="facts">
          <div class="lbl">ECC · {capacity === 0 ? 'Co-working space' : 'Classroom'}</div>
          <div class="seats">{capacity === 0 ? 'Not used for lectures' : `${capacity} seats`}</div>
          {#if capacity !== 0}
            <div class="dim">
              {roomCount} class{roomCount === 1 ? '' : 'es'} · {Math.round((roomCount / PERIODS_PER_WEEK) * 100)}% of
              periods
            </div>
          {/if}
        </div>
        <div class="readout">
          <div><b>{current.rank}<span class="of"> / {cases.length}</span></b><small>Rank</small></div>
          <div><b class:err={current.status !== 'ok'}>{current.score}%</b><small>Satisfied</small></div>
          <div><b class:err={current.errors}>{current.errors}</b><small>Unsatisfied</small></div>
        </div>
      </header>
      {#if current.status !== 'ok'}
        <div class="casebar" title={current.unsatisfied.map((u) => u.message).join('\n')}>
          <span class="tag">Case {current.rank} · {current.errors} unsatisfied</span>
          <ul>
            {#each current.unsatisfied.slice(0, SHOWN_MOVED) as u (u.row)}<li>{u.message}</li>{/each}
          </ul>
          {#if current.unsatisfied.length > SHOWN_MOVED}
            <span class="more">+{current.unsatisfied.length - SHOWN_MOVED} more</span>
          {/if}
        </div>
      {/if}
      <div class="sect">
        <span class="lbl">
          Weekly timetable — {selectedRoom}
          <span class="dim"> · case {current.rank}, scheduled by Prolog</span>
        </span>
        <span class="exports">
          <span class="lbl"><span class="n">3</span> Export</span>
          <button class="btn ghost small" type="button" onclick={downloadCsv} title="Download case {current.rank} as a CSV">Case {current.rank} CSV</button>
          <button class="btn small" type="button" onclick={downloadPdf} disabled={pdfStatus === 'loading'}>
            {pdfStatus === 'loading' ? 'Rendering…' : `Case ${current.rank} PDF`}
          </button>
        </span>
      </div>
      {#if pdfStatus === 'error'}
        <p class="error small">{pdfError}</p>
      {/if}
      <div class="week">
        <RoomTimetable room={selectedRoom} {capacity} {classes} flagged={moved} />
      </div>
    {:else}
      <div class="empty">
        <h1 class="big">8F</h1>
        {#if status === 'loading'}
          <p>Prolog is placing every flexible class…</p>
          {#if uncapped}<p class="dim">No cap — searching for every case. This can take a long time.</p>{/if}
        {:else if status === 'error'}
          <p class="lbl">Couldn't load the schedule</p>
          <p class="error">{errorMessage}</p>
        {:else if rows && !configFile}
          <p>Now choose the config JSON, then run the scheduler.</p>
          <p class="dim">Your CSV edits are kept — open them again with Edit CSV.</p>
        {:else}
          <p>Choose a schedule CSV and a config JSON. The CSV opens in the editor; saving runs the scheduler.</p>
          <p class="dim">Then pick a case from the tabs on the right and a room on the floor plan.</p>
        {/if}
      </div>
    {/if}
  </main>

  <!-- Right edge: ranked case tabs (scrolls when there are many) -->
  <nav class="cases" aria-label="Cases">
    <span class="cases-label">Cases</span>
    <span class="cases-count" title={result && !result.complete ? 'The time limit stopped the search' : ''}>
      {result ? `${cases.length} found` : '—'}{result && !result.complete ? ' · timed out' : ''}
    </span>
    <div class="case-list">
      {#each caseGroups as { label, bad, cases: group } (label)}
        <span class="grp" class:bad>{label}</span>
        {#each group as c (c.rank)}
            <button
              type="button"
              class="ct"
              class:u={bad}
              class:selected={c.rank === current?.rank}
              aria-pressed={c.rank === current?.rank}
              title="Case {c.rank}: {c.score}% of classes satisfied{c.errors ? `, ${c.errors} moved` : ''}"
              onclick={() => selectCase(c.rank)}
            >
              <b>{c.rank}</b>
              <small>{c.score}%</small>
              <span class="bar"><i style="width: {c.score}%"></i></span>
            </button>
        {/each}
      {/each}
    </div>
  </nav>
</div>

{#if editorOpen && rows}
  <ScheduleEditor
    {rows}
    fileName={csvFile?.name}
    {justUploaded}
    {canRun}
    busy={status === 'loading'}
    error={editorError}
    bind:maxCases
    onsave={saveEdits}
    oncancel={() => ((editorOpen = false), (justUploaded = false), (editorError = ''))}
  />
{/if}

<style>
  /* One screen, no page scroll on laptops/desktops: the app fills the
     window, and the floor plan and timetable stretch or shrink to fit. */
  /* Edge to edge: the app is the whole page, no frame around it. */
  .app {
    height: 100%;
    min-height: 600px;
    display: grid;
    grid-template-columns: clamp(300px, 26vw, 380px) minmax(0, 1fr) 76px;
    overflow: hidden;
    background: var(--cream);
  }

  .app > * {
    min-height: 0;
  }

  .dim {
    color: var(--sub);
  }

  .lbl .dim {
    display: block;
  }

  .step-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
    border-bottom: 1px solid var(--ink);
    padding-bottom: 4px;
  }

  .n {
    font: 600 16px var(--serif);
    letter-spacing: 0;
    margin-right: 4px;
  }

  .error {
    color: var(--error);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .error.small {
    margin: 6px 0 0;
    font-size: 13px;
    max-height: 4.5em;
    overflow: auto;
  }

  /* ---- rail ---- */
  .rail {
    background: var(--tan);
    padding: 22px 22px 18px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .brand {
    gap: 22px;
  }

  .brand > .lbl {
    font-size: 15px;
  }

  .logo {
    width: 48px;
    height: 48px;
    flex: none;
    margin: 6px 0 6px 10px;
    border: 1.5px solid var(--ink);
    transform: rotate(45deg);
    display: grid;
    place-items: center;
  }

  .logo span {
    transform: rotate(-45deg);
    font: 600 20px var(--serif);
  }

  .inputs {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .inputs .step-head + .file,
  .inputs .step-head + .cap-row {
    margin-top: 2px;
  }

  .inputs .step-head:not(:first-child) {
    margin-top: 6px;
  }

  .file {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 7px 10px;
    border: 1px dashed var(--hair);
    cursor: pointer;
  }

  .file.set {
    border-style: solid;
    border-color: var(--ink);
  }

  .file:hover,
  .file:focus-within {
    background: var(--hover);
  }

  .file input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  .file .name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file:not(.set) .name {
    color: var(--sub);
  }

  .file .act {
    flex: none;
    font-size: 11px;
  }

  .help {
    position: relative;
  }

  .help summary {
    cursor: pointer;
    list-style: none;
    color: var(--sub);
  }

  .help summary::after {
    content: ' ?';
  }

  /* Opens over the page instead of pushing the rail taller. */
  .help .pop {
    position: absolute;
    z-index: 10;
    top: calc(100% + 8px);
    left: -12px;
    width: 340px;
    padding: 12px 14px;
    background: var(--cream);
    border: 1px solid var(--ink);
    box-shadow: 0 16px 30px -12px rgba(40, 40, 60, 0.4);
    font-size: 14px;
  }

  .help .pop {
    width: min(420px, calc(100vw - 40px));
    max-height: calc(100vh - 120px);
    overflow: auto;
  }

  .help .pop p {
    margin: 0 0 10px;
  }

  .help .pop p.lbl {
    margin-bottom: 4px;
    padding-bottom: 3px;
    border-bottom: 1px solid var(--ink);
  }

  .help pre {
    margin: 0 0 6px;
    padding: 8px 10px;
    background: var(--tan);
    font-size: 12px;
    line-height: 1.45;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .help code {
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  .load-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 4px;
  }

  .load-row .btn {
    min-width: 7.5em;
  }

  .load-row .btn .n {
    font-size: 14px;
  }

  .plan {
    flex: 1;
    min-height: 0;
  }

  .exports {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .btn.small {
    padding: 5px 10px;
    font-size: 12px;
  }

  /* ---- main ---- */
  .main {
    background: var(--cream);
    padding: clamp(18px, 3vh, 32px) clamp(20px, 3vw, 40px);
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .big {
    margin: 0;
    font: 800 clamp(64px, 13vh, 132px) / 0.88 var(--serif);
    letter-spacing: -0.02em;
  }

  .room-head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: end;
    gap: 28px;
    margin-bottom: clamp(10px, 2vh, 22px);
  }

  .facts {
    font: 300 clamp(17px, 2.2vh, 22px) / 1.3 var(--sans);
  }

  .readout {
    display: flex;
  }

  .readout > div {
    padding: 0 14px;
  }

  .readout > div + div {
    border-left: 1px solid var(--hair);
  }

  .readout b {
    display: block;
    font: 300 clamp(28px, 4.5vh, 42px) / 1 var(--sans);
  }

  .readout small {
    font: 500 11px var(--sans);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--sub);
  }

  .sect {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 6px 12px;
    border-bottom: 1px solid var(--ink);
    padding-bottom: 5px;
    margin-bottom: 6px;
  }

  .week {
    flex: 1;
    min-height: 0;
  }

  .empty {
    margin: auto;
    max-width: 30rem;
    text-align: center;
    font: 300 20px / 1.4 var(--sans);
  }

  .empty .big {
    color: var(--soft);
    margin-bottom: 18px;
  }

  .empty p {
    margin: 0 0 6px;
  }

  .empty .error {
    font: 400 16px / 1.45 var(--sans);
    text-align: left;
    max-height: 40vh;
    overflow: auto;
    padding: 10px 14px;
    border-left: 3px solid var(--error);
    background: rgba(155, 44, 44, 0.06);
  }

  /* ---- case tabs ---- */
  .cases {
    background: var(--cream);
    border-left: 1px solid var(--soft);
    display: flex;
    flex-direction: column;
    padding: 16px 0 10px;
  }

  .cases-label {
    align-self: center;
    font: 500 11px var(--sans);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--hair);
  }

  .cases-count {
    align-self: center;
    margin-bottom: 6px;
    font: 400 12px var(--sans);
    color: var(--sub);
  }

  /* The only part of the page that scrolls, and only with many cases. */
  .case-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    scrollbar-width: thin;
    scrollbar-color: var(--soft) transparent;
  }

  .grp {
    margin: 6px 6px 4px;
    padding-top: 6px;
    border-top: 1px solid var(--soft);
    text-align: center;
    font: 500 9px var(--sans);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--hair);
  }

  .grp.bad {
    color: var(--error);
  }

  .ct {
    position: relative;
    flex: none;
    min-height: 50px;
    margin-left: 8px;
    border: 0;
    border-radius: 26px 0 0 26px;
    background: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.15s;
  }

  .ct:hover {
    background: var(--hover);
  }

  .ct b {
    font: 600 19px/1 var(--serif);
  }

  .ct small {
    margin-top: 2px;
    font: 500 11px var(--sans);
    letter-spacing: 0.04em;
    color: var(--sub);
  }

  .ct .bar {
    position: relative;
    width: 30px;
    height: 2px;
    margin-top: 3px;
    background: var(--soft);
  }

  .ct .bar i {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--ink);
  }

  .ct.u .bar i {
    background: var(--error);
  }

  .ct.u::after {
    content: '';
    position: absolute;
    top: 9px;
    right: 12px;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--error);
  }

  .ct.selected {
    background: var(--ink);
    color: var(--cream);
  }

  .ct.selected small {
    color: var(--soft);
  }

  .ct.selected .bar {
    background: #555;
  }

  .ct.selected .bar i {
    background: var(--cream);
  }

  /* ---- step 2 + case readout ---- */
  .cap-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .cap-row .dim {
    display: block;
    font: 400 12px var(--sans);
    letter-spacing: 0.04em;
    text-transform: none;
  }

  .num {
    width: 64px;
    padding: 5px 8px;
    border: 1px solid var(--ink);
    background: var(--cream);
    font: 500 16px var(--sans);
    text-align: right;
  }

  .load-row .btn {
    flex: 1;
  }

  .readout .of {
    font-size: 0.5em;
    color: var(--sub);
  }

  .readout b.err {
    color: var(--error);
  }

  .casebar {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
    padding: 6px 12px;
    margin-bottom: clamp(6px, 1.4vh, 12px);
    border: 1px solid var(--error);
    background: rgba(155, 44, 44, 0.05);
    color: var(--error);
    font-size: 14px;
  }

  .casebar .tag {
    flex: none;
    padding: 2px 8px;
    background: var(--error);
    color: var(--cream);
    font: 500 11px var(--sans);
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .casebar ul {
    flex: 1;
    min-width: 0;
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    gap: 18px;
    overflow: hidden;
    white-space: nowrap;
  }

  .casebar li {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .casebar li::before {
    content: '✕ ';
    font-size: 11px;
  }

  .casebar .more {
    flex: none;
    font: 500 11px var(--sans);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  /* Short laptop screens: tighten the rail so the floor plan keeps its size. */
  @media (min-width: 900px) and (max-height: 780px) {
    .rail {
      padding: 14px 16px 12px;
      gap: 10px;
    }

    .logo {
      width: 40px;
      height: 40px;
      margin: 4px 0 4px 8px;
    }

    .logo span {
      font-size: 17px;
    }

    .inputs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }

    .inputs > .step-head,
    .cap-row,
    .load-row {
      grid-column: 1 / -1;
    }

    .file {
      padding: 5px 8px;
      font-size: 14px;
    }

    .file .act {
      display: none;
    }
  }

  /* Phones / narrow windows: stack and scroll. */
  @media (max-width: 899px) {
    .app {
      height: auto;
      min-height: 100%;
      grid-template-columns: 1fr;
    }

    .app {
      overflow: visible;
    }

    .cases {
      order: -1;
      flex-direction: row;
      align-items: center;
      border-left: 0;
      padding: 8px;
    }

    .cases-label,
    .cases-count,
    .grp {
      display: none;
    }

    .case-list {
      flex-direction: row;
      overflow: auto hidden;
      gap: 4px;
    }

    .ct {
      width: 56px;
      min-height: 48px;
      margin: 0;
      border-radius: 24px;
    }

    .casebar ul {
      flex-direction: column;
      gap: 2px;
    }

    .plan {
      height: 70vh;
      flex: none;
    }

    .room-head {
      grid-template-columns: auto 1fr;
    }

    .readout {
      grid-column: 1 / -1;
    }
  }
</style>
