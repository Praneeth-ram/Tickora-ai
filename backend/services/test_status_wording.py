from datetime import date

from backend.services.llm_chat_service import _latest_request_sentence


def test_latest_pending_request_uses_start_date_and_is_pending():
    rows = [
        {"start_date": date(2025, 5, 8), "end_date": date(2025, 5, 8), "status": "rejected"},
        {"start_date": date(2025, 8, 13), "end_date": date(2025, 8, 13), "status": "pending"},
    ]
    assert _latest_request_sentence("leave", rows) == (
        "Your latest leave request, starting 13 August 2025, is pending."
    )


def test_decided_request_uses_was():
    rows = [{"start_date": date(2025, 5, 8), "end_date": date(2025, 5, 8), "status": "approved"}]
    assert _latest_request_sentence("wfh", rows) == (
        "Your latest work-from-home request, starting 8 May 2025, was approved."
    )