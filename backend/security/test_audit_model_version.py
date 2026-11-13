import logging
from backend.security import access_policy as ap


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_audit_line_carries_model_version():
    collector = _Collect()
    previous_level = ap.audit.level
    ap.audit.setLevel(logging.INFO)
    ap.audit.addHandler(collector)
    try:
        ap.set_model_fingerprint("aaaa/bbbb/cccc")
        actor = ap.Actor(employee_id=1, organization_id=1, department_id=1, role=ap.ADMIN)
        ap.authorize_entity(actor, "attendance")
    finally:
        ap.audit.removeHandler(collector)
        ap.audit.setLevel(previous_level)
    assert any("model=aaaa/bbbb/cccc" in line for line in collector.lines)