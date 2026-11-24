import pytest
from backend.services.answer_writer import all_parts_covered
from backend.services.payload.answer_payload import merge_compound_facts
from backend.services.llm_chat_service import _combine_periods


def test_merged_facts_keep_order_and_entity():
    parts = [
        {"entity": "leave request", "kind": "count", "count": 0},
        {"entity": "attendance record", "kind": "count", "count": 22},
    ]
    merged = merge_compound_facts(
        period={"start_date": "2026-09-01", "end_date": "2026-10-31"},
        parts=parts,
    )
    assert merged["compound"] is True
    assert [p["entity"] for p in merged["parts"]] == [
        "leave request", "attendance record",
    ]
    assert [p["order"] for p in merged["parts"]] == [1, 2]


def test_coverage_rejects_reply_that_drops_a_part():
    parts = [
        {"entity": "leave request"},
        {"entity": "attendance record"},
    ]
    assert not all_parts_covered(
        "You have no leave requests in October 2026.", parts
    )
    assert all_parts_covered(
        "You have no leave requests. You have 22 attendance records.",
        parts,
    )


def test_same_entity_pair_keeps_each_figure():
    parts = [
        {"entity": "attendance record", "kind": "count", "count": 14},
        {"entity": "attendance record", "kind": "count", "count": 9},
    ]
    merged = merge_compound_facts(
        period={"start_date": "2026-09-01", "end_date": "2026-10-31"},
        parts=parts,
    )
    assert [p["count"] for p in merged["parts"]] == [14, 9]


def test_combined_period_spans_both_parts():
    results = [
        {"period": {"start_date": "2026-10-01", "end_date": "2026-10-31"}},
        {"period": {"start_date": "2026-09-01", "end_date": "2026-09-30"}},
    ]
    assert _combine_periods(results) == {
        "start_date": "2026-09-01",
        "end_date": "2026-10-31",
    }