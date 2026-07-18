"""Deterministic temporal retrieval over immutable Snapper history."""

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Dict, Optional, Tuple

from .models import CaptureCursor, SystemSnap
from .services import SnapperError


class InvalidQuery(SnapperError):
    """A temporal query argument is invalid."""


class SnapNotFound(SnapperError):
    """No recorded logical state exists for the requested scope or time."""


class UnsupportedEncoding(SnapperError):
    """A stored snap encoding cannot yet be reconstructed."""


def _bounded_scope(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise InvalidQuery("scope must be a non-empty string")
    scope = scope.strip()
    if len(scope) > 100:
        raise InvalidQuery("scope exceeds 100 characters")
    return scope


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return (
        value.astimezone(datetime_timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class ObserverCoverage:
    """Observer evidence applicable to one temporal query."""

    status: str
    checked_through: Optional[datetime]
    checked_at: Optional[datetime]
    gap_started_at: Optional[datetime]
    gap_ended_at: Optional[datetime]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "checked_through": _timestamp(self.checked_through),
            "checked_at": _timestamp(self.checked_at),
            "gap_started_at": _timestamp(self.gap_started_at),
            "gap_ended_at": _timestamp(self.gap_ended_at),
        }


@dataclass(frozen=True)
class StateQueryResult:
    """One complete logical snap plus request and coverage evidence."""

    scope: str
    requested_at: Optional[datetime]
    snap_id: str
    snap_time: datetime
    observed_at: datetime
    completed_at: datetime
    snap_schema_version: int
    capture_policy: str
    encoding: str
    state_hash: str
    state: Dict[str, Any]
    coverage: ObserverCoverage

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "requested_at": _timestamp(self.requested_at),
            "actual_snap_time": _timestamp(self.snap_time),
            "observed_at": _timestamp(self.observed_at),
            "completed_at": _timestamp(self.completed_at),
            "snap_id": self.snap_id,
            "snap_schema_version": self.snap_schema_version,
            "capture_policy": self.capture_policy,
            "encoding": self.encoding,
            "state_hash": self.state_hash,
            "coverage": self.coverage.as_dict(),
            "state": deepcopy(self.state),
        }


@dataclass(frozen=True)
class ComponentHistoryPoint:
    """One boundary, component change, baseline, or recovery record."""

    kind: str
    snap_id: str
    snap_time: datetime
    observed_at: datetime
    completed_at: datetime
    snap_schema_version: int
    capture_policy: str
    encoding: str
    reasons: Tuple[str, ...]
    component_changed: bool
    present: bool
    component_hash: Optional[str]
    registration_version: Optional[int]
    revision: Optional[int]
    recovered_gap_started_at: Optional[datetime]
    recovered_gap_start_unknown: bool
    component: Optional[Dict[str, Any]]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "snap_id": self.snap_id,
            "snap_time": _timestamp(self.snap_time),
            "observed_at": _timestamp(self.observed_at),
            "completed_at": _timestamp(self.completed_at),
            "snap_schema_version": self.snap_schema_version,
            "capture_policy": self.capture_policy,
            "encoding": self.encoding,
            "reasons": list(self.reasons),
            "component_changed": self.component_changed,
            "present": self.present,
            "component_hash": self.component_hash,
            "registration_version": self.registration_version,
            "revision": self.revision,
            "recovered_gap_started_at": _timestamp(
                self.recovered_gap_started_at
            ),
            "recovered_gap_start_unknown": self.recovered_gap_start_unknown,
            "component": deepcopy(self.component),
        }


@dataclass(frozen=True)
class ComponentHistoryResult:
    """Recorded evolution of one component over a requested interval."""

    scope: str
    component_name: str
    start_at: datetime
    end_at: datetime
    suppress_unchanged_baselines: bool
    start_coverage: ObserverCoverage
    end_coverage: ObserverCoverage
    entries: Tuple[ComponentHistoryPoint, ...]

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "component": self.component_name,
            "start_at": _timestamp(self.start_at),
            "end_at": _timestamp(self.end_at),
            "suppress_unchanged_baselines": self.suppress_unchanged_baselines,
            "start_coverage": self.start_coverage.as_dict(),
            "end_coverage": self.end_coverage.as_dict(),
            "entries": [entry.as_dict() for entry in self.entries],
        }


