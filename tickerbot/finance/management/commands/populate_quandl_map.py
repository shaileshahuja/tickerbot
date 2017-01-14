from django.core.management.base import BaseCommand
from django.conf import settings
import quandl
import csv
from datetime import datetime, timedelta, date
from finance.models import QuandlTickerDatabaseMap


class Command(BaseCommand):
    # def add_arguments(self, parser):
    #     parser.add_argument('database', type=str)

    def handle(self, *args, **options):
        filename = settings.DJANGO_DIR + '/finance/management/data/WIKI_20161126.partial.csv'
        with open(filename, 'r') as handle:
            reader = csv.reader(handle)
            for row in reader:
                latest = datetime.strptime(row[1], "%Y-%m-%d").date()
                if latest + timedelta(days=5) < date.today():
                    continue
                ticker = row[0]
                closing_column = 11
                database = 'WIKI'
                if not QuandlTickerDatabaseMap.objects.filter(ticker=ticker).exists():
                    QuandlTickerDatabaseMap.objects.create(ticker=ticker, database=database,
                                                           closing_column=closing_column)

