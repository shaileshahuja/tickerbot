# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2016-11-21 17:17
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('insights', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PortfolioValue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('on', models.DateField()),
                ('value', models.FloatField()),
                ('talk_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='insights.TalkUser')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='portfolioentry',
            unique_together=set([('ticker', 'talk_user')]),
        ),
        migrations.AlterUniqueTogether(
            name='portfoliovalue',
            unique_together=set([('on', 'talk_user')]),
        ),
    ]
