<script>
  // One room's week: days down the side, the two periods across (morning
  // 09:00–12:00 | lunch | afternoon 13:00–16:00). Every class fills exactly
  // one period (the gateway enforces that), so one cell = one class. The
  // grid stretches to the height it's given, and long titles shrink and
  // clamp instead of making the page scroll.
  let { room, capacity, classes = [] } = $props();

  const DAYS = [
    ['Mon', 'Monday'],
    ['Tue', 'Tuesday'],
    ['Wed', 'Wednesday'],
    ['Thu', 'Thursday'],
    ['Fri', 'Friday'],
    ['Sat', 'Saturday'],
    ['Sun', 'Sunday'],
  ];
  const WEEKEND = new Set(['Sat', 'Sun']);

  const byDayStart = $derived(
    new Map(classes.filter((c) => c.room === room).map((c) => [`${c.day}-${c.start}`, c])),
  );
</script>

{#if capacity === 0}
  <p class="not-used">Co-working space — not used for lectures.</p>
{:else}
  <div class="grid" role="table" aria-label="Weekly timetable for {room}">
    <div class="row head" role="row">
      <span role="columnheader"></span>
      <span role="columnheader" class="lbl">Morning <em>09:00 – 12:00</em></span>
      <span role="columnheader" class="lbl lunch">Lunch</span>
      <span role="columnheader" class="lbl">Afternoon <em>13:00 – 16:00</em></span>
    </div>
    {#each DAYS as [code, name] (code)}
      <div class="row" class:weekend={WEEKEND.has(code)} role="row">
        <span class="day" role="rowheader" title={name}>{code}</span>
        {#each [9, null, 13] as start, i (i)}
          {#if start === null}
            <span class="lunch" role="cell" aria-label="Lunch"></span>
          {:else}
            {@const lesson = byDayStart.get(`${code}-${start}`)}
            <span class="cell" role="cell">
              {#if lesson}
                <span class="class" title="{lesson.title} — {lesson.prof}, {lesson.students} / {capacity} seats">
                  <b>{lesson.title}</b>
                  <span class="meta">{lesson.prof} · {lesson.students} / {capacity} seats</span>
                </span>
              {:else}
                <span class="free">Free</span>
              {/if}
            </span>
          {/if}
        {/each}
      </div>
    {/each}
  </div>
{/if}

<style>
  .grid {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-rows: auto repeat(7, minmax(0, 1fr));
    /* Text scales with the window height so seven days always fit. */
    font-size: clamp(12px, 2.1vh, 20px);
  }

  .row {
    display: grid;
    grid-template-columns: 4.2em 1fr 3.4em 1fr;
    min-height: 0;
    border-bottom: 1px solid var(--soft);
  }

  .row.head {
    border-bottom: 1px solid var(--ink);
  }

  .row.head > span {
    padding: 0 0.6em 0.4em;
    align-self: end;
  }

  .head em {
    display: block;
    font: 300 13px var(--sans);
    font-style: normal;
    letter-spacing: 0.04em;
    text-transform: none;
    color: var(--hair);
  }

  .head .lunch {
    text-align: center;
    color: var(--hair);
  }

  .day {
    align-self: center;
    padding-left: 0.3em;
    font: 600 1.35em var(--serif);
  }

  .weekend .day {
    color: var(--hair);
  }

  .lunch {
    border-left: 1px solid var(--soft);
    border-right: 1px solid var(--soft);
  }

  .cell {
    min-width: 0;
    min-height: 0;
    padding: 0.35em 0.6em;
    display: flex;
    align-items: center;
    overflow: hidden;
  }

  .class {
    min-width: 0;
    display: flex;
    flex-direction: column;
    padding-left: 0.6em;
    border-left: 3px solid var(--accent);
  }

  .class b {
    font-weight: 500;
    font-size: 1.05em;
    line-height: 1.15;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .meta {
    font-size: 0.85em;
    color: var(--sub);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .free {
    font-size: 0.75em;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--soft);
  }

  .not-used {
    margin: 0;
    padding: 3rem 1rem;
    text-align: center;
    font: 300 22px var(--sans);
    color: var(--hair);
    border-top: 1px solid var(--soft);
    border-bottom: 1px solid var(--soft);
  }

  @media (max-width: 899px) {
    .grid {
      height: auto;
      grid-template-rows: auto;
      grid-auto-rows: minmax(64px, auto);
      font-size: 15px;
    }
  }
</style>
