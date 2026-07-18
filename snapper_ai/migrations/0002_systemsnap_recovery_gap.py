from django.db import migrations, models


def mark_legacy_recoveries(apps, schema_editor):
    SystemSnap = apps.get_model("snapper_ai", "SystemSnap")
    legacy_ids = []
    for snap in SystemSnap.objects.only("pk", "reasons").iterator(
        chunk_size=1000
    ):
        if isinstance(snap.reasons, list) and "recovery" in snap.reasons:
            legacy_ids.append(snap.pk)
        if len(legacy_ids) == 1000:
            SystemSnap.objects.filter(pk__in=legacy_ids).update(
                recovered_gap_start_unknown=True
            )
            legacy_ids.clear()
    if legacy_ids:
        SystemSnap.objects.filter(pk__in=legacy_ids).update(
            recovered_gap_start_unknown=True
        )


def clear_legacy_recoveries(apps, schema_editor):
    SystemSnap = apps.get_model("snapper_ai", "SystemSnap")
    SystemSnap.objects.filter(recovered_gap_start_unknown=True).update(
        recovered_gap_start_unknown=False
    )


class Migration(migrations.Migration):

    dependencies = [
        ("snapper_ai", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsnap",
            name="recovered_gap_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsnap",
            name="recovered_gap_start_unknown",
            field=models.BooleanField(default=False, null=True),
        ),
        migrations.RunPython(
            mark_legacy_recoveries,
            clear_legacy_recoveries,
        ),
        migrations.AddConstraint(
            model_name="systemsnap",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(recovered_gap_started_at__isnull=True)
                    | (
                        models.Q(recovered_gap_start_unknown__isnull=False)
                        & models.Q(recovered_gap_start_unknown=False)
                    )
                ),
                name="snapper_recovery_gap_evidence_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="systemsnap",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(recovered_gap_started_at__isnull=True)
                    | models.Q(
                        recovered_gap_started_at__lt=models.F("snap_time")
                    )
                ),
                name="snapper_recovery_gap_order_ck",
            ),
        ),
    ]
