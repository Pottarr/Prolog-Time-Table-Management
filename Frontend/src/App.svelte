<script>
  import { API_BASE } from './config.js';
  import FloorPlan from './lib/FloorPlan.svelte';
  import RoomTimetable from './lib/RoomTimetable.svelte';

  // The floor's rooms, so the plan and room tabs can be drawn before any
  // schedule is loaded (the gateway sends the same list back with it).
  const FLOOR_ROOMS = Array.from({ length: 10 }, (_, i) => `ECC-8${String(i + 1).padStart(2, '0')}`);
  const PERIODS_PER_WEEK = 14; // 7 days × morning/afternoon

  let csvFile = $state(null);
  let configFile = $state(null);
  let autoSchedule = $state(false);
  let status = $state('idle'); // idle | loading | error | done
  let errorMessage = $state('');
  // The schedule on screen (from /api/schedule/parse, or solved by Prolog
  // via /api/schedule/auto) plus the complete CSV + config it came from, so
  // the PDF download matches what's on screen even if the form is changed
  // afterwards. For auto-scheduling that CSV is Prolog's completed one.
  let schedule = $state(null);
  let submitted = $state(null);
  let completedCsvUrl = $state('');
  let selectedRoom = $state(null);
  let pdfStatus = $state('idle'); // idle | loading | error
  let pdfError = $state('');

  const rooms = $derived(schedule?.rooms ?? FLOOR_ROOMS);
  const capacity = $derived(schedule && selectedRoom ? schedule.capacities[selectedRoom] : null);
  const roomCount = $derived(
    schedule && selectedRoom ? schedule.classes.filter((c) => c.room === selectedRoom).length : 0,
  );
  const fileBase = $derived(
    schedule ? `classroom-schedule-${schedule.academic_year}-s${schedule.semester}` : '',
  );

  function resetResult() {
    status = 'loading';
    errorMessage = '';
    schedule = null;
    if (completedCsvUrl) URL.revokeObjectURL(completedCsvUrl);
    completedCsvUrl = '';
    submitted = null;
    pdfStatus = 'idle';
    pdfError = '';
  }

  function buildFormData({ file, config }) {
    const formData = new FormData();
    formData.append('csv_file', file);
    formData.append('config_file', config);
    return formData;
  }

  async function errorFromResponse(response) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : null;
    return new Error(detail ?? `Request failed with status ${response.status}`);
  }

  async function downloadPdf() {
    pdfStatus = 'loading';
    pdfError = '';
    try {
      const response = await fetch(`${API_BASE}/api/schedule/pdf`, {
        method: 'POST',
        body: buildFormData(submitted),
      });
      if (!response.ok) throw await errorFromResponse(response);

      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `${fileBase}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      pdfStatus = 'idle';
    } catch (err) {
      pdfStatus = 'error';
      pdfError = err instanceof Error ? err.message : String(err);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!csvFile || !configFile) {
      status = 'error';
      errorMessage = 'Choose both a schedule CSV and a config JSON file first.';
      return;
    }

    resetResult();

    const inputs = { file: csvFile, config: configFile };
    const endpoint = autoSchedule ? '/api/schedule/auto' : '/api/schedule/parse';

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        body: buildFormData(inputs),
      });

      if (!response.ok) throw await errorFromResponse(response);

      schedule = await response.json();
      if (schedule.csv) {
        const completed = new Blob([schedule.csv], { type: 'text/csv' });
        submitted = { file: completed, config: inputs.config };
        completedCsvUrl = URL.createObjectURL(completed);
      } else {
        submitted = inputs;
      }
      // Keep the room the user was looking at; otherwise open on the
      // busiest room so the page never starts with an empty week.
      if (!selectedRoom || !schedule.rooms.includes(selectedRoom)) {
        const counts = schedule.classes.reduce(
          (acc, c) => acc.set(c.room, (acc.get(c.room) ?? 0) + 1),
          new Map(),
        );
        selectedRoom = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? schedule.rooms[0];
      }
      status = 'done';
    } catch (err) {
      status = 'error';
      errorMessage = err instanceof Error ? err.message : String(err);
    }
  }

  function selectRoom(room) {
    if (schedule) selectedRoom = room;
  }
</script>

<div class="app">
  <!-- Left rail: inputs, the floor plan, exports -->
  <aside class="rail">
    <div class="brand">
      <div class="logo" aria-hidden="true"><span>8F</span></div>
      <div class="lbl">
        ECC timetable
        <span class="dim">
          {schedule ? `Semester ${schedule.semester} · ${schedule.academic_year}` : '8th floor · 801 – 810'}
        </span>
      </div>
    </div>

    <form class="inputs" onsubmit={handleSubmit}>
      <div class="step-head">
        <span class="lbl"><span class="n">1</span> Files</span>
        <details class="help">
          <summary class="lbl">Format</summary>
          <div class="pop">
            <p class="lbl">Schedule CSV</p>
            <pre>room,day,start,span,title,prof,students
ECC-804,Mon,9,3,Software Design,Dr. Veera,35
ECC-808,Mon,13,3,Discrete Mathematics,Dr. Visit,100</pre>
            <p>
              <code>day</code> is Mon – Sun · <code>start</code> is 9 (morning) or 13 (afternoon) ·
              <code>span</code> is always 3 · <code>students</code> can't exceed the room's seats.
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

            <p class="lbl">Auto-schedule</p>
            <pre>NULL,NULL,13,3,Algorithms,Dr. Veera,35
ECC-804,Mon,NULL,3,Databases,Dr. Suphamit,40</pre>
            <p>
              Leave <code>room</code>, <code>day</code> or <code>start</code> blank (or <code>NULL</code>)
              and Prolog fills them in. The first row means "any day, any room, starts 13:00"; the
              second "room 804 on Monday, any time".
            </p>
          </div>
        </details>
      </div>
      <label class="file" class:set={csvFile}>
        <input type="file" accept=".csv,text/csv" onchange={(e) => (csvFile = e.target.files?.[0] ?? null)} />
        <span class="name">{csvFile?.name ?? 'Choose schedule CSV'}</span>
        <span class="act lbl">{csvFile ? 'Change' : 'Browse'}</span>
      </label>
      <label class="file" class:set={configFile}>
        <input type="file" accept=".json,application/json" onchange={(e) => (configFile = e.target.files?.[0] ?? null)} />
        <span class="name">{configFile?.name ?? 'Choose config JSON'}</span>
        <span class="act lbl">{configFile ? 'Change' : 'Browse'}</span>
      </label>

      <div class="load-row">
        <label class="toggle" title="Leave room, day or start blank (or NULL) and Prolog fills them in">
          <input type="checkbox" bind:checked={autoSchedule} />
          <span class="track" aria-hidden="true"></span>
          Auto-schedule
        </label>
        <button class="btn" type="submit" disabled={status === 'loading'}>
          {#if status === 'loading'}
            {autoSchedule ? 'Scheduling…' : 'Loading…'}
          {:else}
            <span class="n">2</span> Load
          {/if}
        </button>
      </div>
    </form>

    <div class="plan">
      <FloorPlan
        classes={schedule?.classes ?? []}
        capacities={schedule?.capacities ?? null}
        selectedRoom={schedule ? selectedRoom : null}
        onselect={selectRoom}
      />
    </div>
  </aside>

  <!-- Main: the selected room's week -->
  <main class="main">
    {#if status === 'done' && schedule && selectedRoom}
      <header class="room-head">
        <h1 class="big">{selectedRoom.slice(4)}</h1>
        <div class="facts">
          <div class="lbl">ECC · {capacity === 0 ? 'Co-working space' : 'Classroom'}</div>
          <div class="seats">{capacity === 0 ? 'Not used for lectures' : `${capacity} seats`}</div>
          {#if capacity !== 0}
            <div class="dim">{roomCount} class{roomCount === 1 ? '' : 'es'} · {roomCount * 3} h / week</div>
          {/if}
        </div>
        <div class="readout">
          <div><b>{schedule.classes.length}</b><small>Classes on floor</small></div>
          <div>
            <b>{capacity === 0 ? '—' : `${Math.round((roomCount / PERIODS_PER_WEEK) * 100)}%`}</b>
            <small>Periods used</small>
          </div>
        </div>
      </header>
      <div class="sect">
        <span class="lbl">
          Weekly timetable — {selectedRoom}
          {#if completedCsvUrl}<span class="dim"> · scheduled by Prolog</span>{/if}
        </span>
        <span class="exports">
          <span class="lbl"><span class="n">3</span> Export</span>
          {#if completedCsvUrl}
            <a class="btn ghost small" href={completedCsvUrl} download="{fileBase}.csv">Completed CSV</a>
          {/if}
          <button class="btn small" type="button" onclick={downloadPdf} disabled={pdfStatus === 'loading'}>
            {pdfStatus === 'loading' ? 'Rendering…' : 'Summary PDF'}
          </button>
        </span>
      </div>
      {#if pdfStatus === 'error'}
        <p class="error small">{pdfError}</p>
      {/if}
      <div class="week">
        <RoomTimetable room={selectedRoom} {capacity} classes={schedule.classes} />
      </div>
    {:else}
      <div class="empty">
        <h1 class="big">8F</h1>
        {#if status === 'loading'}
          <p>{autoSchedule ? 'Prolog is placing every flexible class…' : 'Checking the schedule…'}</p>
        {:else if status === 'error'}
          <p class="lbl">Couldn't load the schedule</p>
          <p class="error">{errorMessage}</p>
        {:else}
          <p>Load a schedule CSV and a config JSON to see each room's week.</p>
          <p class="dim">Then pick a room on the floor plan or from the tabs on the right.</p>
        {/if}
      </div>
    {/if}
  </main>

  <!-- Right edge: room tabs -->
  <nav class="tabs" aria-label="Rooms">
    <span class="tabs-label" aria-hidden="true">Rooms</span>
    {#each rooms as room (room)}
      <button
        type="button"
        class:selected={room === selectedRoom && schedule}
        class:off={schedule?.capacities[room] === 0}
        disabled={!schedule}
        aria-pressed={room === selectedRoom}
        title={room}
        onclick={() => selectRoom(room)}
      >{room.slice(4)}</button>
    {/each}
  </nav>
</div>

<style>
  /* One screen, no page scroll on laptops/desktops: the app fills the
     window, and the floor plan and timetable stretch or shrink to fit. */
  /* Edge to edge: the app is the whole page, no frame around it. */
  .app {
    height: 100%;
    min-height: 600px;
    display: grid;
    grid-template-columns: clamp(300px, 26vw, 380px) minmax(0, 1fr) 64px;
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

  .inputs .step-head + .file {
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

  .toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
  }

  .toggle input {
    position: absolute;
    opacity: 0;
  }

  .track {
    position: relative;
    width: 36px;
    height: 20px;
    flex: none;
    border-radius: 10px;
    background: var(--soft);
    transition: background 0.15s;
  }

  .track::after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--cream);
    transition: transform 0.15s;
  }

  .toggle input:checked + .track {
    background: var(--ink);
  }

  .toggle input:checked + .track::after {
    transform: translateX(16px);
  }

  .toggle input:focus-visible + .track {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
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

  /* ---- room tabs ---- */
  .tabs {
    background: var(--cream);
    border-left: 1px solid var(--soft);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
    padding: 16px 0;
  }

  .tabs-label {
    align-self: center;
    margin-bottom: 10px;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font: 500 11px var(--sans);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--hair);
  }

  .tabs button {
    flex: 0 1 52px;
    min-height: 34px;
    margin-left: 8px;
    border: 0;
    border-radius: 26px 0 0 26px;
    background: none;
    font: 600 18px var(--serif);
    cursor: pointer;
    transition: background 0.15s;
  }

  .tabs button:hover:not(:disabled) {
    background: var(--hover);
  }

  .tabs button.off {
    color: var(--hair);
  }

  .tabs button.selected {
    background: var(--ink);
    color: var(--cream);
  }

  .tabs button:disabled {
    color: var(--soft);
    cursor: default;
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

    .tabs {
      order: -1;
      flex-direction: row;
      flex-wrap: wrap;
      justify-content: center;
      border-left: 0;
      padding: 8px;
    }

    .tabs-label {
      display: none;
    }

    .tabs button {
      flex: none;
      width: 52px;
      height: 40px;
      margin: 0;
      border-radius: 20px;
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
