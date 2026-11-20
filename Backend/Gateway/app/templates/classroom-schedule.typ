// Classroom weekly schedule — A4 landscape
// Compile with: typst compile classroom-schedule.typ

#set page(
  paper: "a4",
  flipped: true,
  margin: (x: 10mm, y: 8mm),
)

#set text(font: "New Computer Modern", size: 9pt)
#set par(leading: 0.45em)

// ---------- Edit these values ----------
#let header = json("header.json")

// Morning period 09–12, lunch, afternoon period 13–16. Columns are 1fr,
// so these seven slots stretch to fill the page width.
#let time-slots = (
  "09:00–10:00",
  "10:00–11:00",
  "11:00–12:00",
  "12:00–13:00",
  "13:00–14:00",
  "14:00–15:00",
  "15:00–16:00",
)
#let time-starts = range(9, 16)

// Load all classes from schedule.csv.
// CSV columns: room,day,start,span,title,prof,students
// header.json: semester, academic_year, capacities (room -> seats).
// Every room that can hold classes (capacity > 0) gets its own page, in room
// order (ECC-801 first) — even with no classes, so the sheet on its door shows
// it free. Rooms not used for lectures (capacity 0, e.g. 806) get none.
// `start` is 9 (morning) or 13 (afternoon) and `span` is 3 hours.
// Use three-letter day codes: Mon, Tue, Wed, Thu, Fri, Sat, Sun.
// Example: ECC-804,Mon,9,3,Software Engineering,... means 09:00–12:00.
#let csv-rows = csv("schedule.csv", row-type: dictionary)
#let rooms = (
  header.capacities.pairs()
    .filter(((room, seats)) => seats > 0)
    .map(((room, seats)) => room)
    .sorted()
)
#let day-names = (
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
)
#let day-codes = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#let make-schedule(room-number) = {
  day-names.enumerate().map(((day-index, day)) => (
    day: day,
    blocks: csv-rows
      .filter(row => row.room == room-number and row.day == day-codes.at(day-index))
      .map(row => {
        let start-hour = int(row.start)
        let start-index = time-starts.position(hour => hour == start-hour)
        assert(
          start-index != none and start-hour != 12,
          message: "CSV start must be 9–11 or 13–15; 12 is reserved for lunch.",
        )
        (
          start: start-index,
          span: int(row.span),
          title: row.title,
          prof: row.prof,
          students: row.students,
        )
      }),
  ))
}
// ---------- End of editable values ----------

// #let header-fill = rgb("#1f4e78")
#let header-fill = rgb("#aaaaaa")
// #let day-fill = rgb("#d9eaf7")
#let day-fill = rgb("#bbbbbb")
// #let occupied-fill = rgb("#fff2cc")
#let occupied-fill = rgb("eeeeee")
// #let free-fill = rgb("#f7f7f7")
#let free-fill = rgb("#ffffff")
// #let lunch-fill = rgb("#d9ead3")
#let lunch-fill = rgb("#dddddd")
#let lunch-index = 3

// Produce explicitly positioned cells so multi-hour classes can use colspan.
#let schedule-cells(schedule) = {
  let cells = ()

  for (row-index, entry) in schedule.enumerate() {
    let table-row = row-index + 1
    let occupied = ()

    for block in entry.blocks {
      assert(
        block.start >= 0 and block.span >= 1
          and block.start + block.span <= time-slots.len(),
        message: "A CSV class has an invalid start or span.",
      )
      assert(
        not (block.start <= lunch-index
          and lunch-index < block.start + block.span),
        message: "A CSV class overlaps the fixed 12:00–13:00 lunch period.",
      )
      for slot in range(block.start, block.start + block.span) {
        assert(
          not occupied.contains(slot),
          message: "Two CSV classes overlap on the same day.",
        )
        occupied.push(slot)
      }
    }

    cells.push(table.cell(x: 0, y: table-row, fill: day-fill)[
      #text(weight: "bold")[#entry.day]
    ])

    for slot-index in range(time-slots.len()) {
      if slot-index == lunch-index {
        cells.push(table.cell(
          x: slot-index + 1,
          y: table-row,
          fill: lunch-fill,
        )[#text(weight: "bold", size: 8pt)[Lunch]])
      } else if not occupied.contains(slot-index) {
        cells.push(table.cell(
          x: slot-index + 1,
          y: table-row,
          fill: free-fill,
        )[#text(fill: rgb("#aaaaaa"))[—]])
      }
    }

    for block in entry.blocks {
      cells.push(table.cell(
        x: block.start + 1,
        y: table-row,
        colspan: block.span,
        fill: occupied-fill,
      )[
        #text(weight: "medium", size: 9pt)[#block.title]
        #linebreak()
        #text(fill: rgb("#555555"), size: 8pt)[#block.prof · #block.students students]
      ])
    }
  }

  cells
}

#let render-room(room-number) = {
  let schedule = make-schedule(room-number)

  align(center)[
    #text(size: 20pt, weight: "bold")[Classroom #room-number]
    #v(2pt)
    #text(size: 10pt, fill: rgb("#555555"))[
      Semester #header.semester · Academic Year #header.academic_year ·
      Capacity #header.capacities.at(room-number) seats
    ]
  ]

  v(5pt)

  block(breakable: false)[
    #table(
      columns: (25mm,) + (1fr,) * time-slots.len(),
      rows: (12mm,) + (20mm,) * schedule.len(),
      inset: 2.5pt,
      align: (center + horizon),
      stroke: 0.6pt + rgb("#808080"),

      table.cell(x: 0, y: 0, fill: header-fill)[
        #text(fill: white, weight: "bold")[Day / Time]
      ],
      ..time-slots.enumerate().map(((index, slot)) => table.cell(
        x: index + 1,
        y: 0,
        fill: header-fill,
      )[#text(fill: white, weight: "bold", size: 8.5pt)[#slot]]),
      ..schedule-cells(schedule),
    )
  ]

  v(4pt)
  align(right)[
    #text(size: 7pt, fill: rgb("#666666"))[
      Grey = occupied · Darker grey = lunch · Dash = available
    ]
  ]
}

#for (index, room) in rooms.enumerate() {
  render-room(room)
  if index < rooms.len() - 1 { pagebreak() }
}
