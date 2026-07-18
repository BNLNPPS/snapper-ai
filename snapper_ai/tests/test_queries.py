from datetime import datetime, timedelta, timezone

from django.test import TestCase

from snapper_ai.models import CaptureCursor, SystemSnap
from snapper_ai.queries import (
    InvalidQuery,
    SnapNotFound,
    UnsupportedEncoding,
    component_history,
    latest,
    state_at,
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


class StateAtQueryTests(TestCase):
    def setUp(self):
        self.at = datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc)

    def _snap(
        self,
        *,
        minutes=0,
        encoding=SystemSnap.Encoding.FULL,
        recovered_gap_started_at=None,
        recovered_gap_start_unknown=False,
    ):
        snap_time = self.at + timedelta(minutes=minutes)
        return SystemSnap.objects.create(
            scope="epicprod",
            snap_time=snap_time,
            observed_at=snap_time + timedelta(seconds=2),
            completed_at=snap_time + timedelta(seconds=2, milliseconds=5),
            capture_policy="epicprod-v1",
            encoding=encoding,
            state_hash=f"hash-{minutes}",
            state={"components": {"panda": {"revision": minutes + 1}}},
            recovered_gap_started_at=recovered_gap_started_at,
            recovered_gap_start_unknown=recovered_gap_start_unknown,
        )

    def test_state_at_returns_latest_eligible_snap_and_actual_time(self):
        older = self._snap(minutes=0)
        newer = self._snap(minutes=5)
        requested_at = self.at + timedelta(minutes=3)

        result = state_at("epicprod", requested_at)

        self.assertEqual(result.snap_id, str(older.pk))
        self.assertEqual(result.snap_time, older.snap_time)
        self.assertEqual(result.requested_at, requested_at)
        self.assertEqual(result.coverage.status, "covered")
        self.assertEqual(result.coverage.checked_through, newer.snap_time)
        self.assertEqual(
            result.as_dict()["requested_at"],
            "2026-07-18T13:33:00Z",
        )

    def test_state_at_reports_known_half_open_recovery_gap(self):
        older = self._snap(minutes=0)
        gap_started_at = self.at + timedelta(minutes=1)
        recovery = self._snap(
            minutes=5,
            recovered_gap_started_at=gap_started_at,
        )

        before_gap = state_at(
            "epicprod",
            self.at + timedelta(seconds=30),
        )
        in_gap = state_at(
            "epicprod",
            self.at + timedelta(minutes=2),
        )
        at_gap_start = state_at("epicprod", gap_started_at)
        at_recovery = state_at("epicprod", recovery.snap_time)

        self.assertEqual(before_gap.coverage.status, "covered")
        self.assertEqual(in_gap.snap_id, str(older.pk))
        self.assertEqual(in_gap.coverage.status, "gap")
        self.assertEqual(in_gap.coverage.gap_started_at, gap_started_at)
        self.assertEqual(in_gap.coverage.gap_ended_at, recovery.snap_time)
        self.assertEqual(at_gap_start.coverage.status, "gap")
        self.assertEqual(at_recovery.coverage.status, "covered")

    def test_state_at_reports_legacy_recovery_start_as_unknown(self):
        for unknown_value in (True, None):
            with self.subTest(unknown_value=unknown_value):
                SystemSnap.objects.all().delete()
                self._snap(minutes=0)
                recovery = self._snap(
                    minutes=5,
                    recovered_gap_start_unknown=unknown_value,
                )

                result = state_at(
                    "epicprod",
                    self.at + timedelta(minutes=2),
                )

                self.assertEqual(result.coverage.status, "unknown")
                self.assertIsNone(result.coverage.gap_started_at)
                self.assertEqual(
                    result.coverage.gap_ended_at,
                    recovery.snap_time,
                )

    def test_state_at_uses_active_gap_and_rejects_unchecked_future(self):
        newest = self._snap(minutes=0)
        gap_started_at = self.at + timedelta(minutes=1)
        CaptureCursor.objects.create(
            scope="epicprod",
            latest_boundary_at=self.at + timedelta(minutes=2),
            latest_check_at=self.at + timedelta(minutes=2, seconds=4),
            heartbeat_at=self.at + timedelta(minutes=2, seconds=4),
            latest_snap=newest,
            coverage_gap_started_at=gap_started_at,
        )

        in_gap = state_at(
            "epicprod",
            self.at + timedelta(minutes=1, seconds=30),
        )
        unchecked = state_at(
            "epicprod",
            self.at + timedelta(minutes=3),
        )

        self.assertEqual(in_gap.coverage.status, "gap")
        self.assertIsNone(in_gap.coverage.gap_ended_at)
        self.assertEqual(unchecked.coverage.status, "unknown")
        self.assertEqual(unchecked.coverage.gap_started_at, gap_started_at)

    def test_state_at_rejects_invalid_or_unavailable_state(self):
        first = self._snap(minutes=0)
        with self.assertRaises(InvalidQuery):
            state_at("epicprod", datetime(2026, 7, 18, 13, 30))
        with self.assertRaises(SnapNotFound):
            state_at("epicprod", first.snap_time - timedelta(seconds=1))
        self._snap(minutes=5, encoding=SystemSnap.Encoding.DELTA)
        with self.assertRaises(UnsupportedEncoding):
            state_at("epicprod", self.at + timedelta(minutes=6))


