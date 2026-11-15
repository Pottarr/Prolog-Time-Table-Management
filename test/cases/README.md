# Hand-test cases

Upload these in the frontend (or `curl` them at the gateway) to see each
rule pass or fail. Unless the **Config** column says otherwise, pair the
CSV with `test/config.json` (808/809 = 100 seats, 805 = 20, 806 = 0 — the
co-working space, not used for classes — and the rest = 50).

The same table is checked automatically by
`Backend/Gateway/tests/test_case_files.py`, so if you add or change a file
here, update that list too.

## Complete CSVs (auto-scheduling **off**)

| File | Config | Expected |
|---|---|---|
| `01-valid-full-week.csv` | default | ✅ Loads. Every class room (all but 806) used, Sun–Sat, morning and afternoon, sections in parentheses, a quoted title with a comma, 808/809 holding 95–100 students |
| `02-valid-boundaries.csv` | default | ✅ Loads. Students exactly at capacity, whole morning and whole afternoon, 1 student, same professor morning + afternoon, same course title twice with different professors |
| `03-over-capacity.csv` | default | ❌ `51 students don't fit in ECC-804 (capacity 50)` |
| `04-100-students-small-room.csv` | default | ❌ `100 students don't fit in ECC-807 (capacity 50)` — the professor's example: 100 students need 808/809 |
| `05-room-not-on-floor.csv` | default | ❌ `room 'ECC-502' isn't on the ECC 8th floor` |
| `06-past-afternoon.csv` | default | ❌ starts at 14:00 — `'start' must be 9 or 13` |
| `07-into-lunch.csv` | default | ❌ starts at 10:00, would run into lunch — `'start' must be 9 or 13` |
| `08-span-too-long.csv` | default | ❌ 4 hours — `'span' must be 3` |
| `09-two-classes-one-period.csv` | default | ❌ Two classes in 804's Monday morning — one class per period |
| `10-professor-clash.csv` | default | ❌ `Dr. Veera` and `dr.  veera` (same person) in two rooms the same morning |
| `11-bad-day.csv` | default | ❌ `Monday` instead of `Mon` |
| `12-missing-students.csv` | default | ❌ blank `students` |
| `13-old-six-columns.csv` | default | ❌ old header without `students` |
| `17-uses-big-801.csv` | default | ❌ 150 students in 801 (capacity 50) |
| `18-coworking-806.csv` | default | ❌ `ECC-806 isn't used for classes` — capacity 0 in the config |
| `20-short-class.csv` | default | ❌ a 1-hour class — `'span' must be 3` (every class is 3 hours) |
| `17-uses-big-801.csv` | `config-big-801.json` | ✅ Loads — same CSV, but this config gives 801 200 seats (and shows Semester 2 · 2027) |

## Config files

| File | CSV | Expected |
|---|---|---|
| `config-semester-3.json` | `01-valid-full-week.csv` | ❌ `Config 'semester' must be one of (1, 2)` |
| `config-missing-room.json` | `01-valid-full-week.csv` | ❌ `missing a capacity for: ECC-810` |

## Incomplete CSVs (auto-scheduling **on**)

| File | Config | Expected |
|---|---|---|
| `14-auto-valid.csv` | default | ✅ Prolog fills every blank: the 35-student class gets a 50-seat room, the 100-student class 808/809, fixed values kept |
| `15-auto-too-big-for-any-room.csv` | default | ❌ 150 students `don't fit in any room (largest capacity is 100)` |
| `16-auto-fixed-clash.csv` | default | ❌ Dr. A fixed twice in Monday morning — one class at a time |
| `19-auto-skips-806.csv` | default | ✅ 126 flexible classes fill all 9 class rooms × 14 periods exactly — nothing lands in 806 |
