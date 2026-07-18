from datetime import datetime, timedelta, timezone

from django.test import TestCase

from snapper_ai.capture import capture_scope, report_capture_failure
from snapper_ai.models import CaptureCursor, CurrentComponent


class RecoveryGapCaptureTests(TestCase):
    def setUp(self):
        self.at = datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc)
        CurrentComponent.objects.create(
            scope="epicprod",
            name="health",
            publisher_identity="test:health",
            registration={},
            registration_hash="registration-hash",
            data={"status": "ok"},
            content_hash="content-hash",
            revision=1,
            assessed_at=self.at,
            accepted_at=self.at,
            changed_at=self.at,
        )

    def _capture(self, at):
        return capture_scope(
            scope="epicprod",
            boundary_at=at,
            capture_policy="epicprod-v1",
            opportunity_seconds=30,
            baseline_every=10,
        )

    def test_recovery_snap_persists_reported_gap_start(self):
        self._capture(self.at)
        gap_started_at = self.at + timedelta(seconds=30)
        report_capture_failure(
            scope="epicprod",
            boundary_at=gap_started_at,
            error="observer unavailable",
        )

        result = self._capture(self.at + timedelta(seconds=60))

        self.assertEqual(result.reasons, ("recovery",))
        self.assertEqual(
            result.snap.recovered_gap_started_at,
            gap_started_at,
        )
        self.assertFalse(result.snap.recovered_gap_start_unknown)
        self.assertEqual(
            result.snap.state["recovered_gap_started_at"],
            "2026-07-18T13:30:30Z",
        )
        cursor = CaptureCursor.objects.get(scope="epicprod")
        self.assertIsNone(cursor.coverage_gap_started_at)

    def test_recovery_snap_persists_implicitly_missed_boundary(self):
        self._capture(self.at)

        result = self._capture(self.at + timedelta(seconds=60))

        self.assertEqual(result.reasons, ("recovery",))
        self.assertEqual(
            result.snap.recovered_gap_started_at,
            self.at + timedelta(seconds=30),
        )
