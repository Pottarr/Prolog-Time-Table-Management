<script>
  import { API_BASE } from './config.js';
  import FloorPlan from './lib/FloorPlan.svelte';
  import RoomTimetable from './lib/RoomTimetable.svelte';

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

  function onFileChange(event) {
    csvFile = event.target.files?.[0] ?? null;
  }

  function onConfigChange(event) {
    configFile = event.target.files?.[0] ?? null;
  }

  function resetResult() {
    status = 'loading';
    errorMessage = '';
    schedule = null;
    if (completedCsvUrl) URL.revokeObjectURL(completedCsvUrl);
    completedCsvUrl = '';
    submitted = null;
    selectedRoom = null;
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
      link.download = `classroom-schedule-${schedule.academic_year}-s${schedule.semester}.pdf`;
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
      errorMessage = 'Please choose both a schedule CSV and a config JSON file.';
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
      // Open on the busiest room so the page never starts with an empty panel.
      const counts = schedule.classes.reduce(
        (acc, c) => acc.set(c.room, (acc.get(c.room) ?? 0) + 1),
        new Map(),
      );
      selectedRoom = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? schedule.rooms[0];
      status = 'done';
    } catch (err) {
      status = 'error';
      errorMessage = err instanceof Error ? err.message : String(err);
    }
  }
</script>

<main>
  <h1>Classroom Schedule Generator</h1>
  <p class="subtitle">
    ECC building, 8th floor (rooms ECC-801 – ECC-810). Upload a schedule CSV,
    then click a room on the floor plan to see its weekly timetable.
  </p>

  <form onsubmit={handleSubmit}>
    <label>
      Schedule CSV
      <input type="file" accept=".csv,text/csv" onchange={onFileChange} required />
    </label>

    <label>
      Config JSON
      <input type="file" accept=".json,application/json" onchange={onConfigChange} required />
    </label>
    <p class="hint">
      Semester, academic year, and the seat capacity of every room, e.g.
    </p>
    <pre class="hint-example">{`{
  "semester": 1,
  "academic_year": 2026,
  "rooms": { "ECC-801": 50, …, "ECC-806": 0, …, "ECC-810": 50 }
}`}</pre>

    <label class="checkbox-row">
      <input type="checkbox" bind:checked={autoSchedule} />
      Auto-scheduling (let Prolog pick day / time / room)
    </label>

    {#if autoSchedule}
      <p class="hint">
        Leave <code>day</code>, <code>start</code>, or <code>room</code> blank
        (or write <code>NULL</code>) for whatever the professor is flexible
        on. <code>span</code>, <code>title</code>, <code>prof</code>, and
        <code>students</code> are always required. Example rows:
      </p>
      <pre class="hint-example">NULL,NULL,13,3,Algorithms,Dr. Veera,35
ECC-804,Mon,NULL,3,Databases,Dr. Suphamit,40</pre>
      <p class="hint">
        The first means "any day, any room, but must start at 13:00"; the
        second means "must be room ECC-804 on Monday, any start time". A
        blank room is only ever filled with one big enough for the class,
        and Prolog keeps every professor to one class per period.
      </p>
    {/if}

    <button type="submit" disabled={status === 'loading'}>
      {#if status === 'loading'}
        {autoSchedule ? 'Scheduling…' : 'Loading…'}
      {:else}
        {autoSchedule ? 'Run auto-scheduling' : 'Load schedule'}
      {/if}
    </button>
  </form>

  {#if status === 'error'}
    <p class="error">{errorMessage}</p>
  {/if}

  {#if status === 'done' && schedule}
    <div class="result">
      <div class="result-bar">
        <p>
          Semester {schedule.semester} · Academic Year {schedule.academic_year} ·
          {schedule.classes.length} classes
          {#if completedCsvUrl}· scheduled by Prolog{/if}
        </p>
        <div class="actions">
          {#if completedCsvUrl}
            <a
              href={completedCsvUrl}
              download="classroom-schedule-{schedule.academic_year}-s{schedule.semester}.csv"
            >Download completed CSV</a>
          {/if}
          <button type="button" onclick={downloadPdf} disabled={pdfStatus === 'loading'}>
            {pdfStatus === 'loading' ? 'Rendering PDF…' : 'Download summary PDF'}
          </button>
        </div>
      </div>
      {#if pdfStatus === 'error'}
        <p class="error">{pdfError}</p>
      {/if}

      <FloorPlan
        classes={schedule.classes}
        capacities={schedule.capacities}
        {selectedRoom}
        onselect={(room) => (selectedRoom = room)}
      />

      {#if selectedRoom}
        <RoomTimetable
          room={selectedRoom}
          capacity={schedule.capacities[selectedRoom]}
          classes={schedule.classes}
        />
      {/if}
    </div>
  {/if}
</main>

<style>
  main {
    max-width: 1000px;
    margin: 2rem auto;
    padding: 0 1rem 3rem;
  }

  .subtitle {
    color: #555;
  }

  form {
    max-width: 640px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin: 1.5rem 0;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-weight: 600;
  }

  label.checkbox-row {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }

  input[type='file'] {
    font: inherit;
    padding: 0.35rem;
  }

  .hint {
    margin: 0;
    font-size: 0.9rem;
    color: #444;
  }

  .hint-example {
    margin: 0;
    padding: 0.5rem 0.75rem;
    background: #f4f4f4;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 0.85rem;
    overflow-x: auto;
  }

  button {
    align-self: flex-start;
    padding: 0.5rem 1.25rem;
    font-size: 1rem;
    cursor: pointer;
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .error {
    color: #b00020;
    white-space: pre-wrap;
  }


  .result {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    margin-top: 1.5rem;
  }

  .result-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem 1rem;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .result-bar p {
    margin: 0;
    color: #444;
  }
</style>
