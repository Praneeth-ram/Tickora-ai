from datetime import date
from backend.services.llm_chat_service import apply_session_topic


def test_short_follow_up_inherits_topic():
    assert apply_session_topic("and for September?", "leave") == "and for September leave"


def test_question_with_its_own_topic_is_not_changed():
    assert apply_session_topic("show my payroll for June", "leave") == "show my payroll for June"


def test_no_memory_means_no_change():
    assert apply_session_topic("and for September?", None) == "and for September?"