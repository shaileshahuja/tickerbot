import json
import logging
import uuid
from datetime import datetime, date
from random import choice, randint
from celery import group
import numpy as np
import plotly.graph_objs as go
import plotly.offline as offline
import plotly.plotly as py
from celery.app import shared_task
from dateutils import relativedelta
from django.conf import settings
from django.core.mail.message import EmailMultiAlternatives
from django.db import transaction
from slackclient import SlackClient
from finance import PriceAPI
 

from insights import SlackMessage
from insights.models import TalkUser, PortfolioEntry, TransactionHistory, SlackAuth, NOTIFY_OFF, NOTIFY_WEEKLY

logger = logging.getLogger(__name__)


def parse_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def pretty_date(date_obj):
    return date_obj.strftime("%d %b %Y")


@shared_task
def plot_ticker(talk_user_id, ticker, date_period):
    start_date, end_date = split_date_period(date_period)
    logger.info(ticker + ": " + date_period)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    data = PriceAPI.get_historical(ticker, start_date, end_date)
    title = ticker + ' price from ' + pretty_date(start_date) + " to " + pretty_date(end_date)
    graph_url = plot_graph([get_stock_scatter_trace(data, ticker)], title)
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_image(graph_url,
                                                                                       [{"text": "get insights",
                                                                                         "value": "get insights"},
                                                                                        {"text": "compare with sp500",
                                                                                         "value": "compare with spy"}])


@shared_task
def price_ticker(talk_user_id, ticker, price_date):
    logger.info(ticker + ": " + price_date)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    if not price_date or price_date == date.today():
        price_date = datetime.now()
        price = PriceAPI.get_current_value(ticker)
        printed_date = price_date.strftime("%r, %a, %d %b %Y")
    else:
        price_date = parse_date(price_date)
        buffer_date = price_date - relativedelta(days=3)
        price = PriceAPI.get_historical(ticker, buffer_date, price_date)[0]['value']
        printed_date = pretty_date(price_date)
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_text(
        ticker + " price on " + printed_date + ": *USD " + str(price) + "*",
        [{"text": "buy", "value": "buy {}".format(ticker)}, {"text": "sell", "value": "sell {}".format(ticker)}])


@shared_task
def compare_tickers(talk_user_id, new_ticker, base_ticker, date_period):
    logger.info(new_ticker + ": " + base_ticker + ": " + str(date_period))
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    start_date, end_date = split_date_period(date_period)
    data_base = PriceAPI.get_historical(base_ticker, start_date, end_date)
    data_new = PriceAPI.get_historical(new_ticker, start_date, end_date)
    title = "Comparison of " + base_ticker + " with " + new_ticker + " from " + pretty_date(start_date) + " to " \
            + pretty_date(end_date)
    graph_url = plot_graph(
        [get_stock_scatter_trace(data_base, base_ticker), get_stock_scatter_trace(data_new, new_ticker)],
        title)
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_image(graph_url)


@shared_task
def ticker_insights(talk_user_id, ticker, date_period):
    def change(start, end):
        return (end - start) / start * 100

    logger.info(ticker + ": " + str(date_period))
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    insights = []
    start_date, end_date = split_date_period(date_period)
    data = PriceAPI.get_historical(ticker, start_date, end_date)
    ar = np.array([(row['date'], float(row['value'])) for row in data], dtype=[('date', 'S10'), ('price', float)])
    ar = np.sort(ar, order='date')
    first = ar['price'][0]
    last = ar['price'][-1]
    avg = np.average(ar['price'])
    std = np.std(ar['price'])
    max = np.max(ar['price'])
    min = np.min(ar['price'])
    drop_from_max = abs(change(max, last))
    rise_from_min = change(min, last)
    change_total = change(first, last)
    insights.append("The price has dropped *{:.2f}%* from its peak".format(drop_from_max))
    insights.append("The price has risen *{:.2f}%* from its low".format(rise_from_min))
    insights.append("The price changed by *{:.2f}%* from start to end".format(change_total))
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    for insight in insights:
        sm.send_text(insight)


@shared_task
def buying_price(talk_user_id, ticker, quantity):
    logger.debug(ticker + ": " + quantity)
    quantity = int(quantity)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    price = PriceAPI.get_current_value(ticker)
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    sm.send_text("Are you sure you want to buy {} share(s) of {} for ${:.2f}? "
                 "(price might be different on trade execution)".format(quantity, ticker, price * quantity),
                 [{"text": "yes", "value": "yes"}, {"text": "no", "value": "no"}])


