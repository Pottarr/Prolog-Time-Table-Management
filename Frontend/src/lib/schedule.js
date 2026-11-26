// Shared schedule constants and helpers for the editor and the page.

export const ROOMS = Array.from({ length: 10 }, (_, i) => `ECC-8${String(i + 1).padStart(2, '0')}`);
export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const PERIOD_STARTS = [9, 13];
export const COLUMNS = ['room', 'day', 'start', 'span', 'title', 'prof', 'students'];

/** Professor names compare case- and whitespace-insensitively (as in the gateway). */
export const profKey = (prof) => (prof ?? '').trim().split(/\s+/).join(' ').toLowerCase();

/**
 * Time clashes between rows that fix both day and period: the same room,
 * or the same professor, twice in one period. Returns Map(rowIndex ->
 * { groups, with, messages }) for every clashing row.
 */
export function clashFlags(rows) {
  const groups = new Map();
  rows.forEach((row, i) => {
    if (!row.day || !PERIOD_STARTS.map(String).includes(String(row.start ?? ''))) return;
    const when = `${row.day}|${row.start}`;
    const add = (key, message) => {
      if (!groups.has(key)) groups.set(key, { message, rows: [] });
      groups.get(key).rows.push(i);
    };
    const period = String(row.start) === '9' ? 'morning' : 'afternoon';
    if (row.room) add(`room|${row.room}|${when}`, `${row.room} double-booked ${row.day} ${period}`);
    const prof = profKey(row.prof);
    if (prof) add(`prof|${prof}|${when}`, `${row.prof.trim()} teaches twice ${row.day} ${period}`);
  });

  const flags = new Map();
  for (const [key, group] of groups) {
    if (group.rows.length < 2) continue;
    for (const i of group.rows) {
      const flag = flags.get(i) ?? { groups: [], with: [], messages: [] };
      flag.groups.push(key);
      flag.messages.push(group.message);
      for (const j of group.rows) if (j !== i && !flag.with.includes(j)) flag.with.push(j);
      flags.set(i, flag);
    }
  }
  return flags;
}

const cell = (value) => {
  if (value === null || value === undefined || String(value).trim() === '') return 'NULL';
  const text = String(value).trim();
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

/** Editor rows (null = flexible) back to a schedule CSV. */
export function rowsToCsv(rows) {
  return [COLUMNS.join(','), ...rows.map((row) => COLUMNS.map((c) => cell(row[c])).join(','))].join('\n') + '\n';
}
