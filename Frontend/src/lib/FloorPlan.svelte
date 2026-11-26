<script>
  // Clickable ECC 8th-floor plan, drawn from the real floor plan SVG
  // (./ecc-8th-floor.svg, landscape 814×499). It's turned 90° into portrait
  // so it fits the tall left rail with bigger rooms; every label is turned
  // back so text stays upright. The SVG ships with one `<g id="room-8NN">`
  // per classroom; those groups get data-room / state classes before the
  // markup is injected, so the file itself stays a plain drawing that can be
  // edited in any SVG tool. Toilets, lifts, stairs, P/S and corridors are
  // left as they are and aren't clickable.
  import floorPlanSvg from './ecc-8th-floor.svg?raw';

  // `flaggedRooms`: rooms holding a class that didn't get what it asked
  // for in the case on screen (drawn red).
  let { classes = [], capacities = null, selectedRoom = null, flaggedRooms = new Set(), onselect } = $props();

  const WIDTH = 814;
  const HEIGHT = 499;

  const ROOM_GROUP_RE =
    /<g id="room-(8\d\d)" class="space"><rect ([^>]*)\/><text x="([\d.]+)" y="([\d.]+)"([^>]*)>\d+<\/text><\/g>/g;

  // Turn a label back upright around its own anchor point.
  const upright = (x, y) => `transform="rotate(-90 ${x} ${y})"`;

  const countsByRoom = $derived(
    classes.reduce((counts, c) => counts.set(c.room, (counts.get(c.room) ?? 0) + 1), new Map()),
  );

  function roomGroup(number, rectAttrs, x, y, textAttrs) {
    const room = `ECC-${number}`;
    const loaded = capacities !== null;
    const count = countsByRoom.get(room) ?? 0;
    // Capacity 0 in the config = not a classroom (806 is the co-working space).
    const unused = loaded && capacities[room] === 0;
    const state = [
      'room',
      !loaded ? 'idle' : unused ? 'unused' : count > 0 ? 'booked' : 'empty',
      room === selectedRoom ? 'selected' : '',
      flaggedRooms.has(room) ? 'clash' : '',
    ].join(' ');
    const sub = !loaded ? '' : unused ? 'not used' : count === 0 ? 'free' : `${count} class${count === 1 ? '' : 'es'}`;
    const label = !loaded
      ? room
      : unused
        ? `${room}: not used for lectures`
        : `${room}: ${capacities[room]} seats, ${count === 0 ? 'no classes' : sub}${flaggedRooms.has(room) ? ', has a moved class' : ''}`;
    // In the turned plan, "up" on screen is towards smaller x in the
    // original drawing, so the number sits at x - 10 and the count at x + 14.
    const nx = Number(x) - (sub ? 10 : 0);
    const sx = Number(x) + 16;
    return (
      `<g id="room-${number}" class="${state}" data-room="${room}" role="button" tabindex="0" aria-label="${label}" aria-pressed="${room === selectedRoom}">` +
      `<title>${label}</title>` +
      `<rect ${rectAttrs}/>` +
      `<text class="num" x="${nx}" y="${y}"${textAttrs} ${upright(nx, y)}>${number}</text>` +
      (sub
        ? `<text class="sub" x="${sx}" y="${y}" text-anchor="middle" dominant-baseline="central" ${upright(sx, y)}>${sub}</text>`
        : '') +
      `</g>`
    );
  }

  const markup = $derived(
    floorPlanSvg
      .replace(/ viewBox="0 0 814 499" width="\d+" height="\d+"/, ` viewBox="0 0 ${HEIGHT} ${WIDTH}"`)
      // The paper background is sized in %, which would no longer cover the
      // drawing once it's turned; give it the drawing's own size instead.
      .replace('<rect width="100%" height="100%"', `<rect width="${WIDTH}" height="${HEIGHT}"`)
      // Turn every other label (M, W, L, P, S…) upright; "Window" already
      // carries its own rotation, which the turn makes horizontal.
      .replace(/<text x="([\d.]+)" y="([\d.]+)"(?![^>]*transform)/g, (m, x, y) => `${m} ${upright(x, y)}`)
      .replace(ROOM_GROUP_RE, (_, number, rectAttrs, x, y, textAttrs) =>
        roomGroup(number, rectAttrs, x, y, textAttrs.replace(/ transform="[^"]*"/, '')),
      )
      // Wrap the drawing in a 90° clockwise turn: (x, y) -> (HEIGHT - y, x).
      .replace(/(<svg[^>]*>)/, `$1<g transform="translate(${HEIGHT} 0) rotate(90)">`)
      .replace(/<\/svg>\s*$/, '</g></svg>'),
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

<style>
  .plan {
    height: 100%;
    min-height: 0;
    display: flex;
    justify-content: center;
  }

  .plan :global(svg) {
    display: block;
    height: 100%;
    width: auto;
    max-width: 100%;
  }

  /* Repaint the black-on-white drawing in the Desk Calendar palette. */
  .plan :global(svg > rect),
  .plan :global([fill='#fff']) {
    fill: var(--cream);
  }

  .plan :global([stroke='#000']) {
    stroke: var(--ink);
  }

  .plan :global([stroke='#fff']) {
    stroke: var(--cream);
  }

  .plan :global([stroke-width='6']),
  .plan :global([stroke-width='7']) {
    stroke-width: 3.5;
  }

  .plan :global(text) {
    font-family: var(--sans);
    fill: var(--sub);
  }

  .plan :global(.room) {
    cursor: pointer;
    outline: none;
  }

  .plan :global(.room rect) {
    fill: var(--cream);
    transition: fill 120ms ease;
  }

  .plan :global(.room .num) {
    font: 600 24px var(--serif);
    fill: var(--ink);
  }

  .plan :global(.room .sub) {
    font: 500 13px var(--sans);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    fill: var(--hair);
  }

  .plan :global(.room.booked .sub) {
    fill: var(--accent);
  }

  .plan :global(.room.clash .num),
  .plan :global(.room.clash .sub) {
    fill: var(--error);
  }

  .plan :global(.room.clash rect) {
    stroke: var(--error);
    stroke-width: 3;
  }

  .plan :global(.room.unused rect) {
    fill: var(--tan);
  }

  .plan :global(.room.unused .num) {
    fill: var(--hair);
  }

  .plan :global(.room:hover rect),
  .plan :global(.room:focus-visible rect) {
    fill: var(--hover);
  }

  .plan :global(.room:focus-visible rect) {
    stroke: var(--accent);
    stroke-width: 3;
  }

  .plan :global(.room.selected rect) {
    fill: var(--accent);
  }

  .plan :global(.room.selected text) {
    fill: var(--cream);
  }
</style>
