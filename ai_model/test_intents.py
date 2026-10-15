from pydantic import ValidationError
from ai_model.intents import IntentRequest

def main():
    # Test 1: Valid attendance question
    request = IntentRequest.model_validate({
        "intent": "attendance_summary",
        "period": "this_month",
    })
    print("VALID:", request.model_dump(mode="json"))

    # Test 2: Valid leave-status question
    request = IntentRequest.model_validate({
        "intent": "leave_status",
        "status": "PENDING",
    })
    print("VALID:", request.model_dump(mode="json"))

    # Test 3: Invalid intent
    try:
        IntentRequest.model_validate({
            "intent": "delete_database",
        })
    except ValidationError as exc:
        print("\nEXPECTED VALIDATION ERROR:")
        print(exc.errors(include_url=False))

    # Test 4: Invalid date range
    try:
        IntentRequest.model_validate({
            "intent": "attendance_records",
            "period": "custom",
            "start_date": "2026-10-31",
            "end_date": "2026-10-01",
        })
    except ValidationError as exc:
        print("\nEXPECTED DATE ERROR:")
        print(exc.errors(include_url=False))


if __name__ == "__main__":
    main()
