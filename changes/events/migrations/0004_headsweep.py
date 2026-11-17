from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_headlevel'),
    ]

    operations = [
        migrations.CreateModel(
            name='HeadSweep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('ch', models.PositiveSmallIntegerField(help_text='1-based channel it was swept in')),
                ('label', models.CharField(blank=True, default='', help_text='the number written on the head', max_length=8)),
                ('end', models.CharField(blank=True, default='', help_text="'' every point; else why it ended early", max_length=40)),
                ('points', models.JSONField(default=list, help_text='[[drive duty, mA, PT volts, PT spread], ...] full drive first')),
                ('drv_before', models.IntegerField(blank=True, null=True)),
                ('thr_before', models.IntegerField(blank=True, null=True)),
                ('suggested_drv', models.IntegerField(blank=True, null=True)),
                ('suggested_thr', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'ordering': ['at'],
            },
        ),
    ]
