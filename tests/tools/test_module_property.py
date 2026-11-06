"""Module properties reach the oces Plane fork's endpoints through the SDK's raw helpers."""

from __future__ import annotations

import pytest
from plane.errors.errors import HttpError

BASE = "acme/projects/p1"
VALUES = f"{BASE}/modules/m1/module-properties/prop-1/values"


def _call(registered, **arguments):
    return registered["module_property"].fn(project_id="p1", **arguments)


@pytest.mark.parametrize(
    ("arguments", "method", "endpoint"),
    [
        ({"action": "list"}, "_get", f"{BASE}/module-properties"),
        ({"action": "retrieve", "property_id": "prop-1"}, "_get", f"{BASE}/module-properties/prop-1"),
        ({"action": "delete", "property_id": "prop-1"}, "_delete", f"{BASE}/module-properties/prop-1"),
        ({"action": "get_values", "module_id": "m1"}, "_get", f"{BASE}/modules/m1/module-property-values"),
        ({"action": "get_values", "module_id": "m1", "property_id": "prop-1"}, "_get", VALUES),
        ({"action": "delete_value", "module_id": "m1", "property_id": "prop-1"}, "_delete", VALUES),
        ({"action": "list_values"}, "_get", f"{BASE}/module-property-values"),
    ],
)
def test_reads_and_deletes_hit_their_endpoint(arguments, method, endpoint, registered, spy):
    _call(registered, **arguments)

    call = spy.recorder.only()
    assert call.method == f"modules.{method}"
    assert call.kwargs["endpoint"] == endpoint


def test_create_sends_the_property_with_a_default_display_format(registered, spy):
    _call(
        registered,
        action="create",
        display_name="Depends on",
        property_type="RELATION",
        relation_type="MODULE",
        is_multi=True,
    )

    call = spy.recorder.only()
    assert call.method == "modules._post"
    assert call.kwargs["endpoint"] == f"{BASE}/module-properties"
    assert call.kwargs["data"] == {
        "display_name": "Depends on",
        "property_type": "RELATION",
        "relation_type": "MODULE",
        "is_multi": True,
    }


def test_create_text_defaults_display_format_and_parses_options(registered, spy):
    _call(registered, action="create", display_name="Owner note", property_type="TEXT")
    assert spy.recorder.only().kwargs["data"]["settings"] == {"display_format": "single-line"}

    spy.recorder.calls.clear()
    _call(
        registered,
        action="create",
        display_name="Risk",
        property_type="OPTION",
        options='[{"name": "High", "color": "#EF4444"}]',
    )
    data = spy.recorder.only().kwargs["data"]
    assert data["options"] == [{"name": "High", "color": "#EF4444"}]
    assert "settings" not in data


def test_update_patches_only_the_fields_given(registered, spy):
    _call(registered, action="update", property_id="prop-1", display_name="Renamed", is_required=False)

    call = spy.recorder.only()
    assert call.method == "modules._patch"
    assert call.kwargs["endpoint"] == f"{BASE}/module-properties/prop-1"
    assert call.kwargs["data"] == {"display_name": "Renamed", "is_required": False}


@pytest.mark.parametrize("value", ["2026-10-30", 0, False, ["u1", "u2"]])
def test_set_value_posts_the_value_in_its_own_type(value, registered, spy):
    _call(registered, action="set_value", module_id="m1", property_id="prop-1", value=value)

    call = spy.recorder.only()
    assert call.method == "modules._post"
    assert call.kwargs["endpoint"] == VALUES
    assert call.kwargs["data"] == {"value": value}


def test_an_unset_value_reads_as_none(registered, spy):
    spy.returns["modules._get"] = HttpError("HTTP 404: Not Found", 404, {})

    assert _call(registered, action="get_values", module_id="m1", property_id="prop-1") is None


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"property_type": "FORMULA"}, "property_type must be one of"),
        ({"property_type": "RELATION", "relation_type": "RICH_TEXT"}, "relation_type must be one of"),
        ({"property_type": "OPTION", "options": "High"}, "options must be a JSON array"),
    ],
)
def test_bad_input_is_refused_before_plane_sees_it(arguments, error, registered, spy):
    result = _call(registered, action="create", display_name="X", **arguments)

    assert error in result
    assert not spy.recorder.calls
