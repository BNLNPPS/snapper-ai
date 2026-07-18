from datetime import datetime, timedelta, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RecoveryGapMigrationTests(TransactionTestCase):
    migrate_from = ("snapper_ai", "0001_initial")
    migrate_to = ("snapper_ai", "0002_systemsnap_recovery_gap")

    def test_existing_recovery_snaps_are_marked_start_unknown(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldSystemSnap = old_apps.get_model("snapper_ai", "SystemSnap")
        at = datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc)
        recovery = OldSystemSnap.objects.create(
            scope="epicprod",
            snap_time=at,
            observed_at=at + timedelta(seconds=2),
            completed_at=at + timedelta(seconds=2, milliseconds=5),
            capture_policy="epicprod-v1",
            reasons=["baseline", "recovery"],
            state_hash="recovery-hash",
            state={},
        )
        ordinary = OldSystemSnap.objects.create(
            scope="epicprod",
            snap_time=at + timedelta(minutes=5),
            observed_at=at + timedelta(minutes=5, seconds=2),
            completed_at=at + timedelta(
                minutes=5,
                seconds=2,
                milliseconds=5,
            ),
            capture_policy="epicprod-v1",
            reasons=["baseline"],
            state_hash="ordinary-hash",
            state={},
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        SystemSnap = new_apps.get_model("snapper_ai", "SystemSnap")

        self.assertTrue(
            SystemSnap.objects.get(pk=recovery.pk).recovered_gap_start_unknown
        )
        self.assertFalse(
            SystemSnap.objects.get(pk=ordinary.pk).recovered_gap_start_unknown
        )
