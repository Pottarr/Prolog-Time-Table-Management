<script>
  // The schedule CSV editor: a pop-up over the page with two tabs.
  //   Classes    — one row per CSV row; room / day / period are dropdowns
  //                ("Any" = Prolog picks it), the rest are typed.
  //   Professors — each professor's general preference (a day and/or a
  //                period). The gateway rewrites day/start on all of that
  //                professor's rows (/api/csv/professor-preference).
  // Requests that clash (two fixed rows wanting one room or professor in
  // one period) are flagged but allowed: the scheduler then moves one of
  // them to a free spot ("unsatisfied" cases). Saving hands the rows back to the page,
  // which re-runs the scheduler.
  import { untrack } from 'svelte';
  import { API_BASE } from '../config.js';
  import { DAYS, ROOMS, PERIOD_STARTS, clashFlags, profKey } from './schedule.js';

  let {
    rows: initialRows = [],
    fileName = '',
    justUploaded = false,
    canRun = false,
    busy = false,
    error = '',
    maxCases = $bindable(10),
    onsave,
    oncancel,
  } = $props();

  let nextId = 0;
  const withId = (row) => ({ ...row, _id: nextId++ });
  let draft = $state(untrack(() => initialRows.map(withId)));
  let tab = $state('classes');
  let filter = $state('');
  let dirty = $state(false);
  let openProf = $state(null);
  let prefBusy = $state(false);
  let prefError = $state('');

  const PERIOD_LABEL = { 9: 'Morning 09–12', 13: 'Afternoon 13–16' };

  const flags = $derived(clashFlags(draft));
  const clashCount = $derived(new Set([...flags.values()].flatMap((f) => f.groups)).size);

  const visible = $derived.by(() => {
    const q = filter.trim().toLowerCase();
    return draft
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => !q || `${row.title ?? ''} ${row.prof ?? ''}`.toLowerCase().includes(q));
  });

  const professors = $derived.by(() => {
    const byKey = new Map();
    draft.forEach((row, index) => {
      const key = profKey(row.prof);
      if (!key) return;
      if (!byKey.has(key)) byKey.set(key, { key, name: row.prof.trim().replace(/\s+/g, ' '), rows: [] });
      byKey.get(key).rows.push(index);
    });
    const q = filter.trim().toLowerCase();
    return [...byKey.values()]
      .filter((p) => !q || p.name.toLowerCase().includes(q))
      .map((p) => {
        const days = new Set(p.rows.map((i) => draft[i].day ?? 'any'));
        const periods = new Set(p.rows.map((i) => periodOf(draft[i].start)));
        const day = days.size === 1 ? [...days][0] : 'mixed';
        const period = periods.size === 1 ? [...periods][0] : 'mixed';
        // Periods a preference leaves open, vs. how many classes need one.
        const slots = (day === 'any' || day === 'mixed' ? 7 : 1) * (period === 'any' || period === 'mixed' ? 2 : 1);
        return { ...p, day, period, mixedDays: [...days], tooMany: p.rows.length > slots };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  function periodOf(start) {
    if (start == null || start === '') return 'any';
    if (String(start) === '9') return 'morning';
    if (String(start) === '13') return 'afternoon';
    return 'other';
  }

  function set(index, field, value) {
    draft[index][field] = value === '' ? null : value;
    dirty = true;
  }

  function addRow() {
    draft.push(withId({ room: null, day: null, start: null, span: '3', title: '', prof: '', students: '' }));
    dirty = true;
    filter = '';
  }

  function removeRow(index) {
    draft.splice(index, 1);
    dirty = true;
  }

  const strip = (rows) => rows.map(({ _id, ...row }) => row);

  async function setPreference(prof, change) {
    prefBusy = true;
    prefError = '';
    try {
      const response = await fetch(`${API_BASE}/api/csv/professor-preference`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows: strip(draft), prof: prof.name, day: 'keep', period: 'keep', ...change }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`);
      // Same order back; keep each row's id so the Classes tab doesn't re-render from scratch.
      draft = body.rows.map((row, i) => ({ ...row, _id: draft[i]._id }));
      dirty = true;
    } catch (err) {
      prefError = err instanceof Error ? err.message : String(err);
    } finally {
      prefBusy = false;
    }
  }

  function save() {
    onsave?.(strip(draft));
  }

  function onkeydown(event) {
    if (event.key === 'Escape' && !busy) oncancel?.();
  }

  const clashText = (f) =>
    f.with.length ? `Clash · row ${f.with.map((i) => i + 1).join(', ')}` : '';
</script>

<svelte:window {onkeydown} />

<div class="scrim">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="editor-title">
    <header class="m-head">
      <h2 id="editor-title">Edit schedule</h2>
      <div class="sub">
        <div class="lbl dim">{fileName || 'schedule.csv'}</div>
        <div class="note">
          {#if justUploaded && !dirty}
            <span class="lbl accent">Just uploaded</span> — check it, then save to run the scheduler.
          {:else if dirty}
            <span class="lbl dim">Unsaved changes</span>
          {:else}
            Leave room, day or period on <b>Any</b> and Prolog picks it.
          {/if}
        </div>
      </div>
      <button class="x" type="button" aria-label="Close without saving" onclick={() => oncancel?.()} disabled={busy}>×</button>
    </header>

    <div class="m-tabs" role="tablist">
      <button type="button" role="tab" aria-selected={tab === 'classes'} class:on={tab === 'classes'} onclick={() => (tab = 'classes')}>
        Classes<i>{draft.length}</i>
      </button>
      <button type="button" role="tab" aria-selected={tab === 'profs'} class:on={tab === 'profs'} onclick={() => (tab = 'profs')}>
        Professors<i>{professors.length}</i>
      </button>
    </div>

    <div class="m-body">
      <div class="toolbar">
        <input
          class="search"
          type="search"
          placeholder={tab === 'classes' ? 'Filter by title or professor' : 'Find a professor'}
          bind:value={filter}
        />
        {#if tab === 'classes'}
          <span class="hint">Leave room, day or period on <b>Any</b> and Prolog picks it.</span>
          <span class="sp"></span>
          <button class="btn ghost small" type="button" onclick={addRow}>+ Add class</button>
        {:else}
          <span class="hint">
            A preference rewrites <b>day</b> and <b>start</b> on every one of that professor's rows in the CSV. Room
            stays per class.
          </span>
        {/if}
      </div>

      {#if tab === 'classes'}
        <table class="classes">
          <thead>
            <tr>
              <th></th><th>Title</th><th>Professor</th><th class="r">Students</th><th>Room</th><th>Day</th>
              <th>Period</th><th>Span</th><th></th><th></th>
            </tr>
          </thead>
          <tbody>
            {#each visible as { row, index } (row._id)}
              {@const flag = flags.get(index)}
              <tr class:clash={flag}>
                <td class="idx">{index + 1}</td>
                <td><input class="t" value={row.title ?? ''} oninput={(e) => set(index, 'title', e.target.value)} aria-label="Title, row {index + 1}" /></td>
                <td><input class="t" value={row.prof ?? ''} oninput={(e) => set(index, 'prof', e.target.value)} aria-label="Professor, row {index + 1}" /></td>
                <td class="r">
                  <input class="t num" inputmode="numeric" value={row.students ?? ''} oninput={(e) => set(index, 'students', e.target.value)} aria-label="Students, row {index + 1}" />
                </td>
                <td>
                  <select value={row.room ?? ''} onchange={(e) => set(index, 'room', e.target.value)} aria-label="Room, row {index + 1}">
                    <option value="">Any room</option>
                    {#each ROOMS as room (room)}<option value={room}>{room}</option>{/each}
                    {#if row.room && !ROOMS.includes(row.room)}<option value={row.room}>{row.room} (not on 8F)</option>{/if}
                  </select>
                </td>
                <td>
                  <select value={row.day ?? ''} onchange={(e) => set(index, 'day', e.target.value)} aria-label="Day, row {index + 1}">
                    <option value="">Any day</option>
                    {#each DAYS as day (day)}<option value={day}>{day}</option>{/each}
                    {#if row.day && !DAYS.includes(row.day)}<option value={row.day}>{row.day} (invalid)</option>{/if}
                  </select>
                </td>
                <td>
                  <select value={row.start ?? ''} onchange={(e) => set(index, 'start', e.target.value)} aria-label="Period, row {index + 1}">
                    <option value="">Any time</option>
                    {#each PERIOD_STARTS as start (start)}<option value={String(start)}>{PERIOD_LABEL[start]}</option>{/each}
                    {#if row.start && !PERIOD_STARTS.map(String).includes(String(row.start))}
                      <option value={row.start}>Starts {row.start}:00 (invalid)</option>
                    {/if}
                  </select>
                </td>
                <td>
                  <select class="span" value={row.span ?? ''} onchange={(e) => set(index, 'span', e.target.value)} aria-label="Span, row {index + 1}">
                    <option value="3">3 h</option>
                    {#if String(row.span ?? '') !== '3'}<option value={row.span ?? ''}>{row.span ?? '—'} h (invalid)</option>{/if}
                  </select>
                </td>
                <td>{#if flag}<span class="flag" title={flag.messages.join('\n')}>{clashText(flag)}</span>{/if}</td>
                <td><button class="del" type="button" aria-label="Delete row {index + 1}" onclick={() => removeRow(index)}>×</button></td>
              </tr>
            {:else}
              <tr><td colspan="10" class="empty">{draft.length ? 'No class matches the filter.' : 'No classes yet — add one.'}</td></tr>
            {/each}
          </tbody>
        </table>
      {:else}
        {#if prefError}<p class="error">{prefError}</p>{/if}
        <table class="profs">
          <thead>
            <tr><th>Professor</th><th>Classes</th><th>Preferred day</th><th>Preferred period</th><th></th></tr>
          </thead>
          <tbody>
            {#each professors as prof (prof.key)}
              {@const open = openProf === prof.key}
              {@const clashing = prof.rows.some((i) => flags.has(i))}
              <tr class:open>
                <td class="pname">{prof.name}{#if clashing}<span class="dot" title="Asks for clashing periods"></span>{/if}</td>
                <td class="dim">{prof.rows.length} class{prof.rows.length === 1 ? '' : 'es'}</td>
                <td>
                  <select
                    value={prof.day}
                    disabled={prefBusy}
                    onchange={(e) => setPreference(prof, { day: e.target.value })}
                    aria-label="Preferred day for {prof.name}"
                  >
                    {#if prof.day === 'mixed'}<option value="mixed" disabled>Mixed</option>{/if}
                    <option value="any">Any day</option>
                    {#each DAYS as day (day)}<option value={day}>{day}</option>{/each}
                  </select>
                  {#if prof.day === 'mixed'}
                    <span class="mixed">rows differ: {prof.mixedDays.map((d) => (d === 'any' ? 'Any' : d)).join(' · ')}</span>
                  {/if}
                </td>
                <td>
                  <span class="pill" role="group" aria-label="Preferred period for {prof.name}">
                    {#each [['any', 'Any'], ['morning', 'Morning'], ['afternoon', 'Afternoon']] as [value, label] (value)}
                      <button
                        type="button"
                        class:on={prof.period === value}
                        aria-pressed={prof.period === value}
                        disabled={prefBusy}
                        onclick={() => setPreference(prof, { period: value })}
                      >{label}</button>
                    {/each}
                  </span>
                  {#if prof.period === 'mixed' || prof.period === 'other'}<span class="mixed">rows differ</span>{/if}
                </td>
                <td class="expand">
                  <button type="button" onclick={() => (openProf = open ? null : prof.key)} aria-expanded={open}>
                    {open ? '▾ Hide classes' : '▸ Show classes'}
                  </button>
                </td>
              </tr>
              {#if open || prof.tooMany}
                <tr class="sub" class:open>
                  <td colspan="5">
                    {#if open}
                      {#each prof.rows as i (i)}
                        <span class="chip">#{i + 1} {draft[i].title || 'Untitled'}{draft[i].room ? ` · ${draft[i].room.slice(4)}` : ''}</span>
                      {/each}
                    {/if}
                    {#if prof.tooMany}
                      <span class="warn">
                        ⚠ This preference leaves fewer periods than {prof.name}'s {prof.rows.length} classes — some will be
                        moved elsewhere (allowed, shown as unsatisfied).
                      </span>
                    {/if}
                  </td>
                </tr>
              {/if}
            {:else}
              <tr><td colspan="5" class="empty">No professors{filter ? ' match the search' : ' yet'}.</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>

    <footer class="m-foot">
      <span class="note">
        {#if error}
          <span class="error">{error}</span>
        {:else if !canRun}
          <span class="dim">Choose the config JSON to run the scheduler — your edits are kept.</span>
        {:else if clashCount}
          <span class="dot"></span><b>{clashCount} time clash{clashCount === 1 ? '' : 'es'}</b>
          <span class="dim"> — allowed; the scheduler moves a class to a free spot (an unsatisfied case).</span>
        {:else}
          <span class="dim">No time clashes between fixed classes.</span>
        {/if}
      </span>
      <label class="lbl cap" title="0 = no cap: every case, however long it takes">
        Cases <span class="dim">0 = no cap</span>
        <input class="num" type="number" min="0" bind:value={maxCases} disabled={busy} />
      </label>
      <button class="btn ghost" type="button" onclick={() => oncancel?.()} disabled={busy}>Cancel</button>
      <button class="btn" type="button" onclick={save} disabled={busy || prefBusy}>
        {#if busy}Scheduling…{:else if canRun}Save &amp; run scheduler{:else}Save{/if}
      </button>
    </footer>
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(43, 43, 43, 0.42);
    display: grid;
    place-items: center;
    padding: 24px;
  }

  .modal {
    width: min(1120px, 100%);
    height: min(760px, 100%);
    background: var(--cream);
    border: 1px solid var(--ink);
    box-shadow: 0 30px 60px -20px rgba(30, 30, 50, 0.55);
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .m-head {
    display: flex;
    align-items: flex-end;
    gap: 24px;
    padding: 22px 28px 0;
  }

  h2 {
    margin: 0;
    font: 800 44px/1 var(--serif);
    letter-spacing: -0.01em;
  }

  .sub {
    flex: 1;
    min-width: 0;
    padding-bottom: 4px;
  }

  .note {
    font-size: 15px;
  }

  .accent {
    color: var(--accent);
  }

  .dim {
    color: var(--sub);
  }

  .x {
    align-self: flex-start;
    border: 0;
    background: none;
    font: 300 32px/1 var(--sans);
    cursor: pointer;
    padding: 0 4px;
  }

  .m-tabs {
    display: flex;
    padding: 0 28px;
    margin-top: 16px;
    border-bottom: 1px solid var(--ink);
  }

  .m-tabs button {
    padding: 8px 18px 7px;
    margin-bottom: -1px;
    border: 1px solid transparent;
    border-bottom: 0;
    background: none;
    font: 500 13px var(--sans);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--sub);
    cursor: pointer;
  }

  .m-tabs button.on {
    color: var(--ink);
    background: var(--cream);
    border-color: var(--ink);
    border-bottom: 1px solid var(--cream);
  }

  .m-tabs i {
    font: 600 13px var(--serif);
    font-style: normal;
    margin-left: 6px;
    color: var(--hair);
  }

  /* The only part of the editor that scrolls. */
  .m-body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 14px 28px;
    scrollbar-width: thin;
    scrollbar-color: var(--soft) transparent;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }

  .sp {
    flex: 1;
  }

  .search {
    width: 260px;
    flex: none;
    padding: 5px 10px;
    border: 1px solid var(--hair);
    background: var(--cream);
    font: 400 15px var(--sans);
  }

  .hint {
    font-size: 13px;
    color: var(--sub);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    position: sticky;
    top: -14px;
    z-index: 1;
    background: var(--cream);
    text-align: left;
    font: 500 11px var(--sans);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--sub);
    padding: 6px 8px;
    border-bottom: 1px solid var(--ink);
  }

  td {
    padding: 4px 8px;
    border-bottom: 1px solid var(--soft);
    vertical-align: middle;
  }

  .r {
    text-align: right;
  }

  td.idx {
    width: 34px;
    font: 600 14px var(--serif);
    color: var(--hair);
  }

  .t {
    width: 100%;
    padding: 4px 6px;
    border: 1px solid transparent;
    background: none;
    font: 400 15px var(--sans);
  }

  .t.num {
    width: 60px;
    text-align: right;
  }

  .t:hover {
    border-color: var(--hair);
  }

  .t:focus {
    outline: 1px solid var(--accent);
    border-color: var(--accent);
    background: var(--cream);
  }

  select {
    appearance: none;
    padding: 4px 24px 4px 8px;
    border: 1px solid var(--hair);
    border-radius: 0;
    background: var(--cream)
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%232b2b2b' stroke-width='1.2'/%3E%3C/svg%3E")
      no-repeat right 8px center;
    font: 400 15px var(--sans);
    color: var(--ink);
    cursor: pointer;
  }

  select:disabled {
    opacity: 0.6;
    cursor: default;
  }

  select.span {
    color: var(--sub);
  }

  tr.clash td {
    background: rgba(155, 44, 44, 0.06);
  }

  .flag {
    display: inline-block;
    padding: 1px 6px;
    border: 1px solid var(--error);
    font: 500 11px var(--sans);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--error);
    white-space: nowrap;
  }

  .del {
    width: 28px;
    border: 0;
    background: none;
    color: var(--hair);
    font: 300 20px var(--sans);
    cursor: pointer;
  }

  .del:hover {
    color: var(--error);
  }

  .empty {
    padding: 24px 8px;
    text-align: center;
    color: var(--sub);
  }

  .pname {
    font: 600 17px var(--serif);
  }

  .profs td {
    padding: 7px 8px;
  }

  .profs select {
    width: 120px;
  }

  tr.open td {
    background: var(--hover);
  }

  tr.sub td {
    padding-top: 0;
    font-size: 14px;
    color: var(--sub);
  }

  .pill {
    display: inline-flex;
    border: 1px solid var(--ink);
  }

  .pill button {
    padding: 3px 10px;
    border: 0;
    border-left: 1px solid var(--ink);
    background: none;
    font: 500 12px var(--sans);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    cursor: pointer;
  }

  .pill button:first-child {
    border-left: 0;
  }

  .pill button.on {
    background: var(--ink);
    color: var(--cream);
  }

  .pill button:hover:not(.on):not(:disabled) {
    background: var(--hover);
  }

  .mixed {
    margin-left: 6px;
    font: 500 11px var(--sans);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
  }

  .expand {
    text-align: right;
  }

  .expand button {
    border: 0;
    background: none;
    font: 400 13px var(--sans);
    color: var(--sub);
    cursor: pointer;
  }

  .chip {
    display: inline-block;
    margin: 0 4px 4px 0;
    padding: 1px 7px;
    border: 1px solid var(--hair);
    font-size: 13px;
  }

  .warn {
    color: var(--error);
  }

  .dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    margin: 0 6px;
    border-radius: 50%;
    background: var(--error);
    vertical-align: middle;
  }

  .m-foot {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 28px;
    border-top: 1px solid var(--ink);
    background: var(--tan);
  }

  .m-foot .note {
    flex: 1;
    min-width: 0;
    font-size: 15px;
  }

  .m-foot .note .dot {
    margin-left: 0;
  }

  .error {
    color: var(--error);
    overflow-wrap: anywhere;
  }

  p.error {
    margin: 0 0 8px;
  }

  .m-foot .error {
    display: block;
    max-height: 3em;
    overflow: auto;
  }

  .cap {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .num[type='number'] {
    width: 64px;
    padding: 5px 8px;
    border: 1px solid var(--ink);
    background: var(--cream);
    font: 500 16px var(--sans);
    text-align: right;
  }

  @media (max-width: 899px) {
    .scrim {
      padding: 8px;
    }

    h2 {
      font-size: 30px;
    }

    .m-head,
    .m-tabs,
    .m-body,
    .m-foot {
      padding-left: 14px;
      padding-right: 14px;
    }

    .hint {
      display: none;
    }

    .m-foot {
      flex-wrap: wrap;
    }
  }
</style>
