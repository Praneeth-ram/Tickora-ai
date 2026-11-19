from datetime import date

from backend.services.payload.shape import choose_shape, SHORT_LIST_MAX_DAYS


def test_single_day_list_is_single():
    assert choose_shape("attendance.list", date(2026, 11, 3), date(2026, 11, 3)) == "single"


def test_short_range_list_is_list_short():
    assert choose_shape("leave_request.list", date(2026, 11, 9), date(2026, 11, 15)) == "list_short"


def test_boundary_of_short_list():
    start = date(2026, 11, 1)
    end_ok = date.fromordinal(start.toordinal() + SHORT_LIST_MAX_DAYS - 1)
    end_long = date.fromordinal(start.toordinal() + SHORT_LIST_MAX_DAYS)
    assert choose_shape("attendance.list", start, end_ok) == "list_short"
    assert choose_shape("attendance.list", start, end_long) == "summary"


def test_long_range_list_is_summary():
    assert choose_shape("attendance.list", date(2026, 9, 1), date(2026, 11, 18)) == "summary"


def test_aggregates_keep_their_kind():
    assert choose_shape("attendance.count", date(2026, 11, 1), date(2026, 11, 18)) == "count"
    assert choose_shape("attendance.sum", date(2026, 11, 1), date(2026, 11, 18)) == "sum"
    assert choose_shape("attendance.group_by", date(2026, 11, 1), date(2026, 11, 18)) == "group_by"


def test_list_without_dates_is_list_short():
    # Leave balances and holidays with no date range fall back to a short list.
    assert choose_shape("leave_balance.list", None, None) == "list_short"


def test_unknown_operation_kind_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        choose_shape("attendance.delete", None, None)