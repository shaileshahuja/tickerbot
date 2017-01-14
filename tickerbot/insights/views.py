import abc
import json
import logging
import re
import traceback

from django.conf import settings
from django.http.response import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.views.generic.base import View, TemplateView
from rest_framework.exceptions import AuthenticationFailed
from slackclient import SlackClient
from insights import APIAI
from insights.models import SlackAuth, TalkUser
from insights.tasks import plot_ticker, price_ticker, compare_tickers, ticker_insights, selling_price, \
    purchase_shares, portfolio, buying_price, sell_shares, help, feedback, retrieve_channel_users, \
    porfolio_comparison, portfolio_plot, notification_preferences, notification_set

logger = logging.getLogger(__name__)


def get_slack_oauth_uri(request):
    # scope = "bot+channels:write"
    scope = "bot"
    return "https://slack.com/oauth/authorize?scope=" + scope + "&client_id=" + settings.SLACK_CLIENT_ID + \
           "&redirect_uri=" + request.build_absolute_uri(reverse("oauth"))


def authorize(target_username, target_password):
    def wrapper(func):
        def decorator(obj, request, *args, **kwargs):
            if 'HTTP_AUTHORIZATION' in request.META:
                authmeth, auth = request.META['HTTP_AUTHORIZATION'].split(' ', 1)
                if authmeth.lower() == 'basic':
                    auth = auth.strip().decode('base64')
                    username, password = auth.split(':', 1)
                    if username == target_username and password == target_password:
                        return func(obj, request, *args, **kwargs)
            raise AuthenticationFailed()

        return decorator

    return wrapper


class SlackOAuthSuccessView(TemplateView):
    template_name = "success.html"


class SlackOAuthFailureView(TemplateView):
    template_name = "failure.html"


class SlackOAuthView(View):
    def dispatch(self, request, *args, **kwargs):
        try:
            code = request.GET.get('code', '')
            sc = SlackClient("")
            result = sc.api_call("oauth.access", client_id=settings.SLACK_CLIENT_ID,
                                 client_secret=settings.SLACK_CLIENT_SECRET, code=code,
                                 redirect_uri=request.build_absolute_uri(reverse('oauth')))
            if SlackAuth.objects.filter(team_id=result["team_id"]).exists():
                SlackAuth.objects.get(team_id=result["team_id"]).delete()
            slack_auth = SlackAuth.objects.create(access_token=result["access_token"], team_id=result["team_id"],
                                                  team_name=result["team_name"], bot_id=result["bot"]["bot_user_id"],
                                                  bot_access_token=result["bot"]["bot_access_token"])
            retrieve_channel_users.delay(slack_auth.pk)
            return HttpResponseRedirect(reverse("success"))
        except Exception:
            logger.error(traceback.format_exc())
            return HttpResponseRedirect(reverse("failure"))


class SlackActionView(View):
    def dispatch(self, request, *args, **kwargs):
        try:
            query = request.POST
            logger.debug(str(query))
        except Exception:
            logger.error(traceback.format_exc())
        return HttpResponse(status=200)


class YahooFinanceAgentView(View):
    @authorize(target_username="apiai", target_password="dsf^Ah#aKfdJfah$")
    def dispatch(self, request, *args, **kwargs):
        try:
            query = json.loads(request.body)
            logger.debug(str(query))
        except Exception:
            logger.error(traceback.format_exc())
            return
        if query["originalRequest"] and query["originalRequest"]["source"] == 'slack':
            if "team" in query["originalRequest"]["data"]:
                slack_team = query["originalRequest"]["data"]["team"]
                slack_channel = query["originalRequest"]["data"]["user"]
                try:
                    slack_auth = SlackAuth.objects.get(team_id=slack_team)
                except SlackAuth.DoesNotExist:
                    return APIAI.prepare_response("Please authorize: {}".format(get_slack_oauth_uri(request)))
            else:
                slack_channel = query["originalRequest"]["data"]["attachments"][0]["callback_id"]
                bot_id = query["originalRequest"]["data"]["user"]
                try:
                    slack_auth = SlackAuth.objects.get(bot_id=bot_id)
                except SlackAuth.DoesNotExist:
                    return APIAI.prepare_response("Please authorize: {}".format(get_slack_oauth_uri(request)))
            try:
                talk_user = TalkUser.objects.get(slack_auth=slack_auth, slack_id=slack_channel)
            except TalkUser.DoesNotExist:
                sc = SlackClient(slack_auth.bot_access_token)
                result = sc.api_call("users.info", user=slack_channel)
                talk_user = TalkUser.objects.create(slack_auth=slack_auth, slack_id=slack_channel,
                                                    name=result["user"]["profile"]["real_name"],
                                                    email=result["user"]["profile"]["email"])
        else:
            talk_user = TalkUser.objects.get_or_create(email="default@talkai.xyz")[0]
        try:
            action = query["result"]["action"]
            parts = re.split('\W+|_', action)
            class_name = ''.join([part[0].upper() + part[1:] for part in parts]) + "Query"
            class_object = globals()[class_name]
            action_instance = class_object(talk_user, query)
            return action_instance.execute()
        except Exception as e:
            logger.error(traceback.format_exc())
            return self.error(e.message)

    @staticmethod
    def error(message):
        text = "There was an error processing your request by the server. " + str(message)
        return APIAI.prepare_response(text)


