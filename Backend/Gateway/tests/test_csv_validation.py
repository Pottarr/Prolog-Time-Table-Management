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


@pytest.mark.parametrize("room", [f"ECC-8{n:02d}" for n in range(1, 11)])
def test_all_ten_rooms_are_accepted(capacities, room):
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


@pytest.mark.parametrize(
    "start,span,period",
    [
        (9, 3, "morning"),  # whole morning
        (9, 1, "morning"),
        (10, 2, "morning"),
        (11, 1, "morning"),  # ends exactly at lunch
        (13, 3, "afternoon"),  # whole afternoon
        (14, 2, "afternoon"),
        (15, 1, "afternoon"),  # ends exactly at 16:00
    ],
)
def test_class_inside_one_period(capacities, start, span, period):
    [row] = ok(capacities, f"ECC-804,Mon,{start},{span},A,Dr. X,10")
    assert row["period"] == period


@pytest.mark.parametrize(
    "start,span",
    [
        (8, 1),  # before the morning
        (8, 3),
        (11, 2),  # runs into lunch
        (10, 3),
        (12, 1),  # lunch itself
        (14, 3),  # past 16:00
        (15, 2),
        (16, 1),  # after the afternoon
        (17, 1),
        (18, 1),
    ],
)
def test_class_outside_a_period(capacities, start, span):
    rejected(capacities, f"ECC-804,Mon,{start},{span},A,Dr. X,10", match="doesn't fit")


@pytest.mark.parametrize("span", [0, -1, 4, 9])
def test_span_out_of_range(capacities, span):
    rejected(capacities, f"ECC-804,Mon,9,{span},A,Dr. X,10", match="'span' must be 1–3")


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
        "ECC-804,Mon,9,1,A,Dr. X,10",
        "ECC-804,Mon,10,2,B,Dr. Y,10",
        match="ECC-804 already has a morning class on Mon",
    )


def test_short_class_still_takes_the_whole_period(capacities):
    rejected(
        capacities,
        "ECC-804,Mon,9,1,A,Dr. X,10",
        "ECC-804,Mon,11,1,B,Dr. Y,10",
        match="one class per period",
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


def test_professor_clash_with_non_overlapping_hours_same_period(capacities):
    rejected(
        capacities,
        "ECC-801,Mon,9,1,A,Dr. X,10",
        "ECC-802,Mon,10,2,B,Dr. X,10",
        match="one class at a time",
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
    [("ECC-804", 40), ("ECC-805", 30), ("ECC-808", 120), ("ECC-809", 100), ("ECC-801", 1)],
)
def test_students_within_capacity(capacities, room, students):
    ok(capacities, f"{room},Mon,9,3,A,Dr. X,{students}")


@pytest.mark.parametrize(
    "room,students,capacity",
    [("ECC-804", 41, 40), ("ECC-805", 31, 30), ("ECC-806", 100, 60), ("ECC-808", 121, 120)],
)
def test_students_over_capacity(capacities, room, students, capacity):
    rejected(
        capacities,
        f"{room},Mon,9,3,A,Dr. X,{students}",
        match=rf"{students} students don't fit in {room} \(capacity {capacity}\)",
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
    ("NULL,NULL,NULL,4,A,Dr. X,10", "'span' must be 1–3"),
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


@pytest.mark.parametrize("start,span", [(14, 3), (11, 2), (12, 1), (16, 1)])
def test_partial_fixed_start_must_fit_a_period(capacities, start, span):
    partial_rejected(capacities, f"NULL,NULL,{start},{span},A,Dr. X,10", match="doesn't fit")


def test_partial_fixed_room_too_small(capacities):
    partial_rejected(
        capacities,
        "ECC-805,NULL,NULL,3,A,Dr. X,31",
        match=r"31 students don't fit in ECC-805 \(capacity 30\)",
    )


def test_partial_flexible_room_needs_some_room_big_enough(capacities):
    partial_ok(capacities, "NULL,NULL,NULL,3,A,Dr. X,120")
    partial_rejected(
        capacities,
        "NULL,NULL,NULL,3,A,Dr. X,121",
        match=r"don't fit in any room \(largest capacity is 120\)",
    )


def test_partial_professor_clash_between_fixed_rows(capacities):
    partial_rejected(
        capacities,
        "NULL,Mon,9,3,A,Dr. X,10",
        "ECC-803,Mon,10,2,B,Dr. X,10",
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
        "ECC-804,Mon,10,1,B,Dr. Y,10",
        match="ECC-804 already has a morning class on Mon",
    )


@pytest.mark.parametrize("second", [
    "NULL,Mon,9,3,B,Dr. Y,10",  # room flexible
    "ECC-804,NULL,9,3,B,Dr. Y,10",  # day flexible
    "ECC-804,Mon,NULL,3,B,Dr. Y,10",  # start flexible
])
def test_partial_room_flexible_rows_left_to_prolog(capacities, second):
    assert len(partial_ok(capacities, "ECC-804,Mon,9,3,A,Dr. X,10", second)) == 2
