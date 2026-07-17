"""Persistent state for Snapper's component registry and coherent history."""

import uuid

from django.db import models


class CurrentComponent(models.Model):
    """The latest accepted registration and state for one scoped component."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    publisher_identity = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    registration = models.JSONField(default=dict)
    component_schema_version = models.PositiveIntegerField(default=1)
    registration_version = models.PositiveBigIntegerField(default=1)
    registration_hash = models.CharField(max_length=64)

    data = models.JSONField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default="")
    revision = models.PositiveBigIntegerField(default=0)

    assessed_at = models.DateTimeField(null=True, blank=True)
    source_as_of = models.DateTimeField(null=True, blank=True)
    assessment_policy_version = models.CharField(
        max_length=100, blank=True, default=""
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snapper_current_component"
        ordering = ["scope", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "name"],
                name="snapper_comp_scope_name_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["scope", "active", "name"],
                name="snapper_comp_scope_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.scope}:{self.name}@{self.revision}"


class SystemSnap(models.Model):
    """One immutable logical state captured at an aligned scope boundary."""

    class Encoding(models.TextChoices):
        FULL = "full", "Full"
        DELTA = "delta", "Component delta"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=100)
    snap_time = models.DateTimeField()
    observed_at = models.DateTimeField()
    completed_at = models.DateTimeField()

    snap_schema_version = models.PositiveIntegerField(default=1)
    capture_policy = models.CharField(max_length=100)
    encoding = models.CharField(
        max_length=16,
        choices=Encoding.choices,
        default=Encoding.FULL,
    )
    reasons = models.JSONField(default=list)
    changed_components = models.JSONField(default=list)
    component_revisions = models.JSONField(default=dict)
    registration_versions = models.JSONField(default=dict)
    component_hashes = models.JSONField(default=dict)
    state_hash = models.CharField(max_length=64)
    state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "snapper_system_snap"
        ordering = ["scope", "-snap_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "snap_time"],
                name="snapper_snap_scope_time_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["scope", "-snap_time"],
                name="snapper_snap_scope_time_idx",
            ),
        ]

    def __str__(self):
        return f"{self.scope}@{self.snap_time.isoformat()}"


class CaptureCursor(models.Model):
    """Bounded scheduler state for one scope."""

    scope = models.CharField(max_length=100, primary_key=True)
    observed_revisions = models.JSONField(default=dict)
    observed_hashes = models.JSONField(default=dict)
    latest_boundary_at = models.DateTimeField(null=True, blank=True)
    latest_check_at = models.DateTimeField(null=True, blank=True)
    latest_snap = models.ForeignKey(
        SystemSnap,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="capture_cursors",
    )
    baseline_progress = models.PositiveIntegerField(default=0)
    scheduler_result = models.JSONField(default=dict)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    coverage_gap_started_at = models.DateTimeField(null=True, blank=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snapper_capture_cursor"
        ordering = ["scope"]

    def __str__(self):
        return self.scope
