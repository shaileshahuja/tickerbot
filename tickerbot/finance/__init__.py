from datetime import date, datetime
import traceback
import quandl
from dateutils import relativedelta
from quandl.errors.quandl_error import QuandlError
from yahoo_finance import Share, YQLResponseMalformedError, YQLQueryError
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    pass


def timeout_call(func, *args, **kwargs):
    import signal
    timeout_duration = kwargs.get('timeout_duration', 5)

    def handler(signum, frame):
        raise TimeoutError('Function call timed out!')

    # set the timeout handler
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout_duration)
    try:
        result = func(*args)
    finally:
        signal.alarm(0)
    return result


class PriceAPI(object):
    @staticmethod
    def get_current_value(ticker):
        try:
            share = Share(ticker)
            return float(timeout_call(share.get_price))
        except Exception:
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def get_value_on(cls, ticker, on):
        buffer_date = on - relativedelta(days=5)
        return float(cls.get_historical(ticker, buffer_date, on)[-1]['value'])

    @staticmethod
    def get_historical(ticker, start_date, end_date):
        from finance.models import QuandlTickerDatabaseMap
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        try:
            quandl_map = QuandlTickerDatabaseMap.objects.get(ticker=ticker)
            quandl.ApiConfig.api_key = settings.QUANDL_API_KEY
            data_code = quandl_map.database + "/" + ticker + "." + str(quandl_map.closing_column)
            data = quandl.get(data_code, start_date=start_date_str, end_date=end_date_str, returns='numpy', order='asc')
            return [{"date": row['Date'].date(), "value": row['Adj. Close']} for row in data]
        except (QuandlTickerDatabaseMap.DoesNotExist, QuandlError):
            logger.debug("Getting data for {} from yahoo".format(ticker))
            share = Share(ticker)
            try:
                data = timeout_call(share.get_historical, *[start_date_str, end_date_str])
                return [{"date": datetime.strptime(row['Date'], '%Y-%m-%d').date(), "value": row['Adj_Close']}
                        for row in sorted(data)]
            except (YQLQueryError, YQLResponseMalformedError):
                logger.error(traceback.format_exc())
                return [{"date": date.today(), "value": share.get_price()}]
            except Exception:
                logger.error(traceback.format_exc())
                return None
