#set page(
  paper: "a4",
  margin: (x: 1.5cm, y: 2cm),
  header: align(right)[
    #text(8pt, fill: luma(120))[Codebase Documentation]
  ],
  footer: [
    #align(center)[#text(8pt, fill: luma(120))[#context counter(page).display()]]
  ]
)
#set text(font: "Liberation Sans", size: 10pt)
#set par(justify: true)

== Test Case:

== Example of Valid Case:

== Input `test.csv`:
#raw(read("./test/Valid/test.csv"),lang: "csv",block: true)

== Input `config.json`:
#raw(read("./test/Valid/config.json"),lang: "json",block: true)

#for p in range(1, 10) {   // pages 1–5
  align(center + horizon)[
    #rotate(-90deg, reflow: true)[
      #image("./test/Valid/classroom-schedule-2026-s1-case1.pdf", page: p, height: 100%)
    ]
  ]
}

== Example of Valid Case:

== Input `26-cases-percent-levels.csv`:
#raw(read("./test/Invalid/26-cases-percent-levels.csv"),lang: "csv",block: true)

== Input `config-one-room.json`:
#raw(read("./test/Invalid/config-one-room.json"),lang: "json",block: true)
