from __future__ import unicode_literals

from django.db import models

# Create your models here.


class QuandlTickerDatabaseMap(models.Model):
    ticker = models.CharField(max_length=20, unique=True)
    database = models.CharField(max_length=20)
    closing_column = models.PositiveIntegerField()
