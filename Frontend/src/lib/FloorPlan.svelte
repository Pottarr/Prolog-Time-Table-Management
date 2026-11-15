<script>
  // Clickable ECC 8th-floor plan. The SVG ships with one `<g id="room-8NN">`
  // per classroom; we tag those groups with data-room / class hooks before
  // injecting the markup, so the plan itself stays a plain drawing that can
  // be edited in any SVG tool. Toilets, lifts, stairs, P/S and corridors are
  // left untouched and aren't clickable.
  import floorPlanSvg from './ecc-8th-floor.svg?raw';

  let { classes = [], capacities = {}, selectedRoom = null, onselect } = $props();

  const ROOM_GROUP_RE =
    /<g id="room-(8\d\d)" class="space"><rect ([^>]*)\/><text x="([\d.]+)" y="([\d.]+)"([^>]*)>\d+<\/text><\/g>/g;

  const countsByRoom = $derived(
    classes.reduce((counts, c) => counts.set(c.room, (counts.get(c.room) ?? 0) + 1), new Map()),
  );

  const markup = $derived(
    floorPlanSvg
      .replace(/ width="\d+" height="\d+"/, '')
      .replace(ROOM_GROUP_RE, (_, number, rectAttrs, x, y, textAttrs) => {
        const room = `ECC-${number}`;
        const count = countsByRoom.get(room) ?? 0;
        const state = [
          'room',
          count > 0 ? 'booked' : 'empty',
          room === selectedRoom ? 'selected' : '',
        ].join(' ');
        const classesText = count === 0 ? 'free' : `${count} class${count === 1 ? '' : 'es'}`;
        const seats = capacities[room];
        const label = `${room}: ${seats} seats, ${count === 0 ? 'no classes' : classesText}`;
        return (
          `<g id="room-${number}" class="${state}" data-room="${room}" role="button" tabindex="0" aria-label="${label}" aria-pressed="${room === selectedRoom}">` +
          `<title>${label}</title>` +
          `<rect ${rectAttrs}/>` +
          `<text x="${x}" y="${Number(y) - 16}"${textAttrs}>${number}</text>` +
          `<text class="count" x="${x}" y="${Number(y) + 4}" font-size="11" text-anchor="middle" dominant-baseline="central">${seats} seats</text>` +
          `<text class="count" x="${x}" y="${Number(y) + 20}" font-size="11" text-anchor="middle" dominant-baseline="central">${classesText}</text>` +
          `</g>`
        );
      }),
  );

  function roomFromEvent(event) {
    return event.target.closest?.('[data-room]')?.dataset.room ?? null;
  }

  function handleClick(event) {
    const room = roomFromEvent(event);
    if (room) onselect?.(room);
  }

  function handleKeydown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const room = roomFromEvent(event);
    if (room) {
      event.preventDefault();
      onselect?.(room);
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="plan" onclick={handleClick} onkeydown={handleKeydown}>
  {@html markup}
</div>

<div class="legend">
  <span><i class="swatch booked"></i>Has classes</span>
  <span><i class="swatch empty"></i>Free all week</span>
  <span><i class="swatch selected"></i>Selected</span>
</div>

<style>
  .plan :global(svg) {
    display: block;
    width: 100%;
    height: auto;
  }

  .plan :global(.room) {
    cursor: pointer;
    outline: none;
  }

  .plan :global(.room rect) {
    transition: fill 120ms ease;
  }

  .plan :global(.room.booked rect) {
    fill: #dbe8f6;
  }

  .plan :global(.room.empty rect) {
    fill: #f4f4f4;
  }

  .plan :global(.room .count) {
    fill: #555;
  }

  .plan :global(.room:hover rect),
  .plan :global(.room:focus-visible rect) {
    fill: #b9d3ee;
  }

  .plan :global(.room:focus-visible rect) {
    stroke: #1f4e78;
    stroke-width: 3;
  }

  .plan :global(.room.selected rect) {
    fill: #1f4e78;
  }

  .plan :global(.room.selected text) {
    fill: #fff;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.25rem;
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: #444;
  }

  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }

  .swatch {
    display: inline-block;
    width: 0.9rem;
    height: 0.9rem;
    border: 1px solid #888;
  }

  .swatch.booked {
    background: #dbe8f6;
  }

  .swatch.empty {
    background: #f4f4f4;
  }

  .swatch.selected {
    background: #1f4e78;
  }
</style>