@shared_task
def selling_price(talk_user_id, ticker, quantity):
    logger.debug(ticker + ": " + quantity)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    if quantity:
        quantity = int(quantity)
    price = PriceAPI.get_current_value(ticker)
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    entry = talk_user.find_entry(ticker)
    if entry is None:
        quantity = 0
    else:
        if not quantity or quantity > entry.quantity:
            quantity = entry.quantity
    sm.send_text("Are you sure you want to sell {} share(s) of {} for ${:.2f}? "
                 "(price might be different on trade execution)".format(quantity, ticker, price * quantity),
                 [{"text": "yes", "value": "yes"}, {"text": "no", "value": "no"}])


@shared_task
def purchase_shares(talk_user_id, ticker, quantity):
    logger.debug(ticker + ": " + quantity + ": " + str(talk_user_id))
    quantity = int(quantity)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    price = PriceAPI.get_current_value(ticker)
    amount = price * quantity
    if talk_user.cash < amount:
        SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_text(
            "You don't have enough funds to "
            "buy {} share(s) of {} for ${:.2f}".format(quantity, ticker,
                                                       amount))
        return
    with transaction.atomic():
        talk_user.cash -= amount
        talk_user.save()
        entry = talk_user.find_entry(ticker)
        if entry is None:
            PortfolioEntry.objects.create(talk_user=talk_user, quantity=quantity, ticker=ticker)
        else:
            entry.quantity += quantity
            entry.save()
        TransactionHistory.objects.create(talk_user=talk_user, quantity=quantity, ticker=ticker,
                                          amount=amount, buy=True)
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_text(
        "Transaction complete. You have ${:.2f} left in your account".format(talk_user.cash),
        [{"text": "portfolio", "value": "portfolio"}])


@shared_task
def sell_shares(talk_user_id, ticker, quantity):
    logger.debug(ticker + ": " + quantity + ": " + str(talk_user_id))
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    if quantity:
        quantity = int(quantity)
    price = PriceAPI.get_current_value(ticker)
    entry = talk_user.find_entry(ticker)
    if entry is None:
        sm.send_text("There is no point to this...")
        return
    else:
        if not quantity or quantity > entry.quantity:
            quantity = entry.quantity
    amount = price * quantity
    with transaction.atomic():
        talk_user.cash += amount
        talk_user.save()
        if entry.quantity > quantity:
            entry.quantity -= quantity
            entry.save()
        else:
            entry.delete()
        TransactionHistory.objects.create(talk_user=talk_user, quantity=quantity, ticker=ticker,
                                          amount=amount, buy=False)
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_text(
        "Transaction complete. You have ${:.2f} left in your account".format(talk_user.cash),
        [{"text": "portfolio", "value": "portfolio"}])


@shared_task
def portfolio(talk_user_id):
    logger.debug(talk_user_id)
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    total = talk_user.cash
    for entry in talk_user.portfolio_entries.all():
        value = entry.value
        sm.send_text("{} share(s) of {}: ${:.2f}".format(entry.quantity, entry.ticker, value)
                     # ,[{"text": "buy", "value": "buy {}".format(entry.ticker)},
                     #  {"text": "sell", "value": "sell {}".format(entry.ticker)}]
                     )
        total += value
    sm.send_text("Cash: ${:.2f}".format(talk_user.cash))
    sm.send_text("Total portfolio value: ${:.2f}".format(total))


@shared_task
def help(talk_user_id):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    sm = SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id)
    sm.send_text("You can view this again",
                 [
                     # {"text": "login", "value": "login"},
                     # {"text": "register", "value": "register"},
                     {"text": "help", "value": "help"}])

    sm.send_text("You can request for historical price plots. Afterwards, you can get insights or"
                 " compare with other tickers",
                 [{"text": "goog 17 oct to 10 nov", "value": "goog 17 oct to 10 nov"},
                  {"text": "apple last month", "value": "apple last month"}])

    sm.send_text("You can request for current price or price on a specific day",
                 [{"text": "yahoo price now", "value": "yahoo price now"},
                  {"text": "aapl on 10 nov 2015", "value": "aapl on 10 nov 2015"}])

    sm.send_text("You can buy or sell shares",
                 [{"text": "buy 2 goog", "value": "buy 2 goog"},
                  {"text": "sell apple", "value": "sell apple"}])

    sm.send_text("You can check your portfolio, or plot the portfolio performance",
                 [{"text": "portfolio", "value": "portfolio"},
                  {"text": "portfolio plot", "value": "portfolio plot"}])

    sm.send_text("You can find out how you are performing compared to others, and see who's doing well",
                 [{"text": "how am i doing?", "value": "how am i doing?"}])

    sm.send_text("You can update your notification preferences",
                 actions=[{"text": "notification preferences", "value": "notification preferences"}])

    sm.send_text("You can always give feedback. Whether it is feature request, any bugs you encounter, "
                 "and in general if you have any comments. We would love to hear from you!",
                 [{"text": "feedback", "value": "feedback"}])


