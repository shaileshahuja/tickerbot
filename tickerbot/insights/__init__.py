import requests
import logging
from django.http.response import JsonResponse

logger = logging.getLogger(__name__)


class SlackMessage(object):
    def __init__(self, token, channel):
        self.post_url = "https://slack.com/api/chat.postMessage"
        self.token = token
        self.channel = channel

    def send_image(self, image_url, actions=None):
        attachments = '[{"fallback": "image", "image_url":"' + image_url + '", "callback_id": "' + self.channel + \
                      '", "actions": ' + self.format_actions(actions) + '}]'
        return self.send_to_slack(attachments)

    def send_text(self, text, actions=None):
        attachments = '[{"fallback": "New message", "color": "#3AA3E3", "text":"' + text + '","mrkdwn_in": ["text"],' \
                                                                                           ' "callback_id": "' + self.channel + '", "actions": ' + self.format_actions(
            actions) + '}]'
        return self.send_to_slack(attachments)

    @staticmethod
    def format_actions(actions=None):
        action_list = []
        if actions is not None:
            for action in actions:
                action_list.append({
                    "name": action["value"],
                    "text": action["text"],
                    "type": "button",
                    "value": action["value"]
                })
        return str(action_list)

    def send_to_slack(self, attachments):
        slack_params = {"attachments": attachments, "token": self.token, "channel": self.channel, "as_user": True}
        logger.info(slack_params)
        response = requests.get(self.post_url, params=slack_params)
        logger.info(str(response.status_code) + ": " + response.content)
        return response


class APIAI(object):
    @classmethod
    def get_context_params(cls, query, context_name):
        for context in query["result"]["contexts"]:
            if context["name"] == context_name:
                return context["parameters"]
        return None

    @classmethod
    def prepare_response(cls, text, context=None):
        data = {
            "speech": text,
            "displayText": text,
            "data": {"slack": {"text": text}},
            "source": "finbot_app"
        }
        if context is not None:
            data["contextOut"] = context
        return JsonResponse(data)

    @classmethod
    def prepare_context(cls, name, params, lifespan=5):
        return {
            "name": name,
            "lifespan": lifespan,
            "parameters": params
        }
