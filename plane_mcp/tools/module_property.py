"""Custom properties on modules, and the values a module holds for them (oces fork).

plane-sdk has no models or endpoints for these, so calls go through the SDK's own
authenticated request helpers on the modules resource (base path /workspaces/).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastmcp import FastMCP
from plane.errors.errors import HttpError

from plane_mcp.client import get_plane_client_context
from plane_mcp.toolkit import Action, build_annotations, build_description, coerce_list, missing, needs, one_of

NAME = "module_property"
TITLE = "Module properties"

PROPERTY_TYPES = ("TEXT", "DATETIME", "DECIMAL", "BOOLEAN", "OPTION", "RELATION", "URL", "EMAIL")
RELATION_TYPES = ("USER", "ISSUE", "MODULE")
TEXT_FORMATS = ("single-line", "multi-line", "readonly")
DATE_FORMATS = ("MMM dd, yyyy", "dd/MM/yyyy", "MM/dd/yyyy", "yyyy/MM/dd")

_FIELDS = (
    "relation_type",
    "description",
    "is_required",
    "is_multi",
    "is_active",
    "default_value",
    "options",
    "display_format",
    "external_source",
    "external_id",
)

ACTIONS = (
    Action("list", ("project_id",), read=True),
    Action("retrieve", ("project_id", "property_id"), read=True),
    Action("create", ("project_id", "display_name", "property_type"), _FIELDS),
    Action(
        "update",
        ("project_id", "property_id"),
        ("display_name", *_FIELDS),
        note="only the fields you pass are changed; options here replaces the option list",
    ),
    Action("delete", ("project_id", "property_id"), destructive=True, note="also removes its values"),
    Action(
        "get_values",
        ("project_id", "module_id"),
        ("property_id",),
        note="omit property_id for every value plus computed",
        read=True,
    ),
    Action("set_value", ("project_id", "module_id", "property_id", "value"), note="replaces the current value"),
    Action("delete_value", ("project_id", "module_id", "property_id"), destructive=True),
    Action("list_values", ("project_id",), note="every module's values, keyed by module id", read=True),
)

FOOTER = (
    f"property_type is one of: {', '.join(PROPERTY_TYPES)}. relation_type (required for RELATION) is one of: "
    f"{', '.join(RELATION_TYPES)} (MODULE links other modules of the project, e.g. depends on). is_multi only "
    f"for OPTION and RELATION. display_format is required by TEXT ({', '.join(TEXT_FORMATS)}) and DATETIME "
    f"({', '.join(DATE_FORMATS)}). "
    'options takes a JSON array of {"name", "color", "is_default"} objects. '
    "value: TEXT/URL/EMAIL string; DECIMAL number; BOOLEAN true/false; DATETIME YYYY-MM-DD[ HH:MM:SS]; "
    "OPTION an option id; RELATION a user, work item or module id; an array of ids when is_multi. "
    "Progress, points and work item counts are in get_values' computed block, derived from the module's "
    "work items -- read them there, never create properties for them or set them by hand."
)

LEGACY: dict[str, str] = {}  # new in this fork; no retired names


def _json(raw: str, expected: type):
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, expected) else None


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name=NAME,
        description=build_description("Custom properties on modules.", ACTIONS, FOOTER),
        annotations=build_annotations(TITLE, ACTIONS),
    )
    def module_property(
        action: Literal[
            "list",
            "retrieve",
            "create",
            "update",
            "delete",
            "get_values",
            "set_value",
            "delete_value",
            "list_values",
        ],
        project_id: str = "",
        module_id: str = "",
        property_id: str = "",
        display_name: str = "",
        property_type: str = "",
        relation_type: str = "",
        description: str = "",
        default_value: str = "",
        options: str = "",
        display_format: str = "",
        value: str | bool | int | float | list[str] = "",
        # None = leave unchanged; False is a real value.
        is_required: bool | None = None,
        is_multi: bool | None = None,
        is_active: bool | None = None,
        external_source: str = "",
        external_id: str = "",
    ) -> dict[str, Any] | list[Any] | str | None:
        client, workspace_slug = get_plane_client_context()
        api = client.modules  # any resource works: its base path is /workspaces/

        if error := one_of("property_type", property_type, PROPERTY_TYPES):
            return error
        if error := one_of("relation_type", relation_type, RELATION_TYPES):
            return error
        if error := one_of("display_format", display_format, TEXT_FORMATS + DATE_FORMATS):
            return error
        if not project_id:
            return missing(action, "project_id")

        project = f"{workspace_slug}/projects/{project_id}"
        properties = f"{project}/module-properties"

        if action == "list":
            return api._get(properties)
        if action == "list_values":
            return api._get(f"{project}/module-property-values")

        if action in ("create", "update"):
            if action == "create" and (error := needs(action, display_name=display_name, property_type=property_type)):
                return error
            if action == "update" and not property_id:
                return missing(action, "property_id")
            parsed_options = None
            if options:
                parsed_options = _json(options, list)
                if parsed_options is None:
                    return 'Error: options must be a JSON array, for example [{"name": "High"}].'
            # TEXT and DATETIME require a display_format; default rather than fail.
            if not display_format and action == "create":
                display_format = {"TEXT": "single-line", "DATETIME": "MMM dd, yyyy"}.get(property_type, "")
            body = {
                "display_name": display_name,
                "property_type": property_type,
                "relation_type": relation_type,
                "description": description,
                "default_value": coerce_list(default_value, split=False),
                "options": parsed_options,
                "settings": {"display_format": display_format} if display_format else None,
                "is_required": is_required,
                "is_multi": is_multi,
                "is_active": is_active,
                "external_source": external_source,
                "external_id": external_id,
            }
            body = {k: v for k, v in body.items() if v not in (None, "")}
            if action == "create":
                return api._post(properties, body)
            return api._patch(f"{properties}/{property_id}", body)

        if action == "get_values":
            if not module_id:
                return missing(action, "module_id")
            if not property_id:
                return api._get(f"{project}/modules/{module_id}/module-property-values")
            try:
                return api._get(f"{project}/modules/{module_id}/module-properties/{property_id}/values")
            except HttpError as exc:
                if exc.status_code == 404:
                    return None  # unset
                raise

        if action in ("set_value", "delete_value"):
            # `value` is checked against "" only: False and 0 are real values.
            if error := needs(action, module_id=module_id, property_id=property_id):
                return error
            path = f"{project}/modules/{module_id}/module-properties/{property_id}/values"
            if action == "delete_value":
                api._delete(path)
                return None
            if value == "":
                return missing(action, "value")
            return api._post(path, {"value": value})

        if not property_id:
            return missing(action, "property_id")
        if action == "retrieve":
            return api._get(f"{properties}/{property_id}")
        api._delete(f"{properties}/{property_id}")
        return None
