<script>
  import { API_BASE } from './config.js';

  const CURRENT_YEAR = new Date().getFullYear();
  const MIN_ACADEMIC_YEAR = CURRENT_YEAR - 5;
  const MAX_ACADEMIC_YEAR = CURRENT_YEAR + 5;
  const ACADEMIC_YEARS = Array.from(
    { length: MAX_ACADEMIC_YEAR - MIN_ACADEMIC_YEAR + 1 },
    (_, i) => MIN_ACADEMIC_YEAR + i,
  );

  let csvFile = $state(null);
  let semester = $state(1);
  let academicYear = $state(CURRENT_YEAR);
  let autoSchedule = $state(false);
  let status = $state('idle'); // idle | loading | error | not_implemented | done
  let errorMessage = $state('');
  let prologRequestPreview = $state(null);
  let pdfUrl = $state('');
  let pdfFilename = $state('');

  function onFileChange(event) {
    csvFile = event.target.files?.[0] ?? null;
  }

  function resetResult() {
    status = 'loading';
    errorMessage = '';
    prologRequestPreview = null;
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = '';
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!csvFile) {
      status = 'error';
      errorMessage = 'Please choose a CSV file first.';
      return;
    }

    resetResult();

    const formData = new FormData();
    formData.append('csv_file', csvFile);
    formData.append('semester', String(semester));
    formData.append('academic_year', String(academicYear));

    const endpoint = autoSchedule ? '/api/schedule/auto' : '/api/schedule/pdf';

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        body: formData,
      });

      if (response.status === 501) {
        const body = await response.json().catch(() => null);
        status = 'not_implemented';
        errorMessage =
          body?.detail?.message ?? 'Auto-scheduling is not implemented yet.';
        prologRequestPreview = body?.detail?.prolog_request ?? null;
        return;
      }

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = typeof body?.detail === 'string' ? body.detail : null;
        throw new Error(detail ?? `Request failed with status ${response.status}`);
      }

      const blob = await response.blob();
      pdfUrl = URL.createObjectURL(blob);
      pdfFilename = `classroom-schedule-${academicYear}-s${semester}.pdf`;
      status = 'done';
    } catch (err) {
      status = 'error';
      errorMessage = err instanceof Error ? err.message : String(err);
    }
  }
</script>

<main>
  <h1>Classroom Schedule Generator</h1>
  <p class="subtitle">Upload a schedule CSV to generate a printable PDF timetable.</p>

  <form onsubmit={handleSubmit}>
    <label>
      Schedule CSV
      <input type="file" accept=".csv,text/csv" onchange={onFileChange} required />
    </label>

    <label>
      Semester
      <select bind:value={semester}>
        <option value={1}>1</option>
        <option value={2}>2</option>
      </select>
    </label>

    <label>
      Academic year
      <select bind:value={academicYear}>
        {#each ACADEMIC_YEARS as year (year)}
          <option value={year}>{year}</option>
        {/each}
      </select>
    </label>

    <label class="checkbox-row">
      <input type="checkbox" bind:checked={autoSchedule} />
      Auto-scheduling (let Prolog pick day / time / room)
    </label>

    {#if autoSchedule}
      <p class="hint">
        Leave <code>day</code>, <code>start</code>, or <code>room</code> blank
        (or write <code>NULL</code>) for whatever the professor is flexible
        on. <code>span</code>, <code>title</code>, and <code>prof</code> are
        always required. Example rows:
      </p>
      <pre class="hint-example">NULL,NULL,13,3,Algorithms,Dr. Veera
ECC-804,Mon,NULL,3,Databases,Dr. Suphamit</pre>
      <p class="hint">
        The first means "any day, any room, but must start at 13:00"; the
        second means "must be room ECC-804 on Monday, any start time".
      </p>
    {/if}

    <button type="submit" disabled={status === 'loading'}>
      {#if status === 'loading'}
        {autoSchedule ? 'Sending…' : 'Generating…'}
      {:else}
        {autoSchedule ? 'Run auto-scheduling' : 'Generate PDF'}
      {/if}
    </button>
  </form>

  {#if status === 'error'}
    <p class="error">{errorMessage}</p>
  {/if}

  {#if status === 'not_implemented'}
    <div class="notice">
      <p>{errorMessage}</p>
      {#if prologRequestPreview}
        <p>Request the gateway will send to the Prolog service once it exists:</p>
        <pre>{JSON.stringify(prologRequestPreview, null, 2)}</pre>
      {/if}
    </div>
  {/if}

  {#if status === 'done' && pdfUrl}
    <div class="result">
      <a href={pdfUrl} download={pdfFilename}>Download {pdfFilename}</a>
      <iframe title="Schedule PDF preview" src={pdfUrl}></iframe>
    </div>
  {/if}
</main>

<style>
  main {
    max-width: 640px;
    margin: 2rem auto;
    padding: 0 1rem 3rem;
  }

  .subtitle {
    color: #555;
  }

  form {
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

  select,
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

  .notice {
    background: #fff8e1;
    border: 1px solid #e0c46c;
    border-radius: 4px;
    padding: 0.75rem 1rem;
  }

  .notice pre {
    overflow-x: auto;
    background: #fffdf5;
    padding: 0.5rem;
    border-radius: 4px;
  }

  .result {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 1.5rem;
  }

  iframe {
    width: 100%;
    height: 80vh;
    border: 1px solid #ccc;
  }
</style>
