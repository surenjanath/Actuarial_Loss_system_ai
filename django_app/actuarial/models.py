from __future__ import annotations

import uuid

from django.db import models


class OrganizationProfile(models.Model):
    """
    Singleton row (pk=1): organization branding for crew reports and exports.
    Persisted in the database so settings survive sessions and server restarts.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    company_name = models.CharField(max_length=200, blank=True, default='')
    legal_name = models.CharField(max_length=200, blank=True, default='')
    address = models.TextField(max_length=500, blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    region = models.CharField(max_length=120, blank=True, default='')
    postal_code = models.CharField(max_length=32, blank=True, default='')
    country = models.CharField(max_length=120, blank=True, default='')
    phone = models.CharField(max_length=80, blank=True, default='')
    email = models.CharField(max_length=120, blank=True, default='')
    website = models.CharField(max_length=500, blank=True, default='')
    logo_url = models.CharField(max_length=500, blank=True, default='')
    tagline = models.CharField(max_length=300, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organization profile'
        verbose_name_plural = 'Organization profile'

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.company_name.strip() or 'Organization profile'


class WorkspaceState(models.Model):
    """
    Singleton (pk=1): crew pipeline, personalization, Ollama overrides, actuarial mock seed.
    Replaces browser-session storage so configuration survives cookies and restarts.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    pipeline_json = models.JSONField(default=list)
    member_overrides_json = models.JSONField(default=dict)
    global_instructions = models.TextField(blank=True, default='')
    ollama_base_url = models.CharField(max_length=512, blank=True, default='')
    ollama_model = models.CharField(max_length=200, blank=True, default='')
    crew_timeout_sec = models.PositiveIntegerField(null=True, blank=True)
    actuarial_seed = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Workspace state'
        verbose_name_plural = 'Workspace state'

    def save(self, *args, **kwargs) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return 'Workspace state'


class CrewRun(models.Model):
    """One CrewAI pipeline execution (session-scoped; optional member focus for learnings)."""

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        PENDING_APPROVAL = 'pending_approval', 'Pending approval'
        APPROVED = 'approved', 'Approved'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Workspace scope key (fixed); not the Django browser session id.',
    )
    member_id = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        db_index=True,
        help_text='Optional roster member id for cross-run coaching match.',
    )
    topic = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    pipeline_snapshot = models.JSONField(default=list)
    dataset_summary_snapshot = models.TextField(
        blank=True,
        default='',
        help_text='Full kickoff dataset summary (for background workers / audit).',
    )
    global_instructions_snapshot = models.TextField(blank=True)
    ollama_base_url = models.CharField(max_length=512, blank=True)
    ollama_model = models.CharField(max_length=200, blank=True)
    timeout_sec = models.PositiveIntegerField(default=600)
    final_report_text = models.TextField(blank=True)
    report_draft_versions = models.JSONField(
        null=True,
        blank=True,
        help_text='Optional list of {step_index, preview} for debugging.',
    )
    chain_summary = models.TextField(
        blank=True,
        help_text='Crew kickoff raw result string when available.',
    )
    error_message = models.TextField(blank=True)
    live_report_text = models.TextField(
        blank=True,
        default='',
        help_text='Latest board-report draft during run (denormalized for fast polling).',
    )
    live_report_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When live_report_text was last updated.',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_report_pdf = models.FileField(
        upload_to='crew_approved/%Y/%m/',
        blank=True,
        null=True,
        help_text='Generated when the run is approved; stored under MEDIA_ROOT.',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session_key', '-created_at']),
            models.Index(fields=['session_key', 'member_id', '-created_at']),
        ]

    def __str__(self) -> str:
        return f'CrewRun {self.id} {self.status}'


class CrewStepOutput(models.Model):
    """Per-task transcript (working papers / coaching / final report step)."""

    run = models.ForeignKey(
        CrewRun,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    step_index = models.PositiveSmallIntegerField()
    step_kind = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=200, blank=True)
    content = models.TextField(blank=True)
    ollama_model = models.CharField(max_length=200, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['step_index']
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'step_index'],
                name='uniq_crew_step_per_run_index',
            ),
        ]

    def __str__(self) -> str:
        return f'Step {self.step_index} ({self.step_kind}) run={self.run_id}'


class CrewReportVersion(models.Model):
    """Intermediate report bodies per pipeline step (optional persistence from streaming)."""

    run = models.ForeignKey(
        CrewRun,
        on_delete=models.CASCADE,
        related_name='report_versions',
    )
    step_index = models.PositiveSmallIntegerField()
    step_kind = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=200, blank=True)
    report_body = models.TextField(blank=True)
    source_raw = models.TextField(
        blank=True,
        help_text='Full model output for this step (optional).',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['step_index', 'id']


class CrewRunEvent(models.Model):
    """Sequential events for a run (e.g. SSE replay or worker audit)."""

    run = models.ForeignKey(
        CrewRun,
        on_delete=models.CASCADE,
        related_name='run_events',
    )
    seq = models.PositiveIntegerField()
    event_type = models.CharField(max_length=32, db_index=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seq']
        indexes = [
            models.Index(fields=['run', 'seq'], name='actuarial_c_run_id_d13f85_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'seq'],
                name='uniq_crew_run_event_seq',
            ),
        ]
