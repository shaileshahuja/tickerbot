# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2016-11-27 14:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='QuandlTickerDatabaseMap',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ticker', models.CharField(max_length=20, unique=True)),
                ('database', models.CharField(max_length=20)),
                ('closing_column', models.PositiveIntegerField()),
            ],
        ),
    ]