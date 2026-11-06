from types import SimpleNamespace

from app.middleware.audit_log import _redact_if_display_prefs


class RequestStub:
    def __init__(self, changed_fields=None):
        self.state = SimpleNamespace()
        if changed_fields is not None:
            self.state.audit_changed_fields = changed_fields


def test_display_preferences_audit_payload_keeps_only_revision_and_field_names():
    response = {
        "code": 200,
        "message": "success",
        "data": {
            "revision": 7,
            "amount_unit_override": "wan",
            "font_size": "lg",
            "decimal_places": 4,
            "fixed_columns": {"trial_balance": ["amount"]},
        },
    }
    redacted = _redact_if_display_prefs(
        "PATCH",
        "/api/users/me/display-preferences",
        response,
        RequestStub(["font_size", "amount_unit_override", "font_size"]),
    )
    assert redacted == {
        "revision": 7,
        "changed_fields": ["amount_unit_override", "font_size"],
    }
    serialized = repr(redacted)
    assert "wan" not in serialized
    assert "fixed_columns" not in serialized
    assert "decimal_places" not in serialized


def test_display_preferences_trailing_slash_and_invalid_state_fail_closed():
    redacted = _redact_if_display_prefs(
        "patch",
        "/api/users/me/display-preferences/",
        {"data": {"revision": 8, "page_key": "trial_balance"}},
        RequestStub("not-a-list"),
    )
    assert redacted == {"redacted": True, "changed_fields": []}


def test_other_write_responses_are_unchanged():
    response = {"data": {"amount": 100}}
    assert _redact_if_display_prefs(
        "PATCH", "/api/projects/p1", response, RequestStub(),
    ) is response
    assert _redact_if_display_prefs(
        "POST", "/api/users/me/display-preferences", response, RequestStub(),
    ) is response
