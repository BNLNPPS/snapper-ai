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
    """Latest known scheduler coverage for one scope."""

    status: str
    checked_through: Optional[datetime]
    checked_at: Optional[datetime]
    gap_started_at: Optional[datetime]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "checked_through": _timestamp(self.checked_through),
            "checked_at": _timestamp(self.checked_at),
            "gap_started_at": _timestamp(self.gap_started_at),
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
        )
    return ObserverCoverage(
        status="gap" if cursor.coverage_gap_started_at else "covered",
        checked_through=cursor.latest_boundary_at,
        checked_at=cursor.latest_check_at,
        gap_started_at=cursor.coverage_gap_started_at,
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
    if snap.encoding != SystemSnap.Encoding.FULL:
        raise UnsupportedEncoding(
            f"cannot reconstruct {snap.encoding!r} snap {snap.pk}"
        )
    if not isinstance(snap.state, dict):
        raise InvalidQuery(f"snap {snap.pk} does not contain an object state")
    return StateQueryResult(
        scope=scope,
        requested_at=None,
        snap_id=str(snap.pk),
        snap_time=snap.snap_time,
        observed_at=snap.observed_at,
        completed_at=snap.completed_at,
        snap_schema_version=snap.snap_schema_version,
        capture_policy=snap.capture_policy,
        encoding=snap.encoding,
        state_hash=snap.state_hash,
        state=deepcopy(snap.state),
        coverage=_coverage(cursor),
    )
