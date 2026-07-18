"""Deterministic temporal retrieval over immutable Snapper history."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Dict, Optional

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


def _aware_time(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise InvalidQuery("time must be a timezone-aware datetime")
    return value


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
    if snap.encoding != SystemSnap.Encoding.FULL:
        raise UnsupportedEncoding(
            f"cannot reconstruct {snap.encoding!r} snap {snap.pk}"
        )
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
