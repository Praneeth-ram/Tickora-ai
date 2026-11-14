import io
import logging

import pytest

from backend.security.log_redaction import (
    PiiRedactionFilter,
    clear_names,
    mask_text,
    register_names,
)


@pytest.fixture
def capture():
    clear_names()
    register_names(["Reyansh Verma"])
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(PiiRedactionFilter())
    logger = logging.getLogger("test.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.handlers = []
    clear_names()


def test_employee_code_and_name_are_masked(capture):
    logger, stream = capture
    logger.warning("Access check for EMP011 Reyansh Verma on payroll")
    output = stream.getvalue()
    assert "EMP011" not in output
    assert "Reyansh Verma" not in output
    assert "[employee]" in output
    assert "[name]" in output


def test_arguments_are_masked(capture):
    logger, stream = capture
    logger.info("Lookup for %s", "EMP011")
    assert "EMP011" not in stream.getvalue()


def test_traceback_is_masked(capture):
    logger, stream = capture
    try:
        raise ValueError("bad row for EMP011")
    except ValueError:
        logger.exception("Query failed")
    assert "EMP011" not in stream.getvalue()


def test_non_identifying_text_is_unchanged():
    clear_names()
    assert mask_text("Model plan in 0.42s") == "Model plan in 0.42s"


def test_short_names_are_not_registered():
    clear_names()
    register_names(["Al"])
    assert mask_text("Al asked") == "Al asked"
    clear_names()

def test_uvicorn_style_args_keep_arity(capture):
    logger, stream = capture
    logger.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "POST", "/api/chat/EMP011", "1.1", 200)
    output = stream.getvalue()
    assert "EMP011" not in output
    assert "POST" in output