@shared_task
def feedback(talk_user_id, msg):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    # if user_id is None:
    #     username = '#{}@{}'.format(slack_channel, auth.team_name)
    #     reply_to = 'noreply@talkai.xyz'
    # else:
    # user = User.objects.get(pk=user_id)
    username = "{}@{}".format(talk_user.natural_identifier, talk_user.slack_auth.team_name)
    reply_to = talk_user.email

    mail = EmailMultiAlternatives(
        subject="Feedback from {}".format(username),
        from_email="TalkAI Feedback <feedback@talkai.xyz>",
        to=settings.ADMIN_EMAILS,
        reply_to=[reply_to],
        body=msg
    )
    mail.send()
    SlackMessage(talk_user.slack_auth.bot_access_token, talk_user.slack_id).send_text(
        "We have received your feedback! Thank you :)")


@shared_task
def portfolio_plot(talk_user_id):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    slack_auth = talk_user.slack_auth
    sm = SlackMessage(slack_auth.bot_access_token, talk_user.slack_id)
    dates, values = last_week_values(talk_user)
    scatter = go.Scatter(x=dates, y=values)
    graph_url = plot_graph([scatter], 'Portfolio plot from {} to {}'.format(pretty_date(dates[0]),
                                                                            pretty_date(dates[-1])))
    sm.send_image(graph_url)


@shared_task
def porfolio_comparison(talk_user_id):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    slack_auth = talk_user.slack_auth
    sm = SlackMessage(slack_auth.bot_access_token, talk_user.slack_id)
    values = ranked_porfolios_team(slack_auth)
    best = values[0]
    sm.send_text("The top performer in your team is {}"
                 " with a portfolio value of ${:.2f}".format(best[0].natural_identifier, best[1]))
    my_rank = 0
    for i, (user, value) in enumerate(values):
        if user.pk == talk_user.pk:
            my_rank = i
            break
    sm.send_text("You are ranked {} with a portfolio value of ${:.2f}".format(my_rank + 1, values[my_rank][1]))
    if my_rank > 0:
        sm.send_text(
            "{} is just ahead of you, with a portfolio value of ${:.2f}".format(
                values[my_rank - 1][0].natural_identifier,
                values[my_rank - 1][1]))
    if my_rank < len(values) - 1:
        sm.send_text(
            "{} is just behind of you, with a portfolio value of ${:.2f}".format(
                values[my_rank + 1][0].natural_identifier,
                values[my_rank + 1][1]))


@shared_task
def notification_preferences(talk_user_id):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    slack_auth = talk_user.slack_auth
    sm = SlackMessage(slack_auth.bot_access_token, talk_user.slack_id)
    sm.send_text("Please choose how often you want to be notified. Your current setting"
                 " is '*{}*'".format(talk_user.get_notification_frequency_display()),
                 actions=[{"text": "daily", "value": "daily"}, {"text": "weekly", "value": "weekly"},
                          {"text": "never", "value": "never"}])


@shared_task
def notification_set(talk_user_id, notification_frequency):
    talk_user = TalkUser.objects.get(pk=talk_user_id)
    slack_auth = talk_user.slack_auth
    talk_user.notification_frequency = notification_frequency
    talk_user.save()
    sm = SlackMessage(slack_auth.bot_access_token, talk_user.slack_id)
    sm.send_text("Your notification preferences have been updated to"
                 " '{}'".format(talk_user.get_notification_frequency_display()))


@shared_task
def retrieve_channel_users(slack_auth_id):
    slack_auth = SlackAuth.objects.get(pk=slack_auth_id)
    sc = SlackClient(slack_auth.bot_access_token)
    channels = sc.api_call("channels.list")
    for channel in channels["channels"]:
        if channel["is_general"]:
            slack_auth.general_channel_id = channel['id']
            slack_auth.save()
            break
    users = sc.api_call("users.list")
    for user in users["members"]:
        if user["is_bot"] or user["id"] == "USLACKBOT":
            continue
        if not TalkUser.objects.filter(slack_id=user["id"], slack_auth=slack_auth).exists():
            talk_user = TalkUser.objects.create(email=user["profile"]["email"],
                                                name=user["profile"]["real_name"],
                                                slack_id=user["id"],
                                                slack_auth=slack_auth)
            # sm = SlackMessage(slack_auth.bot_access_token, talk_user.slack_id)
            # sm.send_text("Hi, my name is TickerBot. I am a conversational game on slack. You compete with your team"
            #              " for the best portfolio! To learn how to play, just ask :)",
            #              actions=[{"text": "how to play", "value": "how to play"}])
            # sc = SlackClient(slack_auth.access_token)
            # result = sc.api_call("channels.join", name=slack_auth.general_channel_id)


