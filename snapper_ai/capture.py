"""Transactional coherent capture for registered Snapper components."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Optional, Sequence

from django.db import connection, transaction
from django.utils import timezone

from .models import CaptureCursor, CurrentComponent, SystemSnap
from .services import SnapperError


class InvalidCapture(SnapperError):
    """Capture configuration or input is invalid."""


class IncompleteScope(SnapperError):
    """A scope cannot supply a complete coherent state."""


class StaleBoundary(SnapperError):
    """A capture opportunity predates the cursor's latest boundary."""


@dataclass(frozen=True)
class CaptureResult:
    scope: str
    boundary_at: datetime
    checked_at: datetime
    outcome: str
    reasons: Sequence[str]
    changed_components: Sequence[str]
    snap: Optional[SystemSnap]
    coverage_gap_started_at: Optional[datetime]


def _bounded_scope(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise InvalidCapture("scope must be a non-empty string")
    scope = scope.strip()
    if len(scope) > 100:
        raise InvalidCapture("scope exceeds 100 characters")
    return scope


def _capture_policy(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidCapture("capture_policy must be a non-empty string")
    value = value.strip()
    if len(value) > 100:
        raise InvalidCapture("capture_policy exceeds 100 characters")
    return value


def _positive_integer(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvalidCapture(f"{label} must be a positive integer")
    return value


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or not timezone.is_aware(value):
        raise InvalidCapture(f"{label} must be a timezone-aware datetime")
    return value


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def aligned_boundary(at: datetime, opportunity_seconds: int) -> datetime:
    """Return the UTC wall-clock boundary at or immediately before ``at``."""
    at = _aware(at, "at")
    opportunity_seconds = _positive_integer(
        opportunity_seconds, "opportunity_seconds"
    )
    epoch = int(at.timestamp())
    aligned = epoch - (epoch % opportunity_seconds)
    return datetime.fromtimestamp(aligned, tz=datetime_timezone.utc)


def _component_document(component: CurrentComponent) -> dict:
    return {
        "v": component.component_schema_version,
        "registration_version": component.registration_version,
        "registration": component.registration,
        "revision": component.revision,
        "publisher_identity": component.publisher_identity,
        "assessed_at": _timestamp(component.assessed_at),
        "source_as_of": _timestamp(component.source_as_of),
        "assessment_policy": component.assessment_policy_version,
        "accepted_at": _timestamp(component.accepted_at),
        "data": component.data,
    }


def _cursor(scope: str) -> CaptureCursor:
    CaptureCursor.objects.get_or_create(scope=scope)
    return CaptureCursor.objects.select_for_update().get(scope=scope)


def _scheduler_result(
    *,
    outcome: str,
    boundary_at: datetime,
    checked_at: datetime,
    reasons: Sequence[str] = (),
    changed_components: Sequence[str] = (),
    snap: Optional[SystemSnap] = None,
    error: str = "",
) -> dict:
    result = {
        "outcome": outcome,
        "boundary_at": _timestamp(boundary_at),
        "checked_at": _timestamp(checked_at),
        "reasons": list(reasons),
        "changed_components": list(changed_components),
    }
    if snap is not None:
        result["snap_id"] = str(snap.pk)
    if error:
        result["error"] = error[:1000]
    return result


@transaction.atomic
def capture_scope(
    *,
    scope: str,
    boundary_at: datetime,
    capture_policy: str,
    opportunity_seconds: int,
    baseline_every: int,
    manual: bool = False,
    snap_schema_version: int = 1,
    lock_timeout_ms: int = 5000,
) -> CaptureResult:
    """Evaluate one aligned opportunity and persist a full snap when due."""
    scope = _bounded_scope(scope)
    boundary_at = _aware(boundary_at, "boundary_at")
    capture_policy = _capture_policy(capture_policy)
    opportunity_seconds = _positive_integer(
        opportunity_seconds, "opportunity_seconds"
    )
    baseline_every = _positive_integer(baseline_every, "baseline_every")
    snap_schema_version = _positive_integer(
        snap_schema_version, "snap_schema_version"
    )
    lock_timeout_ms = _positive_integer(lock_timeout_ms, "lock_timeout_ms")
    if not isinstance(manual, bool):
        raise InvalidCapture("manual must be boolean")
    if aligned_boundary(boundary_at, opportunity_seconds) != boundary_at:
        raise InvalidCapture(
            f"boundary_at is not aligned to {opportunity_seconds} seconds"
        )
    with connection.cursor() as database_cursor:
        database_cursor.execute(
            "SELECT set_config('lock_timeout', %s, true)",
            [f"{lock_timeout_ms}ms"],
        )

    cursor = _cursor(scope)
    checked_at = timezone.now()
    latest_boundary = cursor.latest_boundary_at
    if latest_boundary is not None and boundary_at < latest_boundary:
        raise StaleBoundary(
            f"boundary {boundary_at.isoformat()} predates "
            f"{latest_boundary.isoformat()} for {scope}"
        )
    if latest_boundary == boundary_at:
        cursor.latest_check_at = checked_at
        cursor.heartbeat_at = checked_at
        cursor.consecutive_failures = 0
        cursor.scheduler_result = _scheduler_result(
            outcome="duplicate",
            boundary_at=boundary_at,
            checked_at=checked_at,
        )
        cursor.save(
            update_fields=[
                "latest_check_at",
                "heartbeat_at",
                "consecutive_failures",
                "scheduler_result",
                "modified_at",
            ]
        )
        return CaptureResult(
            scope=scope,
            boundary_at=boundary_at,
            checked_at=checked_at,
            outcome="duplicate",
            reasons=(),
            changed_components=(),
            snap=None,
            coverage_gap_started_at=cursor.coverage_gap_started_at,
        )

    gap_started_at = cursor.coverage_gap_started_at
    if (
        latest_boundary is not None
        and boundary_at
        > latest_boundary + timedelta(seconds=opportunity_seconds)
        and gap_started_at is None
    ):
        gap_started_at = latest_boundary + timedelta(seconds=opportunity_seconds)

    components = list(
        CurrentComponent.objects.select_for_update()
        .filter(scope=scope, active=True)
        .order_by("name")
    )
    if not components:
        raise IncompleteScope(f"scope {scope!r} has no active components")
    unpublished = [component.name for component in components if component.data is None]
    if unpublished:
        raise IncompleteScope(
            f"scope {scope!r} has unpublished components: {', '.join(unpublished)}"
        )

    revisions = {component.name: component.revision for component in components}
    registration_versions = {
        component.name: component.registration_version
        for component in components
    }
    content_hashes = {
        component.name: component.content_hash for component in components
    }
    observed_revisions = cursor.observed_revisions or {}
    changed = {
        name
        for name, revision in revisions.items()
        if observed_revisions.get(name) != revision
    }
    changed.update(set(observed_revisions) - set(revisions))
    changed_components = tuple(sorted(changed))

    reasons = []
    if cursor.latest_snap_id is None:
        reasons.append("startup")
    if changed_components:
        reasons.append("change")
    if (
        cursor.latest_snap_id is not None
        and cursor.baseline_progress + 1 >= baseline_every
    ):
        reasons.append("baseline")
    if manual:
        reasons.append("manual")
    if gap_started_at is not None:
        reasons.append("recovery")

    cursor.latest_boundary_at = boundary_at
    cursor.latest_check_at = checked_at
    cursor.heartbeat_at = checked_at
    cursor.consecutive_failures = 0

    if not reasons:
        cursor.baseline_progress += 1
        cursor.coverage_gap_started_at = None
        cursor.scheduler_result = _scheduler_result(
            outcome="quiet",
            boundary_at=boundary_at,
            checked_at=checked_at,
            changed_components=changed_components,
        )
        cursor.save(
            update_fields=[
                "latest_boundary_at",
                "latest_check_at",
                "heartbeat_at",
                "consecutive_failures",
                "baseline_progress",
                "coverage_gap_started_at",
                "scheduler_result",
                "modified_at",
            ]
        )
        return CaptureResult(
            scope=scope,
            boundary_at=boundary_at,
            checked_at=checked_at,
            outcome="quiet",
            reasons=(),
            changed_components=changed_components,
            snap=None,
            coverage_gap_started_at=None,
        )

    observed_at = timezone.now()
    component_documents = {
        component.name: _component_document(component)
        for component in components
    }
    completed_at = timezone.now()
    state = {
        "v": snap_schema_version,
        "scope": scope,
        "snap_time": _timestamp(boundary_at),
        "observed_at": _timestamp(observed_at),
        "completed_at": _timestamp(completed_at),
        "capture_policy": capture_policy,
        "encoding": SystemSnap.Encoding.FULL,
        "reasons": reasons,
        "changed_components": list(changed_components),
        "components": component_documents,
    }
    state_hash = _canonical_hash(component_documents)
    snap = SystemSnap.objects.create(
        scope=scope,
        snap_time=boundary_at,
        observed_at=observed_at,
        completed_at=completed_at,
        snap_schema_version=snap_schema_version,
        capture_policy=capture_policy,
        encoding=SystemSnap.Encoding.FULL,
        reasons=reasons,
        changed_components=list(changed_components),
        component_revisions=revisions,
        registration_versions=registration_versions,
        component_hashes=content_hashes,
        state_hash=state_hash,
        state=state,
    )
    cursor.observed_revisions = revisions
    cursor.observed_hashes = content_hashes
    cursor.latest_snap = snap
    cursor.baseline_progress = 0
    cursor.coverage_gap_started_at = None
    cursor.scheduler_result = _scheduler_result(
        outcome="snap",
        boundary_at=boundary_at,
        checked_at=checked_at,
        reasons=reasons,
        changed_components=changed_components,
        snap=snap,
    )
    cursor.save(
        update_fields=[
            "observed_revisions",
            "observed_hashes",
            "latest_boundary_at",
            "latest_check_at",
            "latest_snap",
            "baseline_progress",
            "scheduler_result",
            "heartbeat_at",
            "consecutive_failures",
            "coverage_gap_started_at",
            "modified_at",
        ]
    )
    return CaptureResult(
        scope=scope,
        boundary_at=boundary_at,
        checked_at=checked_at,
        outcome="snap",
        reasons=tuple(reasons),
        changed_components=changed_components,
        snap=snap,
        coverage_gap_started_at=gap_started_at,
    )


@transaction.atomic
def report_capture_failure(
    *,
    scope: str,
    boundary_at: datetime,
    error: str,
) -> CaptureCursor:
    """Record a failed evaluated opportunity for later recovery capture."""
    scope = _bounded_scope(scope)
    boundary_at = _aware(boundary_at, "boundary_at")
    if not isinstance(error, str) or not error.strip():
        raise InvalidCapture("error must be a non-empty string")
    cursor = _cursor(scope)
    checked_at = timezone.now()
    if (
        cursor.latest_boundary_at is not None
        and boundary_at < cursor.latest_boundary_at
    ):
        raise StaleBoundary(
            f"failed boundary {boundary_at.isoformat()} predates "
            f"{cursor.latest_boundary_at.isoformat()} for {scope}"
        )
    cursor.latest_boundary_at = boundary_at
    cursor.latest_check_at = checked_at
    cursor.heartbeat_at = checked_at
    cursor.consecutive_failures += 1
    if cursor.coverage_gap_started_at is None:
        cursor.coverage_gap_started_at = boundary_at
    cursor.scheduler_result = _scheduler_result(
        outcome="failed",
        boundary_at=boundary_at,
        checked_at=checked_at,
        error=error,
    )
    cursor.save(
        update_fields=[
            "latest_boundary_at",
            "latest_check_at",
            "heartbeat_at",
            "consecutive_failures",
            "coverage_gap_started_at",
            "scheduler_result",
            "modified_at",
        ]
    )
    return cursor
