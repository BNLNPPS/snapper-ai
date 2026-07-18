from datetime import datetime, timedelta, timezone

from django.test import TestCase

from snapper_ai.models import CaptureCursor, SystemSnap
from snapper_ai.queries import (
    InvalidQuery,
    SnapNotFound,
    UnsupportedEncoding,
    latest,
)


class LatestQueryTests(TestCase):
    def setUp(self):
        self.at = datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc)

    def _snap(self, *, minutes=0, encoding=SystemSnap.Encoding.FULL):
        snap_time = self.at + timedelta(minutes=minutes)
        return SystemSnap.objects.create(
            scope="epicprod",
            snap_time=snap_time,
            observed_at=snap_time + timedelta(seconds=2),
            completed_at=snap_time + timedelta(seconds=2, milliseconds=5),
            capture_policy="epicprod-v1",
            encoding=encoding,
            state_hash=f"hash-{minutes}",
            state={
                "v": 1,
                "scope": "epicprod",
                "snap_time": snap_time.isoformat(),
                "components": {"panda": {"revision": minutes + 1}},
            },
        )

    def test_latest_returns_newest_snap_with_actual_time_and_coverage(self):
        self._snap(minutes=0)
        newest = self._snap(minutes=5)
        CaptureCursor.objects.create(
            scope="epicprod",
            latest_boundary_at=newest.snap_time + timedelta(seconds=30),
            latest_check_at=newest.snap_time + timedelta(seconds=34),
            heartbeat_at=newest.snap_time + timedelta(seconds=34),
            latest_snap=newest,
        )

        result = latest(" epicprod ")

        self.assertEqual(result.snap_id, str(newest.pk))
        self.assertEqual(result.snap_time, newest.snap_time)
        self.assertIsNone(result.requested_at)
        self.assertEqual(result.coverage.status, "covered")
        serialized = result.as_dict()
        self.assertEqual(
            serialized["actual_snap_time"],
            "2026-07-18T13:35:00Z",
        )
        self.assertEqual(
            serialized["state"]["components"]["panda"]["revision"],
            6,
        )

    def test_latest_reports_active_coverage_gap(self):
        newest = self._snap()
        gap_started_at = newest.snap_time + timedelta(seconds=30)
        CaptureCursor.objects.create(
            scope="epicprod",
            latest_boundary_at=gap_started_at,
            latest_check_at=gap_started_at + timedelta(seconds=4),
            heartbeat_at=gap_started_at + timedelta(seconds=4),
            latest_snap=newest,
            coverage_gap_started_at=gap_started_at,
        )

        result = latest("epicprod")

        self.assertEqual(result.coverage.status, "gap")
        self.assertEqual(result.coverage.gap_started_at, gap_started_at)

    def test_latest_reports_unknown_coverage_without_cursor(self):
        self._snap()

        result = latest("epicprod")

        self.assertEqual(result.coverage.status, "unknown")
        self.assertIsNone(result.coverage.checked_through)

    def test_latest_rejects_invalid_or_unavailable_state(self):
        with self.assertRaises(InvalidQuery):
            latest(" ")
        with self.assertRaises(SnapNotFound):
            latest("testbed")
        self._snap(encoding=SystemSnap.Encoding.DELTA)
        with self.assertRaises(UnsupportedEncoding):
            latest("epicprod")
