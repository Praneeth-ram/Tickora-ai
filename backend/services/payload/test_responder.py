from backend.services.payload.test_builders import ATT  # reuse spec shape
from datetime import date
from backend.services.payload.builders import build_count
from backend.services.response_writer import check_numbers, narrate

START, END = date(2026, 11, 9), date(2026, 11, 15)
DRAFT = "You have 1 absent attendance record from 9 Nov 2026 to 15 Nov 2026."


def _payload():
    return build_count(ATT, 1, START, END, {"status": "absent"})


def test_accepts_answer_using_only_payload_numbers():
    fake = lambda *a, **k: "You were absent on 1 day between 9 and 15 November 2026."
    assert narrate("q", _payload(), DRAFT, generate=fake) == fake()


def test_rejects_invented_number_and_returns_draft():
    fake = lambda *a, **k: "You were absent on 3 days."
    assert narrate("q", _payload(), DRAFT, generate=fake) == DRAFT


def test_empty_candidate_returns_draft():
    fake = lambda *a, **k: "   "
    assert narrate("q", _payload(), DRAFT, generate=fake) == DRAFT


def test_generation_error_returns_draft():
    def boom(*a, **k):
        raise RuntimeError("gpu busy")
    assert narrate("q", _payload(), DRAFT, generate=boom) == DRAFT


def test_error_payload_skips_model():
    p = _payload()
    p["error"] = "query failed"
    called = []
    fake = lambda *a, **k: called.append(1) or "x"
    assert narrate("q", p, DRAFT, generate=fake) == DRAFT
    assert called == []


def test_number_normalisation():
    assert check_numbers("9.0 and 09", "9", "")
    assert not check_numbers("10", "9", "")