import pytest
from pydantic import ValidationError
from backend.main import FeedbackRequest

def test_valid_feedback_is_accepted():
    item = FeedbackRequest(request_id="abcd1234efgh", rating="down", reason="wrong_number")
    assert item.rating == "down"

@pytest.mark.parametrize("rating", ["maybe", "UP", ""])
def test_unknown_rating_is_rejected(rating):
    with pytest.raises(ValidationError):
        FeedbackRequest(request_id="abcd1234efgh", rating=rating, reason="other")

def test_free_text_reason_is_rejected():
    with pytest.raises(ValidationError):
        FeedbackRequest(request_id="abcd1234efgh", rating="down", reason="Reyansh's salary is wrong")