def _coverage(cursor: Optional[CaptureCursor]) -> ObserverCoverage:
    if cursor is None:
        return ObserverCoverage(
            status="unknown",
            checked_through=None,
            checked_at=None,
            gap_started_at=None,
            gap_ended_at=None,
        )
    return ObserverCoverage(
        status="gap" if cursor.coverage_gap_started_at else "covered",
        checked_through=cursor.latest_boundary_at,
        checked_at=cursor.latest_check_at,
        gap_started_at=cursor.coverage_gap_started_at,
        gap_ended_at=None,
    )


def _aware_time(value: datetime, label: str = "time") -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise InvalidQuery(f"{label} must be a timezone-aware datetime")
    return value


def _bounded_component(component: str) -> str:
    if not isinstance(component, str) or not component.strip():
        raise InvalidQuery("component must be a non-empty string")
    component = component.strip()
    if len(component) > 100:
        raise InvalidQuery("component exceeds 100 characters")
    return component


def _covered_by_snap(snap: SystemSnap) -> ObserverCoverage:
    return ObserverCoverage(
        status="covered",
        checked_through=snap.snap_time,
        checked_at=snap.observed_at,
        gap_started_at=None,
        gap_ended_at=None,
    )


def _coverage_at(
    *,
    scope: str,
    requested_at: datetime,
    snap: SystemSnap,
) -> ObserverCoverage:
    if requested_at == snap.snap_time:
        return _covered_by_snap(snap)

    next_snap = (
        SystemSnap.objects.filter(
            scope=scope,
            snap_time__gt=requested_at,
        )
        .order_by("snap_time")
        .only(
            "snap_time",
            "observed_at",
            "recovered_gap_started_at",
            "recovered_gap_start_unknown",
        )
        .first()
    )
    if next_snap is not None:
        if next_snap.recovered_gap_start_unknown is not False:
            return ObserverCoverage(
                status="unknown",
                checked_through=next_snap.snap_time,
                checked_at=next_snap.observed_at,
                gap_started_at=None,
                gap_ended_at=next_snap.snap_time,
            )
        if next_snap.recovered_gap_started_at is not None:
            if requested_at >= next_snap.recovered_gap_started_at:
                return ObserverCoverage(
                    status="gap",
                    checked_through=next_snap.snap_time,
                    checked_at=next_snap.observed_at,
                    gap_started_at=next_snap.recovered_gap_started_at,
                    gap_ended_at=next_snap.snap_time,
                )
        return ObserverCoverage(
            status="covered",
            checked_through=next_snap.snap_time,
            checked_at=next_snap.observed_at,
            gap_started_at=None,
            gap_ended_at=None,
        )

    cursor = CaptureCursor.objects.filter(scope=scope).first()
    if (
        cursor is None
        or cursor.latest_boundary_at is None
        or requested_at > cursor.latest_boundary_at
    ):
        return ObserverCoverage(
            status="unknown",
            checked_through=(
                cursor.latest_boundary_at if cursor is not None else None
            ),
            checked_at=cursor.latest_check_at if cursor is not None else None,
            gap_started_at=(
                cursor.coverage_gap_started_at
                if cursor is not None
                else None
            ),
            gap_ended_at=None,
        )
    if (
        cursor.coverage_gap_started_at is not None
        and requested_at >= cursor.coverage_gap_started_at
    ):
        return ObserverCoverage(
            status="gap",
            checked_through=cursor.latest_boundary_at,
            checked_at=cursor.latest_check_at,
            gap_started_at=cursor.coverage_gap_started_at,
            gap_ended_at=None,
        )
    return ObserverCoverage(
        status="covered",
        checked_through=cursor.latest_boundary_at,
        checked_at=cursor.latest_check_at,
        gap_started_at=None,
        gap_ended_at=None,
    )


