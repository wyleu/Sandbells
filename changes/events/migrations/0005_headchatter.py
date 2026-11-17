from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0004_headsweep'),
    ]

    operations = [
        migrations.CreateModel(
            name='HeadChatter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('ch', models.PositiveSmallIntegerField(help_text='1-based channel')),
                ('label', models.CharField(blank=True, default='', help_text='the number written on the head', max_length=8)),
                ('drv', models.IntegerField(help_text='laser drive duty 0-65535')),
                ('pwm_hz', models.IntegerField(blank=True, help_text='laser PWM frequency the Pico reported', null=True)),
                ('passes', models.IntegerField(blank=True, help_text='sandtest round trips; null: moved by hand', null=True)),
                ('expected', models.IntegerField(blank=True, help_text='transitions the passes should give', null=True)),
                ('trans', models.IntegerField(blank=True, null=True)),
                ('clean', models.IntegerField(blank=True, null=True)),
                ('max_edges', models.IntegerField(blank=True, null=True)),
                ('mean_x10', models.IntegerField(blank=True, null=True)),
                ('max_burst_ms', models.IntegerField(blank=True, null=True)),
                ('spurious', models.IntegerField(blank=True, null=True)),
                ('end', models.CharField(blank=True, default='', help_text="'' a whole run; else why it ended early", max_length=40)),
            ],
            options={
                'ordering': ['at'],
            },
        ),
    ]
