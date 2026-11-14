import logging
import re
import threading

EMP_CODE_RE = re.compile(r"\bEMP\d{3,}\b", re.IGNORECASE)
MIN_NAME_LENGTH = 4

_names: set[str] = set()
_names_lock = threading.Lock()


def register_names(names) -> None:
    """Add employee full names to mask. Call once at startup from the employees table."""
    with _names_lock:
        for name in names:
            cleaned = (name or "").strip()
            if len(cleaned) >= MIN_NAME_LENGTH:
                _names.add(cleaned)


def clear_names() -> None:
    with _names_lock:
        _names.clear()


def mask_text(text: str) -> str:
    text = EMP_CODE_RE.sub("[employee]", text)
    with _names_lock:
        names = sorted(_names, key=len, reverse=True)
    for name in names:
        text = re.sub(re.escape(name), "[name]", text, flags=re.IGNORECASE)
    return text

def _mask_value(value):
    if isinstance(value, str):
        return mask_text(value)
    return value


class PiiRedactionFilter(logging.Filter):
    """Masks employee codes and registered names in the formatted message and any traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: _mask_value(v) for k, v in record.args.items()}
                else:
                    record.args = tuple(_mask_value(a) for a in record.args)
            else:
                record.msg = mask_text(str(record.msg))
        except Exception:
            return True
        if record.exc_info:
            formatted = logging.Formatter().formatException(record.exc_info)
            record.exc_text = mask_text(formatted)
        return True

def install_pii_redaction(logger_names=("", "uvicorn.access", "uvicorn.error")) -> None:
    """Attach the filter to every handler on the given loggers. Safe to call more than once."""
    for name in logger_names:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, PiiRedactionFilter) for f in handler.filters):
                handler.addFilter(PiiRedactionFilter())