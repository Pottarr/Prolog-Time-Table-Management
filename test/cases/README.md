# Hand-test cases

Upload these in the frontend (or `curl` them at the gateway) to see each
rule pass or fail. Unless the **Config** column says otherwise, pair the
CSV with `test/config.json` (808/809 = 120 seats, 806/807 = 60, 805 = 30,
the rest = 40).

The same table is checked automatically by
`Backend/Gateway/tests/test_case_files.py`, so if you add or change a file
here, update that list too.

## Complete CSVs (auto-scheduling **off**)

| File | Config | Expected |
|---|---|---|
| `01-valid-full-week.csv` | default | ✅ Loads. Every room used, Sun–Sat, morning and afternoon, sections in parentheses, a quoted title with a comma, 808/809 holding 110–120 students |
| `02-valid-boundaries.csv` | default | ✅ Loads. Students exactly at capacity, class ending right at 12:00 / 16:00, same professor morning + afternoon, same course title twice with different professors |
| `03-over-capacity.csv` | default | ❌ `41 students don't fit in ECC-804 (capacity 40)` |
| `04-100-students-small-room.csv` | default | ❌ `100 students don't fit in ECC-806 (capacity 60)` — the professor's example: 100 students need 808/809 |
| `05-room-not-on-floor.csv` | default | ❌ `room 'ECC-502' isn't on the ECC 8th floor` |
| `06-past-afternoon.csv` | default | ❌ 14:00 for 3h ends at 17:00 — doesn't fit inside one period |
| `07-into-lunch.csv` | default | ❌ 11:00 for 2h runs into lunch — doesn't fit inside one period |
| `08-span-too-long.csv` | default | ❌ `'span' must be 1–3 hours` |
| `09-two-classes-one-period.csv` | default | ❌ Two 1-hour classes in 804's Monday morning — one class per period |
| `10-professor-clash.csv` | default | ❌ `Dr. Veera` and `dr.  veera` (same person) in two rooms the same morning |
| `11-bad-day.csv` | default | ❌ `Monday` instead of `Mon` |
| `12-missing-students.csv` | default | ❌ blank `students` |
| `13-old-six-columns.csv` | default | ❌ old header without `students` |
| `17-uses-big-801.csv` | default | ❌ 150 students in 801 (capacity 40) |
| `17-uses-big-801.csv` | `config-big-801.json` | ✅ Loads — same CSV, but this config gives 801 200 seats (and shows Semester 2 · 2027) |

## Config files

| File | CSV | Expected |
|---|---|---|
| `config-semester-3.json` | `01-valid-full-week.csv` | ❌ `Config 'semester' must be one of (1, 2)` |
| `config-missing-room.json` | `01-valid-full-week.csv` | ❌ `missing a capacity for: ECC-810` |

## Incomplete CSVs (auto-scheduling **on**)

| File | Config | Expected |
|---|---|---|
| `14-auto-valid.csv` | default | ✅ Prolog fills every blank: the 35-student class gets a 40-seat room, the 100-student class 808/809, fixed values kept |
| `15-auto-too-big-for-any-room.csv` | default | ❌ 150 students `don't fit in any room (largest capacity is 120)` |
| `16-auto-fixed-clash.csv` | default | ❌ Dr. A fixed twice in Monday morning — one class at a time |
