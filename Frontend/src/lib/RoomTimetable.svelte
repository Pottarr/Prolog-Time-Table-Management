<script>
  // One room's weekly timetable, laid out like a page of the PDF
  // (Backend/Gateway/app/templates/classroom-schedule.typ): days down the
  // side, hourly slots 09:00–16:00 across, 12:00–13:00 fixed as lunch.
  // A room with capacity 0 isn't used for lectures and gets no table.
  let { room, capacity, classes = [] } = $props();

  const FIRST_HOUR = 9;
  const SLOT_COUNT = 7; // 09:00 .. 16:00
  const LUNCH_SLOT = 12 - FIRST_HOUR;
  const DAYS = [
    ['Mon', 'Monday'],
    ['Tue', 'Tuesday'],
    ['Wed', 'Wednesday'],
    ['Thu', 'Thursday'],
    ['Fri', 'Friday'],
    ['Sat', 'Saturday'],
    ['Sun', 'Sunday'],
  ];

  const pad = (hour) => `${String(hour).padStart(2, '0')}:00`;
  const slotLabels = Array.from(
    { length: SLOT_COUNT },
    (_, i) => `${pad(FIRST_HOUR + i)}–${pad(FIRST_HOUR + i + 1)}`,
  );

  const roomClasses = $derived(classes.filter((c) => c.room === room));

  // Per day, a left-to-right list of cells: a class spanning its hours,
  // the lunch slot, or a free hour. The gateway already rejected overlaps.
  const rows = $derived(
    DAYS.map(([code, name]) => {
      const byStart = new Map(
        roomClasses.filter((c) => c.day === code).map((c) => [c.start - FIRST_HOUR, c]),
      );
      const cells = [];
      for (let slot = 0; slot < SLOT_COUNT; ) {
        const lesson = byStart.get(slot);
        if (lesson) {
          cells.push({ kind: 'class', slot, span: lesson.span, lesson });
          slot += lesson.span;
        } else {
          cells.push({ kind: slot === LUNCH_SLOT ? 'lunch' : 'free', slot, span: 1 });
          slot += 1;
        }
      }
      return { name, cells };
    }),
  );

  const totalHours = $derived(roomClasses.reduce((sum, c) => sum + c.span, 0));
</script>

<section class="timetable" aria-label="Timetable for {room}">
  <header>
    <h2>{capacity === 0 ? 'Room' : 'Classroom'} {room}</h2>
    {#if capacity !== 0}
      <p>
        Capacity {capacity} seats ·
        {roomClasses.length === 0
          ? 'No classes scheduled this semester.'
          : `${roomClasses.length} class${roomClasses.length === 1 ? '' : 'es'} · ${totalHours} h per week`}
      </p>
    {/if}
  </header>

  {#if capacity === 0}
    <p class="not-used">Room not used for lectures.</p>
  {:else}
    <div class="scroll">
      <div class="grid" style:--slots={SLOT_COUNT}>
        <div class="head corner">Day / Time</div>
        {#each slotLabels as label (label)}
          <div class="head">{label}</div>
        {/each}

        {#each rows as row, rowIndex (row.name)}
          <div class="day" style:grid-row={rowIndex + 2}>{row.name}</div>
          {#each row.cells as cell (cell.slot)}
            <div
              class="cell {cell.kind}"
              style:grid-row={rowIndex + 2}
              style:grid-column="{cell.slot + 2} / span {cell.span}"
            >
              {#if cell.kind === 'class'}
                <span class="title">{cell.lesson.title}</span>
                <span class="prof">{cell.lesson.prof} · {cell.lesson.students} students</span>
              {:else if cell.kind === 'lunch'}
                <span class="lunch-label">Lunch</span>
              {:else}
                <span class="dash">—</span>
              {/if}
            </div>
          {/each}
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  header h2 {
    margin: 0;
  }

  header p {
    margin: 0.2rem 0 0.75rem;
    color: #555;
  }

  .not-used {
    margin: 0.75rem 0 0;
    padding: 1rem;
    border: 1px dashed #999;
    background: #f4f4f4;
    color: #444;
  }

  .scroll {
    overflow-x: auto;
  }

  .grid {
    display: grid;
    grid-template-columns: 6.5rem repeat(var(--slots), minmax(4.5rem, 1fr));
    grid-auto-rows: minmax(3.5rem, auto);
    min-width: 560px;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    font-size: 0.8rem;
  }

  .grid > div {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 0.25rem;
    text-align: center;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
  }

  .head {
    min-height: 2.5rem;
    background: #aaa;
    color: #fff;
    font-weight: 700;
    font-size: 0.7rem;
  }

  .day {
    grid-column: 1;
    background: #bbb;
    font-weight: 700;
  }

  .cell.class {
    background: #eee;
  }

  .cell.lunch {
    background: #ddd;
    font-weight: 700;
  }

  .title {
    font-weight: 600;
    line-height: 1.2;
  }

  .prof {
    color: #555;
    font-size: 0.75rem;
  }

  .dash {
    color: #aaa;
  }
</style>
