"""Deterministic temporal retrieval over immutable Snapper history."""

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Any, Dict, Optional, Tuple

from .models import CaptureCursor, CurrentComponent, SystemSnap
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


@dataclass(frozen=True)
class ChangedComponent:
    """One component addition, mutation, or removal at a logical snap."""

    name: str
    kind: str
    previous_hash: Optional[str]
    current_hash: Optional[str]
    previous_registration_version: Optional[int]
    current_registration_version: Optional[int]
    previous_revision: Optional[int]
    current_revision: Optional[int]
    previous: Optional[Dict[str, Any]]
    current: Optional[Dict[str, Any]]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "previous_hash": self.previous_hash,
            "current_hash": self.current_hash,
            "previous_registration_version": (
                self.previous_registration_version
            ),
            "current_registration_version": (
                self.current_registration_version
            ),
            "previous_revision": self.previous_revision,
            "current_revision": self.current_revision,
            "previous": deepcopy(self.previous),
            "current": deepcopy(self.current),
        }


@dataclass(frozen=True)
class SystemChange:
    """All derived component changes and recovery evidence at one snap."""

    kind: str
    snap_id: str
    snap_time: datetime
    observed_at: datetime
    completed_at: datetime
    previous_snap_schema_version: int
    snap_schema_version: int
    previous_capture_policy: str
    capture_policy: str
    encoding: str
    state_hash: str
    schema_changed: bool
    capture_policy_changed: bool
    reasons: Tuple[str, ...]
    declared_changed_components: Tuple[str, ...]
    recovered_gap_started_at: Optional[datetime]
    recovered_gap_start_unknown: bool
    components: Tuple[ChangedComponent, ...]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "snap_id": self.snap_id,
            "snap_time": _timestamp(self.snap_time),
            "observed_at": _timestamp(self.observed_at),
            "completed_at": _timestamp(self.completed_at),
            "previous_snap_schema_version": (
                self.previous_snap_schema_version
            ),
            "snap_schema_version": self.snap_schema_version,
            "previous_capture_policy": self.previous_capture_policy,
            "capture_policy": self.capture_policy,
            "encoding": self.encoding,
            "state_hash": self.state_hash,
            "schema_changed": self.schema_changed,
            "capture_policy_changed": self.capture_policy_changed,
            "reasons": list(self.reasons),
            "declared_changed_components": list(
                self.declared_changed_components
            ),
            "recovered_gap_started_at": _timestamp(
                self.recovered_gap_started_at
            ),
            "recovered_gap_start_unknown": self.recovered_gap_start_unknown,
            "components": [
                component.as_dict() for component in self.components
            ],
        }


@dataclass(frozen=True)
class ChangesBetweenResult:
    """System component changes over one requested interval."""

    scope: str
    start_at: datetime
    end_at: datetime
    boundary_snap_id: str
    boundary_snap_time: datetime
    start_coverage: ObserverCoverage
    end_coverage: ObserverCoverage
    changes: Tuple[SystemChange, ...]

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "start_at": _timestamp(self.start_at),
            "end_at": _timestamp(self.end_at),
            "boundary_snap_id": self.boundary_snap_id,
            "boundary_snap_time": _timestamp(self.boundary_snap_time),
            "start_coverage": self.start_coverage.as_dict(),
            "end_coverage": self.end_coverage.as_dict(),
            "changes": [change.as_dict() for change in self.changes],
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
    components = _component_map(snap)
    if component_name not in components:
        return False, None
    component = components[component_name]
    if not isinstance(component, dict):
        raise InvalidQuery(
            f"snap {snap.pk} component {component_name!r} is not an object"
        )
    return True, component


def _component_map(snap: SystemSnap) -> Dict[str, Dict[str, Any]]:
    _require_full_snap(snap)
    if not isinstance(snap.state, dict):
        raise InvalidQuery(f"snap {snap.pk} does not contain an object state")
    components = snap.state.get("components")
    if not isinstance(components, dict):
        raise InvalidQuery(f"snap {snap.pk} has no object component map")
    for component_name, component in components.items():
        if not isinstance(component_name, str) or not isinstance(
            component,
            dict,
        ):
            raise InvalidQuery(
                f"snap {snap.pk} has an invalid component map"
            )
    return components


