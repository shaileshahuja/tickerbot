"""tickerbot URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url
from django.contrib import admin

from insights.views import YahooFinanceAgentView, SlackOAuthView, SlackOAuthSuccessView, SlackOAuthFailureView, \
    SlackActionView

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^oauth', SlackOAuthView.as_view(), name='oauth'),
    url(r'^success', SlackOAuthSuccessView.as_view(), name='success'),
    url(r'^failure', SlackOAuthFailureView.as_view(), name='failure'),
    url(r'^action', SlackActionView.as_view(), name='action'),
    url(r'^18a86229-04f6-4daa-a8c5-713dbc93982b', YahooFinanceAgentView.as_view())
]
