from backend.agents.nodes import supervisor_node


def test_write_requests_are_refused():
    for question in [
        "Delete my attendance for October",
        "Please cancel my leave request",
        "Approve my WFH request",
        "Can you update my timesheet",
    ]:
        assert supervisor_node({"question": question})["request_type"] == "write_request"


def test_read_questions_are_not_refused():
    for question in [
        "Show my leave requests",
        "Was my leave approved?",
        "What is my leave balance?",
        "Show my cancelled leave requests",
    ]:
        assert supervisor_node({"question": question}).get("request_type") != "write_request"