def _result(
    *,
    scope: str,
    requested_at: Optional[datetime],
    snap: SystemSnap,
    coverage: ObserverCoverage,
) -> StateQueryResult:
    _require_full_snap(snap)
    if not isinstance(snap.state, dict):
        raise InvalidQuery(f"snap {snap.pk} does not contain an object state")
    return StateQueryResult(
        scope=scope,
        requested_at=requested_at,
        snap_id=str(snap.pk),
        snap_time=snap.snap_time,
        observed_at=snap.observed_at,
        completed_at=snap.completed_at,
        snap_schema_version=snap.snap_schema_version,
        capture_policy=snap.capture_policy,
        encoding=snap.encoding,
        state_hash=snap.state_hash,
        state=deepcopy(snap.state),
        coverage=coverage,
    )


def _require_full_snap(snap: SystemSnap) -> None:
    if snap.encoding != SystemSnap.Encoding.FULL:
        raise UnsupportedEncoding(
            f"cannot reconstruct {snap.encoding!r} snap {snap.pk}"
        )


def _snap_at(scope: str, requested_at: datetime) -> SystemSnap:
    snap = (
        SystemSnap.objects.filter(
            scope=scope,
            snap_time__lte=requested_at,
        )
        .order_by("-snap_time")
        .first()
    )
    if snap is None:
        raise SnapNotFound(
            f"scope {scope!r} has no snap at or before "
            f"{_timestamp(requested_at)}"
        )
    return snap