class ComponentHistoryQueryTests(TestCase):
    def setUp(self):
        self.at = datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc)

    def _snap(
        self,
        *,
        minutes,
        revision=None,
        reasons=None,
        recovered_gap_started_at=None,
        recovered_gap_start_unknown=False,
    ):
        snap_time = self.at + timedelta(minutes=minutes)
        if revision is None:
            components = {}
            component_revisions = {}
            registration_versions = {}
            component_hashes = {}
        else:
            components = {
                "panda": {
                    "v": 3,
                    "registration_version": 3,
                    "revision": revision,
                    "publisher_identity": "swf-monitor:panda-activity",
                    "assessed_at": snap_time.isoformat(),
                    "source_as_of": snap_time.isoformat(),
                    "assessment_policy": "epicprod-panda-v3",
                    "data": {"jobs_by_state": {"running": revision}},
                },
            }
            component_revisions = {"panda": revision}
            registration_versions = {"panda": 3}
            component_hashes = {"panda": f"component-hash-{revision}"}
        return SystemSnap.objects.create(
            scope="epicprod",
            snap_time=snap_time,
            observed_at=snap_time + timedelta(seconds=2),
            completed_at=snap_time + timedelta(seconds=2, milliseconds=5),
            capture_policy="epicprod-v1",
            reasons=reasons or ["baseline"],
            changed_components=(
                ["panda"] if reasons and "change" in reasons else []
            ),
            component_revisions=component_revisions,
            registration_versions=registration_versions,
            component_hashes=component_hashes,
            state_hash=f"state-hash-{minutes}",
            state={"components": components},
            recovered_gap_started_at=recovered_gap_started_at,
            recovered_gap_start_unknown=recovered_gap_start_unknown,
        )

    def test_history_begins_at_boundary_and_suppresses_unchanged_baselines(self):
        boundary = self._snap(minutes=0, revision=1)
        self._snap(minutes=5, revision=1)
        changed = self._snap(minutes=10, revision=2, reasons=["change"])
        CaptureCursor.objects.create(
            scope="epicprod",
            latest_boundary_at=self.at + timedelta(minutes=12),
            latest_check_at=self.at + timedelta(minutes=12, seconds=4),
            heartbeat_at=self.at + timedelta(minutes=12, seconds=4),
            latest_snap=changed,
        )

        result = component_history(
            "epicprod",
            "panda",
            self.at + timedelta(minutes=2),
            self.at + timedelta(minutes=12),
        )

        self.assertEqual(
            [entry.kind for entry in result.entries],
            ["boundary", "change"],
        )
        self.assertEqual(result.entries[0].snap_id, str(boundary.pk))
        self.assertFalse(result.entries[0].component_changed)
        self.assertEqual(result.entries[1].snap_id, str(changed.pk))
        self.assertEqual(result.entries[1].revision, 2)
        self.assertEqual(result.start_coverage.status, "covered")
        self.assertEqual(result.end_coverage.status, "covered")
        serialized = result.as_dict()
        self.assertEqual(serialized["component"], "panda")
        self.assertEqual(
            serialized["entries"][1]["component"]["source_as_of"],
            "2026-07-18T13:40:00+00:00",
        )

    def test_history_can_include_unchanged_baselines(self):
        self._snap(minutes=0, revision=1)
        baseline = self._snap(minutes=5, revision=1)

        result = component_history(
            "epicprod",
            "panda",
            self.at + timedelta(minutes=1),
            self.at + timedelta(minutes=5),
            suppress_unchanged_baselines=False,
        )

        self.assertEqual(
            [entry.kind for entry in result.entries],
            ["boundary", "baseline"],
        )
        self.assertEqual(result.entries[1].snap_id, str(baseline.pk))
        self.assertFalse(result.entries[1].component_changed)

    def test_history_keeps_recovery_evidence_when_component_is_unchanged(self):
        self._snap(minutes=0, revision=1)
        gap_started_at = self.at + timedelta(minutes=3)
        recovery = self._snap(
            minutes=5,
            revision=1,
            reasons=["recovery"],
            recovered_gap_started_at=gap_started_at,
        )

        result = component_history(
            "epicprod",
            "panda",
            self.at + timedelta(minutes=2),
            self.at + timedelta(minutes=5),
        )

        self.assertEqual(
            [entry.kind for entry in result.entries],
            ["boundary", "recovery"],
        )
        self.assertEqual(result.entries[1].snap_id, str(recovery.pk))
        self.assertFalse(result.entries[1].component_changed)
        self.assertEqual(
            result.entries[1].recovered_gap_started_at,
            gap_started_at,
        )
        self.assertEqual(result.end_coverage.status, "covered")

    def test_history_records_component_absence_and_later_appearance(self):
        self._snap(minutes=0, revision=None)
        self._snap(minutes=5, revision=1, reasons=["change"])

        result = component_history(
            "epicprod",
            "panda",
            self.at + timedelta(minutes=1),
            self.at + timedelta(minutes=5),
        )

        self.assertFalse(result.entries[0].present)
        self.assertIsNone(result.entries[0].component)
        self.assertEqual(result.entries[1].kind, "change")
        self.assertTrue(result.entries[1].present)

    def test_history_rejects_invalid_interval_or_missing_boundary(self):
        first = self._snap(minutes=0, revision=1)
        with self.assertRaises(InvalidQuery):
            component_history(
                "epicprod",
                " ",
                first.snap_time,
                first.snap_time,
            )
        with self.assertRaises(InvalidQuery):
            component_history(
                "epicprod",
                "panda",
                first.snap_time + timedelta(minutes=1),
                first.snap_time,
            )
        with self.assertRaises(InvalidQuery):
            component_history(
                "epicprod",
                "panda",
                datetime(2026, 7, 18, 13, 30),
                first.snap_time,
            )
        with self.assertRaises(InvalidQuery):
            component_history(
                "epicprod",
                "panda",
                first.snap_time,
                first.snap_time,
                suppress_unchanged_baselines="yes",
            )
        with self.assertRaises(SnapNotFound):
            component_history(
                "epicprod",
                "panda",
                first.snap_time - timedelta(minutes=1),
                first.snap_time,
            )
        delta = SystemSnap.objects.create(
            scope="epicprod",
            snap_time=self.at + timedelta(minutes=5),
            observed_at=self.at + timedelta(minutes=5, seconds=2),
            completed_at=self.at + timedelta(minutes=5, seconds=3),
            capture_policy="epicprod-v1",
            encoding=SystemSnap.Encoding.DELTA,
            state_hash="delta-hash",
            state={"components": {}},
        )
        with self.assertRaises(UnsupportedEncoding):
            component_history(
                "epicprod",
                "panda",
                first.snap_time,
                delta.snap_time,
            )