@shared_task
def send_performance_update(slack_auth_id):
    slack_auth = SlackAuth.objects.get(pk=slack_auth_id)
    values = ranked_porfolios_team(slack_auth)
    scatters = []
    messages = []
    user_1, value_1 = values[0]
    dates, values_1 = last_week_values(user_1)
    dates.append(date.today())
    values_1.append(value_1)
    scatters.append(go.Scatter(x=dates, y=values_1, name=user_1.natural_identifier))
    messages.append("{} is leading with a portfolio value of ${:.2f}".format(user_1.natural_identifier, value_1))
    if len(values) > 1:
        user_2, value_2 = values[1]
        _, values_2 = last_week_values(user_2)
        values_2.append(value_2)
        scatters.append(go.Scatter(x=dates, y=values_2, name=user_2.natural_identifier))
        messages.append(
            "Just behind is {}, with a portfolio value of ${:.2f}".format(user_2.natural_identifier, value_2))
    if len(values) > 2:
        user_3, value_3 = values[2]
        _, values_3 = last_week_values(user_3)
        values_3.append(value_3)
        scatters.append(go.Scatter(x=dates, y=values_3, name=user_3.natural_identifier))
        messages.append(
            "{} is ranked 3rd, with a portfolio value of ${:.2f}".format(user_3.natural_identifier, value_3))
    graph_url = plot_graph(scatters, 'Portfolio plot from {} to {}'.format(pretty_date(dates[0]),
                                                                           pretty_date(dates[-1])))
    sm = SlackMessage(slack_auth.bot_access_token, slack_auth.general_channel_id)
    res = sm.send_image(graph_url)
    if json.loads(res.content)["ok"]:
        for message in messages:
            sm.send_text(message)
        return
    for user in slack_auth.talkuser_set.all():
        if user.notification_frequency == NOTIFY_OFF:
            continue
        if user.notification_frequency == NOTIFY_WEEKLY:
            today = date.today()
            if today.weekday() != 4:
                continue
        sm = SlackMessage(slack_auth.bot_access_token, user.slack_id)
        sm.send_image(graph_url, actions=[{"text": "notification preferences",
                                           "value": "notification preferences"}])
        for message in messages:
            sm.send_text(message)


@shared_task
def update_user_list():
    for slack_auth in SlackAuth.objects.all():
        retrieve_channel_users(slack_auth.pk)


@shared_task
def send_performance_updates():
    group(send_performance_update.signature((slack_auth.pk, ), countdown=randint(0, 7200))
          for slack_auth in SlackAuth.objects.all()).apply_async()


def last_week_values(talk_user):
    values = []
    dates = []
    last_week = date.today() - relativedelta(days=7)
    for i in xrange(7):
        on = last_week + relativedelta(days=i)
        dates.append(on)
        values.append(talk_user.value_on(on))
    return dates, values


def ranked_porfolios_team(slack_auth):
    values = []
    for user in slack_auth.talkuser_set.all():
        values.append((user, user.value))
    values.sort(key=lambda x: x[1], reverse=True)
    return values


def get_stock_scatter_trace(data, name):
    x, y = [], []
    for row in data:
        x.append(row["date"])
        y.append(float(row["value"]))
    return go.Scatter(x=x, y=y, name=name)


def plot_graph(traces, title):
    py.sign_in(settings.PLOTLY_USERNAME, settings.PLOTLY_PASSWORD)
    filename = str(uuid.uuid4()) + ".png"
    layout = go.Layout(title=title, width=800, height=640)
    fig = go.Figure(data=traces, layout=layout)
    # plot_file = offline.plot(fig, show_link=False, auto_open=False,
    #                          filename=settings.MEDIA_ROOT + filename,
    #                          include_plotlyjs=True)
    # ghost = Ghost()
    # page, resources = ghost.open(plot_file)
    plot_url = py.plot(fig, filename=filename, auto_open=False, file_opt='new')
    return plot_url + ".png"
    # return "http://8d30bf7d.ngrok.io/media/" + filename + ".html"


def split_date_period(date_period_str):
    today = date.today()
    if not date_period_str:
        start_date = today - relativedelta(days=7)
        end_date = today
    else:
        start_date, end_date = map(parse_date, date_period_str.split('/'))
        if start_date.year > today.year:
            start_date = date(today.year, start_date.month, start_date.day)
        if end_date.year > today.year:
            end_date = date(today.year, end_date.month, end_date.day)
        if end_date > today:
            end_date = today
    return start_date, end_date
