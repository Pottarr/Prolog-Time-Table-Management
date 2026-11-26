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

== Input `test.csv`:
#raw(read("./test/test.csv"),lang: "csv",block: true)