def _component_metadata(
    snap: SystemSnap,
    component_name: str,
    component: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    return (
        (snap.component_hashes or {}).get(component_name),
        (snap.registration_versions or {}).get(
            component_name,
            component.get("registration_version") if component else None,
        ),
        (snap.component_revisions or {}).get(
            component_name,
            component.get("revision") if component else None,
        ),
    )


def _recovery_evidence(
    snap: SystemSnap,
) -> Tuple[Tuple[str, ...], bool, bool]:
    reasons = tuple(snap.reasons) if isinstance(snap.reasons, list) else ()
    start_unknown = (
        snap.recovered_gap_started_at is None
        and (
            snap.recovered_gap_start_unknown is not False
            or "recovery" in reasons
        )
    )
    is_recovery = (
        snap.recovered_gap_started_at is not None or start_unknown
    )
    return reasons, is_recovery, start_unknown


def _component_signature(
    snap: SystemSnap,
    component_name: str,
    present: bool,
    component: Optional[Dict[str, Any]],
) -> tuple:
    if not present or component is None:
        return (False,)
    component_hash, registration_version, revision = _component_metadata(
        snap,
        component_name,
        component,
    )
    if component_hash is None:
        component_hash = json.dumps(
            component.get("data"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
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
    component_hash, registration_version, revision = _component_metadata(
        snap,
        component_name,
        component,
    )
    reasons, _, recovered_gap_start_unknown = _recovery_evidence(snap)
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
        component_hash=component_hash,
        registration_version=registration_version,
        revision=revision,
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
        _, is_recovery, _ = _recovery_evidence(snap)
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


def changes_between(
    scope: str,
    start: datetime,
    end: datetime,
) -> ChangesBetweenResult:
    """Return derived component changes after ``start`` through ``end``."""
    scope = _bounded_scope(scope)
    start_at = _aware_time(start, "start")
    end_at = _aware_time(end, "end")
    if start_at > end_at:
        raise InvalidQuery("start must not be later than end")

    boundary_snap = _snap_at(scope, start_at)
    end_snap = _snap_at(scope, end_at)
    previous_snap = boundary_snap
    previous_components = _component_map(boundary_snap)
    changes = []

    interval_snaps = SystemSnap.objects.filter(
        scope=scope,
        snap_time__gt=start_at,
        snap_time__lte=end_at,
    ).order_by("snap_time")
    for snap in interval_snaps:
        current_components = _component_map(snap)
        component_changes = []
        for component_name in sorted(
            set(previous_components) | set(current_components)
        ):
            previous = previous_components.get(component_name)
            current = current_components.get(component_name)
            previous_present = previous is not None
            current_present = current is not None
            previous_signature = _component_signature(
                previous_snap,
                component_name,
                previous_present,
                previous,
            )
            current_signature = _component_signature(
                snap,
                component_name,
                current_present,
                current,
            )
            if previous_signature == current_signature:
                continue
            if not previous_present:
                kind = "added"
            elif not current_present:
                kind = "removed"
            else:
                kind = "changed"
            previous_hash, previous_registration, previous_revision = (
                _component_metadata(
                    previous_snap,
                    component_name,
                    previous,
                )
            )
            current_hash, current_registration, current_revision = (
                _component_metadata(
                    snap,
                    component_name,
                    current,
                )
            )
            component_changes.append(
                ChangedComponent(
                    name=component_name,
                    kind=kind,
                    previous_hash=previous_hash,
                    current_hash=current_hash,
                    previous_registration_version=previous_registration,
                    current_registration_version=current_registration,
                    previous_revision=previous_revision,
                    current_revision=current_revision,
                    previous=deepcopy(previous),
                    current=deepcopy(current),
                )
            )

        reasons, is_recovery, start_unknown = _recovery_evidence(snap)
        schema_changed = (
            snap.snap_schema_version != previous_snap.snap_schema_version
        )
        capture_policy_changed = (
            snap.capture_policy != previous_snap.capture_policy
        )
        if (
            component_changes
            or is_recovery
            or schema_changed
            or capture_policy_changed
        ):
            declared_changed_components = (
                tuple(snap.changed_components)
                if isinstance(snap.changed_components, list)
                else ()
            )
            if is_recovery:
                kind = "recovery"
            elif schema_changed or capture_policy_changed:
                kind = "policy"
            else:
                kind = "change"
            changes.append(
                SystemChange(
                    kind=kind,
                    snap_id=str(snap.pk),
                    snap_time=snap.snap_time,
                    observed_at=snap.observed_at,
                    completed_at=snap.completed_at,
                    previous_snap_schema_version=(
                        previous_snap.snap_schema_version
                    ),
                    snap_schema_version=snap.snap_schema_version,
                    previous_capture_policy=previous_snap.capture_policy,
                    capture_policy=snap.capture_policy,
                    encoding=snap.encoding,
                    state_hash=snap.state_hash,
                    schema_changed=schema_changed,
                    capture_policy_changed=capture_policy_changed,
                    reasons=reasons,
                    declared_changed_components=declared_changed_components,
                    recovered_gap_started_at=snap.recovered_gap_started_at,
                    recovered_gap_start_unknown=start_unknown,
                    components=tuple(component_changes),
                )
            )
        previous_snap = snap
        previous_components = current_components

    return ChangesBetweenResult(
        scope=scope,
        start_at=start_at,
        end_at=end_at,
        boundary_snap_id=str(boundary_snap.pk),
        boundary_snap_time=boundary_snap.snap_time,
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
        changes=tuple(changes),
    )


@dataclass(frozen=True)
class EventReference:
    """One resolvable reference to a registered exact event stream.

    The generic layer names the registered declaration and bounds event
    time; the hosting integration maps ``resolver`` to a concrete API or
    MCP tool and refines ``availability`` (DESIGN.md, Event-reference
    contract).
    """

    component: str
    source: str
    resolver: str
    scope: str
    from_time: Optional[str]
    until_time: Optional[str]
    event_kind: str
    owner: str
    visibility: str
    availability: str

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "source": self.source,
            "resolver": self.resolver,
            "scope": self.scope,
            "from": self.from_time,
            "until": self.until_time,
            "event_kind": self.event_kind,
            "owner": self.owner,
            "visibility": self.visibility,
            "availability": self.availability,
        }


@dataclass(frozen=True)
class ContextAroundResult:
    """Coherent state at an instant, nearby changes, and event references."""

    scope: str
    requested_at: Optional[str]
    window_seconds: float
    state: StateQueryResult
    changes: "ChangesBetweenResult"
    references: tuple

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "requested_at": self.requested_at,
            "window_seconds": self.window_seconds,
            "state": self.state.as_dict(),
            "changes": self.changes.as_dict(),
            "references": [ref.as_dict() for ref in self.references],
        }


def context_around(
    scope: str,
    time: datetime,
    window_seconds: float = 3600.0,
) -> ContextAroundResult:
    """Return state at ``time``, changes in the window around it, and
    resolvable references to the registered exact event streams.

    The window is centered on the requested time. References come from
    the active component registrations' declared event sources; their
    availability is ``unknown`` here — the hosting integration owns the
    resolver mapping and refines it.
    """
    scope = _bounded_scope(scope)
    requested_at = _aware_time(time)
    try:
        window = float(window_seconds)
    except (TypeError, ValueError):
        raise InvalidQuery("window_seconds must be a number")
    if not 0 < window <= 31 * 24 * 3600:
        raise InvalidQuery("window_seconds must be positive and bounded")
    half = timedelta(seconds=window / 2)
    start_at = requested_at - half
    end_at = requested_at + half

    state = state_at(scope, requested_at)
    changes = changes_between(scope, start_at, end_at)

    references = []
    registrations = (
        CurrentComponent.objects.filter(scope=scope, active=True)
        .order_by("name")
        .values("name", "registration")
    )
    for row in registrations:
        registration = row["registration"] or {}
        for declaration in registration.get("event_sources") or []:
            if not isinstance(declaration, dict):
                continue
            references.append(EventReference(
                component=row["name"],
                source=str(declaration.get("name") or ""),
                resolver=str(declaration.get("resolver") or ""),
                scope=scope,
                from_time=_timestamp(start_at),
                until_time=_timestamp(end_at),
                event_kind=str(declaration.get("event_kind") or ""),
                owner=str(declaration.get("owner") or ""),
                visibility=str(declaration.get("visibility") or ""),
                availability="unknown",
            ))

    return ContextAroundResult(
        scope=scope,
        requested_at=_timestamp(requested_at),
        window_seconds=window,
        state=state,
        changes=changes,
        references=tuple(references),
    )