class APIAIQueryBase(object):
    __metaclass__ = abc.ABCMeta

    DEFAULT_RESPONSE = "Processing..."

    def __init__(self, talk_user, query):
        self.talk_user = talk_user
        self.query = query

    @property
    def async_call_definition(self):
        """
        :return: function reference, list of query params to pass, and dict (context_name->list of context params)
         of context params to pass in
        """
        return None

    @property
    def response_text(self):
        return self.DEFAULT_RESPONSE

    @property
    def make_async_call(self):
        return True

    def async_call(self):
        async_call_definition = self.async_call_definition
        if async_call_definition is None:
            return
        function, param_fields, context_dict = async_call_definition
        if param_fields:
            params = self.query["result"]["parameters"]
            param_args = [params[param_field] for param_field in param_fields]
        else:
            param_args = []
        context_args = []
        if context_dict:
            for context_key, context_fields in context_dict.iteritems():
                context_params = APIAI.get_context_params(self.query, context_key)
                context_args += [context_params[context_field] for context_field in context_fields]
        function.delay(self.talk_user.pk, *param_args + context_args)

    def execute(self):
        if self.make_async_call:
            self.async_call()
        return APIAI.prepare_response(self.response_text)


class TickerPriceQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return price_ticker, ["ticker", "date"], {}


class TickerPlotQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return plot_ticker, ["ticker", "date-period"], {}


class TickerInsightsQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return ticker_insights, [], {'plot': ["ticker", "date-period"]}


class TickerCompareQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return compare_tickers, ["ticker_new"], {'plot': ["ticker", "date-period"]}


class PortfolioCashQuery(APIAIQueryBase):
    @property
    def response_text(self):
        return "You have ${:.2f} left in your account".format(self.talk_user.cash)


class PortfolioPlotQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return portfolio_plot, [], {}


class PortfolioValueQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return portfolio, [], {}


class PortfolioCompareQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return porfolio_comparison, [], {}


class PortfolioBuyQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return buying_price, ["ticker", "quantity"], {}


class PortfolioBuyConfirmQuery(APIAIQueryBase):
    @property
    def make_async_call(self):
        return self.query["result"]["parameters"]["confirm"] != 'no'

    @property
    def async_call_definition(self):
        return purchase_shares, [], {'buy': ["ticker", "quantity"]}

    @property
    def response_text(self):
        if self.make_async_call:
            return self.DEFAULT_RESPONSE
        return "Transaction cancelled!"


class PortfolioSellQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return selling_price, ["ticker", "quantity"], {}


class PortfolioSellConfirmQuery(APIAIQueryBase):
    @property
    def make_async_call(self):
        return self.query["result"]["parameters"]["confirm"] != 'no'

    @property
    def async_call_definition(self):
        return sell_shares, [], {'sell': ["ticker", "quantity"]}

    @property
    def response_text(self):
        if self.make_async_call:
            return self.DEFAULT_RESPONSE
        return "Transaction cancelled!"


class HelpQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return help, [], {}

    @property
    def response_text(self):
        return "This is what you can do here..."


class FeedbackSendQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return feedback, ["message"], {}


class SettingsNotificationOptionsQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return notification_preferences, [], {}


class SettingsNotificationChooseQuery(APIAIQueryBase):
    @property
    def async_call_definition(self):
        return notification_set, ["notification_type"], {}
