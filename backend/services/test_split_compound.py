from datetime import date
from backend.services.llm_chat_service import (
    split_compound_question,
    resolve_date_range_from_question,
)

TODAY = date(2026, 11, 6)

def test_undated_clock_in_part_keeps_october_5():
    question = "Clock in and clock out on October 5 and is October 31 a holiday?"
    parts = split_compound_question(question)
    attendance = [p for p in parts if "clock" in p.lower()]
    assert len(attendance) == 2
    expected = resolve_date_range_from_question("clock out on October 5", TODAY)
    for part in attendance:
        assert resolve_date_range_from_question(part, TODAY) == expected

def test_holiday_part_keeps_its_own_date():
    parts = split_compound_question(
        "Clock in and clock out on October 5 and is October 31 a holiday?"
    )
    holiday = [p for p in parts if "holiday" in p.lower()][0]
    start, _ = resolve_date_range_from_question(holiday, TODAY)
    assert (start.month, start.day) == (10, 31)