def _component_state(
    snap: SystemSnap,
    component_name: str,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    _require_full_snap(snap)
    if not isinstance(snap.state, dict):
        raise InvalidQuery(f"snap {snap.pk} does not contain an object state")
    components = snap.state.get("components")
    if not isinstance(components, dict):
        raise InvalidQuery(f"snap {snap.pk} has no object component map")
    if component_name not in components:
        return False, None
    component = components[component_name]
    if not isinstance(component, dict):
        raise InvalidQuery(
            f"snap {snap.pk} component {component_name!r} is not an object"
        )
    return True, component


def _component_signature(
    snap: SystemSnap,
    component_name: str,
    present: bool,
    component: Optional[Dict[str, Any]],
) -> tuple:
    if not present or component is None:
        return (False,)
    component_hash = (snap.component_hashes or {}).get(component_name)
    if component_hash is None:
        component_hash = json.dumps(
            component.get("data"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    registration_version = (snap.registration_versions or {}).get(
        component_name,
        component.get("registration_version"),
    )
    revision = (snap.component_revisions or {}).get(
        component_name,
        component.get("revision"),
    )
    return (
        True,
        component_hash,
        registration_version,
        revision,
        component.get("v"),
        component.get("assessment_policy"),
        component.get("publisher_identity"),
    )


def _history_point(
    *,
    snap: SystemSnap,
    component_name: str,
    kind: str,
    component_changed: bool,
) -> ComponentHistoryPoint:
    present, component = _component_state(snap, component_name)
    reasons = tuple(snap.reasons) if isinstance(snap.reasons, list) else ()
    recovered_gap_start_unknown = (
        snap.recovered_gap_started_at is None
        and (
            snap.recovered_gap_start_unknown is not False
            or "recovery" in reasons
        )
    )
    return ComponentHistoryPoint(
        kind=kind,
        snap_id=str(snap.pk),
        snap_time=snap.snap_time,
        observed_at=snap.observed_at,
        completed_at=snap.completed_at,
        snap_schema_version=snap.snap_schema_version,
        capture_policy=snap.capture_policy,
        encoding=snap.encoding,
        reasons=reasons,
        component_changed=component_changed,
        present=present,
        component_hash=(snap.component_hashes or {}).get(component_name),
        registration_version=(snap.registration_versions or {}).get(
            component_name,
            component.get("registration_version") if component else None,
        ),
        revision=(snap.component_revisions or {}).get(
            component_name,
            component.get("revision") if component else None,
        ),
        recovered_gap_started_at=snap.recovered_gap_started_at,
        recovered_gap_start_unknown=recovered_gap_start_unknown,
        component=deepcopy(component),
    )


def latest(scope: str) -> StateQueryResult:
    """Return the latest complete logical state and current coverage evidence."""
    scope = _bounded_scope(scope)
    cursor = (
        CaptureCursor.objects.filter(scope=scope)
        .select_related("latest_snap")
        .first()
    )
    snap = cursor.latest_snap if cursor is not None else None
    if snap is None:
        snap = (
            SystemSnap.objects.filter(scope=scope)
            .order_by("-snap_time")
            .first()
        )
    if snap is None:
        raise SnapNotFound(f"scope {scope!r} has no recorded snaps")
    return _result(
        scope=scope,
        requested_at=None,
        coverage=_coverage(cursor),
        snap=snap,
    )


def state_at(scope: str, time: datetime) -> StateQueryResult:
    """Return state at or before ``time`` with observer-coverage evidence."""
    scope = _bounded_scope(scope)
    requested_at = _aware_time(time)
    snap = _snap_at(scope, requested_at)
    return _result(
        scope=scope,
        requested_at=requested_at,
        snap=snap,
        coverage=_coverage_at(
            scope=scope,
            requested_at=requested_at,
            snap=snap,
        ),
    )


def component_history(
    scope: str,
    component: str,
    start: datetime,
    end: datetime,
    *,
    suppress_unchanged_baselines: bool = True,
) -> ComponentHistoryResult:
    """Return one component's boundary state and recorded interval history."""
    scope = _bounded_scope(scope)
    component_name = _bounded_component(component)
    start_at = _aware_time(start, "start")
    end_at = _aware_time(end, "end")
    if start_at > end_at:
        raise InvalidQuery("start must not be later than end")
    if not isinstance(suppress_unchanged_baselines, bool):
        raise InvalidQuery("suppress_unchanged_baselines must be boolean")

    boundary_snap = _snap_at(scope, start_at)
    end_snap = _snap_at(scope, end_at)
    boundary_present, boundary_component = _component_state(
        boundary_snap,
        component_name,
    )
    previous_signature = _component_signature(
        boundary_snap,
        component_name,
        boundary_present,
        boundary_component,
    )
    entries = [
        _history_point(
            snap=boundary_snap,
            component_name=component_name,
            kind="boundary",
            component_changed=False,
        )
    ]

    interval_snaps = SystemSnap.objects.filter(
        scope=scope,
        snap_time__gt=start_at,
        snap_time__lte=end_at,
    ).order_by("snap_time")
    for snap in interval_snaps:
        present, component_state = _component_state(snap, component_name)
        signature = _component_signature(
            snap,
            component_name,
            present,
            component_state,
        )
        component_changed = signature != previous_signature
        reasons = snap.reasons if isinstance(snap.reasons, list) else []
        is_recovery = (
            snap.recovered_gap_started_at is not None
            or snap.recovered_gap_start_unknown is not False
            or "recovery" in reasons
        )
        if component_changed or not suppress_unchanged_baselines or is_recovery:
            if is_recovery:
                kind = "recovery"
            elif component_changed:
                kind = "change"
            else:
                kind = "baseline"
            entries.append(
                _history_point(
                    snap=snap,
                    component_name=component_name,
                    kind=kind,
                    component_changed=component_changed,
                )
            )
        previous_signature = signature

    return ComponentHistoryResult(
        scope=scope,
        component_name=component_name,
        start_at=start_at,
        end_at=end_at,
        suppress_unchanged_baselines=suppress_unchanged_baselines,
        start_coverage=_coverage_at(
            scope=scope,
            requested_at=start_at,
            snap=boundary_snap,
        ),
        end_coverage=_coverage_at(
            scope=scope,
            requested_at=end_at,
            snap=end_snap,
        ),
        entries=tuple(entries),
    )
