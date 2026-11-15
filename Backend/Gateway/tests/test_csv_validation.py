import pytest

from app.csv_validation import (
    CsvValidationError,
    parse_partial_schedule_csv,
    validate_schedule_csv,
)
from tests.conftest import TEST_DATA_DIR, make_csv


def ok(capacities, *rows):
    return validate_schedule_csv(make_csv(*rows), capacities)


def rejected(capacities, *rows, match):
    with pytest.raises(CsvValidationError, match=match):
        validate_schedule_csv(make_csv(*rows), capacities)


# ---------------------------------------------------------------- samples


def test_sample_complete_csv_is_valid(capacities):
    raw = (TEST_DATA_DIR / "schedule-complete.csv").read_bytes()
    assert len(validate_schedule_csv(raw, capacities)) == 9


def test_sample_incomplete_csv_is_valid(capacities):
    raw = (TEST_DATA_DIR / "schedule-incomplete.csv").read_bytes()
    assert len(parse_partial_schedule_csv(raw, capacities)) == 4


def test_parsed_row_shape(capacities):
    [row] = ok(capacities, "ECC-804,Mon,13,3,Artificial Intelligence,Dr. Visit,40")
    assert row == {
        "room": "ECC-804",
        "day": "Mon",
        "start": 13,
        "span": 3,
        "period": "afternoon",
        "title": "Artificial Intelligence",
        "prof": "Dr. Visit",
        "students": 40,
    }


# ------------------------------------------------------- file / structure


def test_old_six_column_header_is_rejected(capacities):
    raw = b"room,day,start,span,title,prof\nECC-804,Mon,9,3,A,Dr. X\n"
    with pytest.raises(CsvValidationError, match="header must be exactly"):
        validate_schedule_csv(raw, capacities)


def test_reordered_header_is_rejected(capacities):
    raw = b"room,day,start,span,title,students,prof\nECC-804,Mon,9,3,A,10,Dr. X\n"
    with pytest.raises(CsvValidationError, match="header must be exactly"):
        validate_schedule_csv(raw, capacities)


def test_header_only_is_rejected(capacities):
    rejected(capacities, match="no data rows")


def test_empty_file_is_rejected(capacities):
    with pytest.raises(CsvValidationError):
        validate_schedule_csv(b"", capacities)


def test_non_utf8_is_rejected(capacities):
    raw = make_csv("ECC-804,Mon,9,3,Caf\xe9,Dr. X,10").decode().encode("latin-1")
    with pytest.raises(CsvValidationError, match="UTF-8"):
        validate_schedule_csv(raw, capacities)


def test_utf8_bom_is_accepted(capacities):
    raw = b"\xef\xbb\xbf" + make_csv("ECC-804,Mon,9,3,A,Dr. X,10")
    assert len(validate_schedule_csv(raw, capacities)) == 1


def test_thai_text_is_accepted(capacities):
    [row] = ok(capacities, "ECC-804,Mon,9,3,วิศวกรรมซอฟต์แวร์,อ. วีระ,10")
    assert row["prof"] == "อ. วีระ"


# ---------------------------------------------------------- required fields


@pytest.mark.parametrize(
    "row",
    [
        ",Mon,9,3,A,Dr. X,10",  # no room
        "ECC-804,Mon,9,3,,Dr. X,10",  # no title
        "ECC-804,Mon,9,3,A,,10",  # no prof
    ],
)
def test_room_title_prof_required(capacities, row):
    rejected(capacities, row, match="required")


# ------------------------------------------------------------------- rooms


@pytest.mark.parametrize("room", [f"ECC-8{n:02d}" for n in range(1, 11) if n != 6])
def test_all_nine_class_rooms_are_accepted(capacities, room):
    ok(capacities, f"{room},Mon,9,3,A,Dr. X,10")


@pytest.mark.parametrize("room", ["ECC-502", "ECC-811", "ECC-800", "ecc-804", "804", "ECC-P"])
def test_room_not_on_the_floor(capacities, room):
    rejected(capacities, f"{room},Mon,9,3,A,Dr. X,10", match="isn't on the ECC 8th floor")


