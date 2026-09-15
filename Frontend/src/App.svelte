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
  let status = $state('idle'); // idle | loading | error | done
  let errorMessage = $state('');
  let pdfUrl = $state('');
  let pdfFilename = $state('');

  function onFileChange(event) {
    csvFile = event.target.files?.[0] ?? null;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!csvFile) {
      status = 'error';
      errorMessage = 'Please choose a CSV file first.';
      return;
    }

    status = 'loading';
    errorMessage = '';
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    pdfUrl = '';

    const formData = new FormData();
    formData.append('csv_file', csvFile);
    formData.append('semester', String(semester));
    formData.append('academic_year', String(academicYear));

    try {
      const response = await fetch(`${API_BASE}/api/schedule/pdf`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
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

    <button type="submit" disabled={status === 'loading'}>
      {status === 'loading' ? 'Generating…' : 'Generate PDF'}
    </button>
  </form>

  {#if status === 'error'}
    <p class="error">{errorMessage}</p>
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

  select,
  input[type='file'] {
    font: inherit;
    padding: 0.35rem;
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
    gap: 0.75rem;
    margin-top: 1.5rem;
  }

  iframe {
    width: 100%;
    height: 80vh;
    border: 1px solid #ccc;
  }
</style>
