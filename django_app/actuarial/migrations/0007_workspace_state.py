from django.db import migrations, models


def merge_crew_runs_to_workspace_scope(apps, schema_editor):
    CrewRun = apps.get_model('actuarial', 'CrewRun')
    CrewRun.objects.all().update(session_key='default')


class Migration(migrations.Migration):

    dependencies = [
        ('actuarial', '0006_crewrun_approved_pdf'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkspaceState',
            fields=[
                (
                    'id',
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ('pipeline_json', models.JSONField(default=list)),
                ('member_overrides_json', models.JSONField(default=dict)),
                ('global_instructions', models.TextField(blank=True, default='')),
                (
                    'ollama_base_url',
                    models.CharField(blank=True, default='', max_length=512),
                ),
                (
                    'ollama_model',
                    models.CharField(blank=True, default='', max_length=200),
                ),
                (
                    'crew_timeout_sec',
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ('actuarial_seed', models.PositiveIntegerField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Workspace state',
                'verbose_name_plural': 'Workspace state',
            },
        ),
        migrations.RunPython(merge_crew_runs_to_workspace_scope, migrations.RunPython.noop),
    ]