# -------------------------------------------------------------------- days


@pytest.mark.parametrize("day", ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
def test_every_day_sun_to_sat_is_accepted(capacities, day):
    ok(capacities, f"ECC-804,{day},9,3,A,Dr. X,10")


@pytest.mark.parametrize("day", ["Monday", "mon", "MON", "M", "", "NULL"])
def test_bad_day(capacities, day):
    rejected(capacities, f"ECC-804,{day},9,3,A,Dr. X,10", match="'day' must be one of")


# ------------------------------------------------------- periods and hours


@pytest.mark.parametrize("start,period", [(9, "morning"), (13, "afternoon")])
def test_class_fills_a_whole_period(capacities, start, period):
    [row] = ok(capacities, f"ECC-804,Mon,{start},3,A,Dr. X,10")
    assert row["period"] == period


@pytest.mark.parametrize("start", [8, 10, 11, 12, 14, 15, 16, 17, 18])
def test_start_must_be_9_or_13(capacities, start):
    rejected(capacities, f"ECC-804,Mon,{start},3,A,Dr. X,10", match="'start' must be 9 or 13")


@pytest.mark.parametrize("span", [1, 2, 4, 0, -1, 9])
def test_span_must_be_3(capacities, span):
    rejected(capacities, f"ECC-804,Mon,9,{span},A,Dr. X,10", match="'span' must be 3")


@pytest.mark.parametrize("field,row", [
    ("start", "ECC-804,Mon,9.5,3,A,Dr. X,10"),
    ("start", "ECC-804,Mon,,3,A,Dr. X,10"),
    ("start", "ECC-804,Mon,NULL,3,A,Dr. X,10"),
    ("span", "ECC-804,Mon,9,three,A,Dr. X,10"),
    ("span", "ECC-804,Mon,9,,A,Dr. X,10"),
])
def test_start_and_span_must_be_integers(capacities, field, row):
    rejected(capacities, row, match=f"'{field}' must be an integer")


# --------------------------------------------------- one class per room/period


def test_two_classes_in_one_room_period(capacities):
    rejected(
        capacities,
        "ECC-804,Mon,9,3,A,Dr. X,10",
        "ECC-804,Mon,9,3,B,Dr. Y,10",
        match="ECC-804 already has a morning class on Mon",
    )


def test_morning_and_afternoon_in_one_room(capacities):
    assert len(ok(capacities, "ECC-804,Mon,9,3,A,Dr. X,10", "ECC-804,Mon,13,3,B,Dr. Y,10")) == 2


def test_same_period_different_rooms(capacities):
    assert len(ok(capacities, "ECC-803,Mon,9,3,A,Dr. X,10", "ECC-804,Mon,9,3,B,Dr. Y,10")) == 2


def test_same_room_period_different_days(capacities):
    assert len(ok(capacities, "ECC-804,Mon,9,3,A,Dr. X,10", "ECC-804,Tue,9,3,B,Dr. Y,10")) == 2


def test_room_full_every_period_of_the_week(capacities):
    rows = [
        f"ECC-804,{day},{start},3,Class {day} {start},Dr. {day}{start},10"
        for day in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
        for start in (9, 13)
    ]
    assert len(ok(capacities, *rows)) == 14


# ------------------------------------------------------------ professors


def test_professor_in_two_rooms_same_period(capacities):
    rejected(
        capacities,
        "ECC-801,Mon,9,3,A,Dr. X,10",
        "ECC-802,Mon,9,3,B,Dr. X,10",
        match="Dr. X already teaches a morning class on Mon",
    )


@pytest.mark.parametrize("other_name", ["dr. x", "DR. X", "  Dr.   X  "])
def test_professor_names_ignore_case_and_spaces(capacities, other_name):
    rejected(
        capacities,
        "ECC-801,Mon,9,3,A,Dr. X,10",
        f"ECC-802,Mon,9,3,B,{other_name},10",
        match="one class at a time",
    )


def test_professor_morning_and_afternoon(capacities):
    assert len(ok(capacities, "ECC-801,Mon,9,3,A,Dr. X,10", "ECC-802,Mon,13,3,B,Dr. X,10")) == 2


def test_professor_same_period_different_days(capacities):
    assert len(ok(capacities, "ECC-801,Mon,9,3,A,Dr. X,10", "ECC-801,Tue,9,3,B,Dr. X,10")) == 2


def test_different_professors_same_name_prefix(capacities):
    assert len(ok(capacities, "ECC-801,Mon,9,3,A,Dr. X,10", "ECC-802,Mon,9,3,B,Dr. Xavier,10")) == 2


# ------------------------------------------------- sections / duplicate titles


def test_same_course_twice_is_allowed(capacities):
    rows = ok(
        capacities,
        "ECC-801,Mon,9,3,Algorithms,Dr. X,40",
        "ECC-802,Mon,9,3,Algorithms,Dr. Y,40",
    )
    assert [r["title"] for r in rows] == ["Algorithms", "Algorithms"]


def test_section_notes_in_parentheses(capacities):
    rows = ok(
        capacities,
        "ECC-801,Mon,9,3,Algorithms (Section 1),Dr. X,40",
        '"ECC-802",Mon,9,3,"Algorithms (Section 2, English program)",Dr. Y,40',
    )
    assert rows[1]["title"] == "Algorithms (Section 2, English program)"


def test_exact_duplicate_row_clashes(capacities):
    row = "ECC-801,Mon,9,3,Algorithms,Dr. X,40"
    rejected(capacities, row, row, match="already has a morning class")


# --------------------------------------------------------------- capacity


@pytest.mark.parametrize(
    "room,students",
    [("ECC-804", 50), ("ECC-805", 20), ("ECC-808", 100), ("ECC-809", 100), ("ECC-801", 1)],
)
def test_students_within_capacity(capacities, room, students):
    ok(capacities, f"{room},Mon,9,3,A,Dr. X,{students}")


@pytest.mark.parametrize(
    "room,students,capacity",
    [("ECC-804", 51, 50), ("ECC-805", 21, 20), ("ECC-807", 100, 50), ("ECC-808", 101, 100)],
)
def test_students_over_capacity(capacities, room, students, capacity):
    rejected(
        capacities,
        f"{room},Mon,9,3,A,Dr. X,{students}",
        match=rf"{students} students don't fit in {room} \(capacity {capacity}\)",
    )


@pytest.mark.parametrize("students", [1, 10])
def test_room_with_capacity_zero_is_not_used_for_classes(capacities, students):
    rejected(
        capacities,
        f"ECC-806,Mon,9,3,A,Dr. X,{students}",
        match=r"ECC-806 isn't used for classes \(capacity 0",
    )


def test_partial_fixed_room_with_capacity_zero(capacities):
    partial_rejected(
        capacities, "ECC-806,NULL,NULL,3,A,Dr. X,5", match="ECC-806 isn't used for classes"
    )


def test_capacity_follows_the_config(capacities):
    capacities["ECC-801"] = 200
    ok(capacities, "ECC-801,Mon,9,3,A,Dr. X,150")


@pytest.mark.parametrize("students", ["", "0", "-3", "12.5", "many", "NULL"])
def test_bad_students(capacities, students):
    rejected(capacities, f"ECC-804,Mon,9,3,A,Dr. X,{students}", match="'students' must")


# --------------------------------------------------------- error reporting


def test_error_names_the_failing_row(capacities):
    rejected(
        capacities,
        "ECC-804,Mon,9,3,A,Dr. X,10",
        "ECC-804,Tue,9,3,B,Dr. Y,10",
        "ECC-804,Wed,9,3,C,Dr. Z,99",
        match="^Row 4:",
    )


# =========================================================== auto (partial)


def partial_ok(capacities, *rows):
    return parse_partial_schedule_csv(make_csv(*rows), capacities)


def partial_rejected(capacities, *rows, match):
    with pytest.raises(CsvValidationError, match=match):
        parse_partial_schedule_csv(make_csv(*rows), capacities)


@pytest.mark.parametrize("blank", ["", "NULL", "null", "  NULL  "])
def test_partial_blank_or_null_means_flexible(capacities, blank):
    [row] = partial_ok(capacities, f"{blank},{blank},{blank},3,A,Dr. X,10")
    assert (row["room"], row["day"], row["start"]) == (None, None, None)


def test_partial_fully_fixed_row(capacities):
    [row] = partial_ok(capacities, "ECC-804,Mon,9,3,A,Dr. X,10")
    assert (row["room"], row["day"], row["start"]) == ("ECC-804", "Mon", 9)


@pytest.mark.parametrize("row,match", [
    ("NULL,NULL,NULL,,A,Dr. X,10", "'span' must be an integer"),
    ("NULL,NULL,NULL,NULL,A,Dr. X,10", "'span' must be an integer"),
    ("NULL,NULL,NULL,4,A,Dr. X,10", "'span' must be 3"),
    ("NULL,NULL,NULL,1,A,Dr. X,10", "'span' must be 3"),
    ("NULL,NULL,NULL,3,,Dr. X,10", "'title' and 'prof' are required"),
    ("NULL,NULL,NULL,3,A,,10", "'title' and 'prof' are required"),
    ("NULL,NULL,NULL,3,A,Dr. X,", "'students' must"),
    ("NULL,NULL,NULL,3,A,Dr. X,NULL", "'students' must"),
    ("NULL,Monday,NULL,3,A,Dr. X,10", "'day' must be blank/NULL"),
    ("NULL,NULL,nine,3,A,Dr. X,10", "'start' must be blank/NULL or an integer"),
    ("ECC-502,NULL,NULL,3,A,Dr. X,10", "isn't on the ECC 8th floor"),
])
def test_partial_invalid_rows(capacities, row, match):
    partial_rejected(capacities, row, match=match)


@pytest.mark.parametrize("start", [10, 11, 12, 14, 16])
def test_partial_fixed_start_must_be_9_or_13(capacities, start):
    partial_rejected(capacities, f"NULL,NULL,{start},3,A,Dr. X,10", match="'start' must be 9 or 13")


def test_partial_fixed_room_too_small(capacities):
    partial_rejected(
        capacities,
        "ECC-805,NULL,NULL,3,A,Dr. X,21",
        match=r"21 students don't fit in ECC-805 \(capacity 20\)",
    )


def test_partial_flexible_room_needs_some_room_big_enough(capacities):
    partial_ok(capacities, "NULL,NULL,NULL,3,A,Dr. X,100")
    partial_rejected(
        capacities,
        "NULL,NULL,NULL,3,A,Dr. X,101",
        match=r"don't fit in any room \(largest capacity is 100\)",
    )


def test_partial_professor_clash_between_fixed_rows(capacities):
    partial_rejected(
        capacities,
        "NULL,Mon,9,3,A,Dr. X,10",
        "ECC-803,Mon,9,3,B,Dr. X,10",
        match="one class at a time",
    )


@pytest.mark.parametrize("second", [
    "ECC-803,NULL,9,3,B,Dr. X,10",  # day flexible
    "ECC-803,Mon,NULL,3,B,Dr. X,10",  # start flexible
])
def test_partial_professor_flexible_rows_left_to_prolog(capacities, second):
    assert len(partial_ok(capacities, "NULL,Mon,9,3,A,Dr. X,10", second)) == 2


def test_partial_room_clash_between_fixed_rows(capacities):
    partial_rejected(
        capacities,
        "ECC-804,Mon,9,3,A,Dr. X,10",
        "ECC-804,Mon,9,3,B,Dr. Y,10",
        match="ECC-804 already has a morning class on Mon",
    )


@pytest.mark.parametrize("second", [
    "NULL,Mon,9,3,B,Dr. Y,10",  # room flexible
    "ECC-804,NULL,9,3,B,Dr. Y,10",  # day flexible
    "ECC-804,Mon,NULL,3,B,Dr. Y,10",  # start flexible
])
def test_partial_room_flexible_rows_left_to_prolog(capacities, second):
    assert len(partial_ok(capacities, "ECC-804,Mon,9,3,A,Dr. X,10", second)) == 2
