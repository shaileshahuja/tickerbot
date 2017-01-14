from __future__ import unicode_literals
from django.db import models
from finance import PriceAPI
from collections import defaultdict


DEFAULT_CASH = 10000.00
NOTIFY_DAILY = 'daily'
NOTIFY_WEEKLY = 'weekly'
NOTIFY_OFF = 'off'
NOTIFICATION_CHOICES = [(NOTIFY_DAILY, 'Daily'), (NOTIFY_WEEKLY, 'Weekly'), (NOTIFY_OFF, 'off')]


class SlackAuth(models.Model):
    access_token = models.CharField(max_length=200)
    team_id = models.CharField(max_length=30, unique=True)
    team_name = models.CharField(max_length=200)
    bot_id = models.CharField(max_length=30)
    bot_access_token = models.CharField(max_length=200)
    general_channel_id = models.CharField(max_length=30, null=True, blank=True)


class TalkUser(models.Model):
    email = models.EmailField()
    name = models.CharField(max_length=300)
    slack_id = models.CharField(max_length=30, null=True, blank=True)
    slack_auth = models.ForeignKey(to=SlackAuth, null=True, blank=True)

    notification_frequency = models.CharField(choices=NOTIFICATION_CHOICES, max_length=20, default=NOTIFY_WEEKLY)
    cash = models.FloatField(default=DEFAULT_CASH)
    reset_on = models.DateTimeField(auto_now_add=True)

    @property
    def value(self):
        total = self.cash
        for entry in self.portfolio_entries.all():
            total += entry.value
        return total

    def find_entry(self, ticker):
        for entry in self.portfolio_entries.all():
            if ticker == entry.ticker:
                return entry
        return None

    def portfolio_on(self, on):
        portfolio = defaultdict(int)
        for entry in self.portfolio_entries.all():
            portfolio[entry.ticker] = entry.quantity
        cash = self.cash
        for history in self.transactionhistory_set.filter(created__gt=on).order_by('-created'):
            if history.buy:
                portfolio[history.ticker] -= history.quantity
                cash += history.amount
            else:
                portfolio[history.ticker] += history.quantity
                cash -= history.amount
        return portfolio, cash

    def value_on(self, on):
        if on < self.reset_on.date():
            return DEFAULT_CASH
        try:
            return self.portfoliovalue_set.get(on=on).value
        except PortfolioValue.DoesNotExist:
            portfolio, cash = self.portfolio_on(on)
            for ticker, quantity in portfolio.iteritems():
                if quantity == 0:
                    continue
                value = PriceAPI.get_value_on(ticker, on)
                cash += value * quantity
            PortfolioValue.objects.create(on=on, talk_user=self, value=cash)
            return cash

    @property
    def natural_identifier(self):
        return self.email if not self.name else self.name


class PortfolioEntry(models.Model):
    ticker = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField()
    talk_user = models.ForeignKey(TalkUser, related_name='portfolio_entries')

    @property
    def value(self):
        return PriceAPI.get_current_value(self.ticker) * self.quantity

    class Meta:
        unique_together = ('ticker', 'talk_user')


class TransactionHistory(models.Model):
    talk_user = models.ForeignKey(TalkUser)
    ticker = models.CharField(max_length=10)
    quantity = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)
    amount = models.FloatField()
    buy = models.BooleanField()


class PortfolioValue(models.Model):
    on = models.DateField()
    value = models.FloatField()
    talk_user = models.ForeignKey(to=TalkUser)

    class Meta:
        unique_together = ('on', 'talk_user')
