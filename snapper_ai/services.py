"""Transactional component registration and publication.

The hosting application authenticates a caller and supplies its trusted
``publisher_identity``. Snapper verifies that identity against the registered
owner; it never derives an identity from component data.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from .models import CurrentComponent


MAX_REGISTRATION_BYTES = 256 * 1024
DEFAULT_MAX_DATA_BYTES = 64 * 1024
MAX_DATA_BYTES = 1024 * 1024
JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
VISIBILITIES = {"public", "operator", "internal"}
_MISSING = object()


class SnapperError(Exception):
    """Base exception for rejected Snapper operations."""


class InvalidRegistration(SnapperError):
    pass


class InvalidPublication(SnapperError):
    pass


class PublisherNotAuthorized(SnapperError):
    pass


class ComponentNotFound(SnapperError):
    pass


class ComponentInactive(SnapperError):
    pass


class StaleAssessment(SnapperError):
    pass


class StaleRevision(SnapperError):
    pass


@dataclass(frozen=True)
class ComponentUpdate:
    component_id: str
    scope: str
    name: str
    created: bool
    registration_changed: bool
    content_changed: bool
    registration_version: int
    revision: int
    accepted_at: Optional[datetime]


def _bounded_identity(value: str, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidPublication(f"{label} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        raise InvalidPublication(f"{label} exceeds {maximum} characters")
    return value


def _validate_json(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _validate_json(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def _canonical(value: Any) -> Tuple[Dict[str, Any], bytes, str]:
    _validate_json(value)
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    normalized = json.loads(encoded.decode("utf-8"))
    return normalized, encoded, hashlib.sha256(encoded).hexdigest()


def _validate_registration(
    registration: Dict[str, Any], component_schema_version: int
) -> Tuple[Dict[str, Any], str]:
    if not isinstance(component_schema_version, int) or isinstance(component_schema_version, bool):
        raise InvalidRegistration("component_schema_version must be a positive integer")
    if component_schema_version < 1:
        raise InvalidRegistration("component_schema_version must be a positive integer")
    if not isinstance(registration, dict):
        raise InvalidRegistration("registration must be a JSON object")
    try:
        normalized, encoded, _ = _canonical(registration)
    except (TypeError, ValueError) as exc:
        raise InvalidRegistration(str(exc)) from exc
    if len(encoded) > MAX_REGISTRATION_BYTES:
        raise InvalidRegistration(
            f"registration exceeds {MAX_REGISTRATION_BYTES} canonical bytes"
        )

    title = normalized.get("title")
    description = normalized.get("description")
    visibility = normalized.get("visibility")
    quantities = normalized.get("quantities")
    if not isinstance(title, str) or not title.strip():
        raise InvalidRegistration("registration.title must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise InvalidRegistration("registration.description must be a non-empty string")
    if visibility not in VISIBILITIES:
        raise InvalidRegistration(
            "registration.visibility must be public, operator, or internal"
        )
    if not isinstance(quantities, dict) or not quantities:
        raise InvalidRegistration("registration.quantities must be a non-empty object")

    seen_paths = set()
    for key, definition in quantities.items():
        if not isinstance(key, str) or not key:
            raise InvalidRegistration("quantity keys must be non-empty strings")
        if not isinstance(definition, dict):
            raise InvalidRegistration(f"quantity {key!r} must be an object")
        path = definition.get("path")
        if not isinstance(path, str) or not path or path.startswith(".") or path.endswith("."):
            raise InvalidRegistration(f"quantity {key!r} has an invalid path")
        if path in seen_paths:
            raise InvalidRegistration(f"quantity path {path!r} is registered twice")
        seen_paths.add(path)
        value_type = definition.get("type")
        if value_type not in JSON_TYPES:
            raise InvalidRegistration(f"quantity {key!r} has an invalid JSON type")
        if "required" in definition and not isinstance(definition["required"], bool):
            raise InvalidRegistration(f"quantity {key!r}.required must be boolean")
        for bound in ("max_items", "max_length"):
            if bound in definition:
                value = definition[bound]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise InvalidRegistration(
                        f"quantity {key!r}.{bound} must be a non-negative integer"
                    )
        if "max_items" in definition and value_type not in {"object", "array"}:
            raise InvalidRegistration(
                f"quantity {key!r}.max_items requires object or array type"
            )
        if "max_length" in definition and value_type != "string":
            raise InvalidRegistration(
                f"quantity {key!r}.max_length requires string type"
            )
        if "enum" in definition and not isinstance(definition["enum"], list):
            raise InvalidRegistration(f"quantity {key!r}.enum must be an array")

    max_bytes = normalized.get("max_serialized_bytes", DEFAULT_MAX_DATA_BYTES)
    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes < 1
        or max_bytes > MAX_DATA_BYTES
    ):
        raise InvalidRegistration(
            f"registration.max_serialized_bytes must be between 1 and {MAX_DATA_BYTES}"
        )

    envelope = {
        "component_schema_version": component_schema_version,
        "registration": normalized,
    }
    _, _, registration_hash = _canonical(envelope)
    return normalized, registration_hash


def _path_value(data: Dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return value is None


def _validate_data(
    data: Dict[str, Any], registration: Dict[str, Any]
) -> Tuple[Dict[str, Any], str]:
    if not isinstance(data, dict):
        raise InvalidPublication("component data must be a JSON object")
    try:
        normalized, encoded, content_hash = _canonical(data)
    except (TypeError, ValueError) as exc:
        raise InvalidPublication(str(exc)) from exc
    max_bytes = registration.get("max_serialized_bytes", DEFAULT_MAX_DATA_BYTES)
    if len(encoded) > max_bytes:
        raise InvalidPublication(
            f"component data exceeds {max_bytes} canonical bytes"
        )

    for key, definition in registration["quantities"].items():
        value = _path_value(normalized, definition["path"])
        if value is _MISSING:
            if definition.get("required", False):
                raise InvalidPublication(f"required quantity {key!r} is missing")
            continue
        if not _matches_type(value, definition["type"]):
            raise InvalidPublication(
                f"quantity {key!r} must be {definition['type']}"
            )
        if "enum" in definition and value not in definition["enum"]:
            raise InvalidPublication(f"quantity {key!r} is outside its enum")
        if "max_items" in definition and len(value) > definition["max_items"]:
            raise InvalidPublication(
                f"quantity {key!r} exceeds {definition['max_items']} items"
            )
        if "max_length" in definition and len(value) > definition["max_length"]:
            raise InvalidPublication(
                f"quantity {key!r} exceeds {definition['max_length']} characters"
            )
    return normalized, content_hash


def _validate_times(assessed_at: datetime, source_as_of: Optional[datetime]) -> None:
    if not isinstance(assessed_at, datetime) or not timezone.is_aware(assessed_at):
        raise InvalidPublication("assessed_at must be a timezone-aware datetime")
    if source_as_of is not None:
        if not isinstance(source_as_of, datetime) or not timezone.is_aware(source_as_of):
            raise InvalidPublication("source_as_of must be a timezone-aware datetime")
        if source_as_of > assessed_at:
            raise InvalidPublication("source_as_of cannot be later than assessed_at")


def _owned_component(scope: str, name: str, publisher_identity: str) -> CurrentComponent:
    try:
        component = CurrentComponent.objects.select_for_update().get(
            scope=scope, name=name
        )
    except CurrentComponent.DoesNotExist as exc:
        raise ComponentNotFound(f"component {scope}:{name} is not registered") from exc
    if component.publisher_identity != publisher_identity:
        raise PublisherNotAuthorized(
            f"publisher {publisher_identity!r} does not own {scope}:{name}"
        )
    if not component.active:
        raise ComponentInactive(f"component {scope}:{name} is retired")
    return component


def _result(
    component: CurrentComponent,
    *,
    created: bool = False,
    registration_changed: bool = False,
    content_changed: bool = False,
) -> ComponentUpdate:
    return ComponentUpdate(
        component_id=str(component.pk),
        scope=component.scope,
        name=component.name,
        created=created,
        registration_changed=registration_changed,
        content_changed=content_changed,
        registration_version=component.registration_version,
        revision=component.revision,
        accepted_at=component.accepted_at,
    )


@transaction.atomic
def register_component(
    *,
    scope: str,
    name: str,
    publisher_identity: str,
    registration: Dict[str, Any],
    component_schema_version: int = 1,
) -> ComponentUpdate:
    """Create or idempotently reconcile one publisher-owned component."""
    scope = _bounded_identity(scope, "scope", 100)
    name = _bounded_identity(name, "name", 100)
    publisher_identity = _bounded_identity(
        publisher_identity, "publisher_identity", 255
    )
    normalized, registration_hash = _validate_registration(
        registration, component_schema_version
    )
    component, created = CurrentComponent.objects.get_or_create(
        scope=scope,
        name=name,
        defaults={
            "publisher_identity": publisher_identity,
            "registration": normalized,
            "component_schema_version": component_schema_version,
            "registration_version": 1,
            "registration_hash": registration_hash,
        },
    )
    if created:
        return _result(component, created=True, registration_changed=True)
    component = CurrentComponent.objects.select_for_update().get(pk=component.pk)

    if component.publisher_identity != publisher_identity:
        raise PublisherNotAuthorized(
            f"publisher {publisher_identity!r} does not own {scope}:{name}"
        )
    if not component.active:
        raise ComponentInactive(f"component {scope}:{name} is retired")
    if component.registration_hash == registration_hash:
        return _result(component)
    if component_schema_version < component.component_schema_version:
        raise InvalidRegistration("component_schema_version cannot decrease")
    if component.data is not None and (
            component_schema_version == component.component_schema_version):
        # A same-version registration change must keep the stored data
        # valid. A schema-version increase declares a breaking shape
        # change: the stored old-shape data remains a valid historical
        # fact, and the publication that follows validates the new
        # shape against this registration.
        _validate_data(component.data, normalized)

    component.registration = normalized
    component.component_schema_version = component_schema_version
    component.registration_hash = registration_hash
    component.registration_version += 1
    update_fields = [
        "registration",
        "component_schema_version",
        "registration_hash",
        "registration_version",
        "modified_at",
    ]
    if component.data is not None:
        component.revision += 1
        component.changed_at = timezone.now()
        update_fields.extend(["revision", "changed_at"])
    component.save(update_fields=update_fields)
    return _result(component, registration_changed=True)


@transaction.atomic
def publish_component(
    *,
    scope: str,
    name: str,
    publisher_identity: str,
    data: Dict[str, Any],
    assessed_at: datetime,
    source_as_of: Optional[datetime] = None,
    assessment_policy_version: Optional[str] = None,
) -> ComponentUpdate:
    """Accept a complete component replacement and advance on semantic change."""
    scope = _bounded_identity(scope, "scope", 100)
    name = _bounded_identity(name, "name", 100)
    publisher_identity = _bounded_identity(
        publisher_identity, "publisher_identity", 255
    )
    _validate_times(assessed_at, source_as_of)
    if assessment_policy_version is not None and (
        not isinstance(assessment_policy_version, str)
        or len(assessment_policy_version) > 100
    ):
        raise InvalidPublication(
            "assessment_policy_version must be a string of at most 100 characters"
        )
    component = _owned_component(scope, name, publisher_identity)
    if component.assessed_at is not None and assessed_at < component.assessed_at:
        raise StaleAssessment(
            f"assessment for {scope}:{name} predates the accepted assessment"
        )
    normalized, content_hash = _validate_data(data, component.registration)
    content_changed = component.data is None or component.content_hash != content_hash
    accepted_at = timezone.now()
    component.data = normalized
    component.content_hash = content_hash
    component.assessed_at = assessed_at
    component.source_as_of = source_as_of
    if assessment_policy_version is not None:
        component.assessment_policy_version = assessment_policy_version
    component.accepted_at = accepted_at
    update_fields = [
        "data",
        "content_hash",
        "assessed_at",
        "source_as_of",
        "accepted_at",
        "modified_at",
    ]
    if assessment_policy_version is not None:
        update_fields.append("assessment_policy_version")
    if content_changed:
        component.revision += 1
        component.changed_at = accepted_at
        update_fields.extend(["revision", "changed_at"])
    component.save(update_fields=update_fields)
    return _result(component, content_changed=content_changed)


@transaction.atomic
def report_component_unchanged(
    *,
    scope: str,
    name: str,
    publisher_identity: str,
    assessed_at: datetime,
    source_as_of: Optional[datetime] = None,
    assessment_policy_version: Optional[str] = None,
    expected_revision: Optional[int] = None,
) -> ComponentUpdate:
    """Refresh provenance without resending or revising component data."""
    scope = _bounded_identity(scope, "scope", 100)
    name = _bounded_identity(name, "name", 100)
    publisher_identity = _bounded_identity(
        publisher_identity, "publisher_identity", 255
    )
    _validate_times(assessed_at, source_as_of)
    if assessment_policy_version is not None and (
        not isinstance(assessment_policy_version, str)
        or len(assessment_policy_version) > 100
    ):
        raise InvalidPublication(
            "assessment_policy_version must be a string of at most 100 characters"
        )
    component = _owned_component(scope, name, publisher_identity)
    if component.data is None:
        raise InvalidPublication(
            f"component {scope}:{name} has no accepted projection to affirm"
        )
    if expected_revision is not None and expected_revision != component.revision:
        raise StaleRevision(
            f"expected revision {expected_revision}, current revision is {component.revision}"
        )
    if component.assessed_at is not None and assessed_at < component.assessed_at:
        raise StaleAssessment(
            f"assessment for {scope}:{name} predates the accepted assessment"
        )
    component.assessed_at = assessed_at
    component.source_as_of = source_as_of
    if assessment_policy_version is not None:
        component.assessment_policy_version = assessment_policy_version
    component.accepted_at = timezone.now()
    update_fields = [
        "assessed_at",
        "source_as_of",
        "accepted_at",
        "modified_at",
    ]
    if assessment_policy_version is not None:
        update_fields.append("assessment_policy_version")
    component.save(update_fields=update_fields)
    return _result(component)
