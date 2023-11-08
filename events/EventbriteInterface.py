import eventbrite as eb
from requests.models import PreparedRequest
import os
import itertools
import functools
import configparser


class EventbriteInterface(eb.Eventbrite):
    EVENT_TIME_FILTERS = ("past", "current_future", "all")
    EVENT_STATUSES = ("draft", "live", "started", "ended", "canceled", "all")
    UTC_FMT = '%Y-%m-%dT%H:%M:%SZ'
    ISO_8061_FORMAT = "YYYY-MM-DD[THH:MM:SS[±HH:MM]]"

    """
    Extend Eventbrite class.
    """
    @functools.lru_cache
    def get_pages(self, url, key, **params):
        """
        Get all pages returned.

        Parameters
        ----------
        url : str
            URL for GET request. Must begin with `/`.
        key : str
            Desired object key from JSON.
        """
        if params is not None:
            # fake a correctly constructed URL, to prepare request, then remove the prefix
            # to be compatible with Eventbrite API requests.
            prefix = "http:/"
            req = PreparedRequest()
            req.prepare_url(prefix+url, params)
            url = req.url[len(prefix):]

        results = self.get(url)
        yield results[key]

        while bool(results.pagination['has_more_items']):
            results = self.get(url, data={'continuation': results['pagination']['continuation']})
            yield results[key]

    @functools.lru_cache
    def get_unpaginated(self, url, key, **params):
        """
        Flatten all returned pages into one collection.

        Parameters
        ----------
        url : str
            URL for GET request. Must begin with `/`.
        key : str
            Desired object key from JSON.
        """
        return itertools.chain.from_iterable(self.get_pages(url, key, **params))

    @functools.lru_cache
    def get_events(self, organization_id, flattened=True, **params):
        """
        Get all events for an organization.

        Parameters
        ----------
        organization_id : int
            Number of the Organization Identifier in Eventbrite.

        flattened : bool, optional
            Returns a flattened array of all pages when `True`,
            otherwise returns an array of all pages content.

        params : dict
        """
        url = f"/organizations/{organization_id}/events"
        if flattened:
            return self.get_unpaginated(url, "events", **params)
        else:
            return self.get_pages(url, "events", **params)


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read([os.environ.get('EVENTBRITE_SECRETS', '../secrets.cfg'), 'eventbrite.cfg'])

    eb = EventbriteInterface(config['eventbrite']['api_key'])
    lang = 'fr'

    # Test get template event
    fr_template = eb.get_event(config['templates'][f'{lang}_event_id'])

    print(fr_template['name'])
    print('OK')
