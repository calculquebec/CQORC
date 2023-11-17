import eventbrite as eb
from requests.models import PreparedRequest
import os
import itertools
import configparser
import logging
from datetime import datetime, timezone


class EventbriteInterface(eb.Eventbrite):
    """
    Extend Eventbrite class.
    """
    EVENT_TIME_FILTERS = ("past", "current_future", "all")
    EVENT_STATUSES = ("draft", "live", "started", "ended", "canceled", "all")
    UTC_FMT = '%Y-%m-%dT%H:%M:%SZ'
    ISO_8061_FORMAT = "YYYY-MM-DD[THH:MM:SS[±HH:MM]]"

    def __init__(self, token):
        super(EventbriteInterface, self).__init__(token)
        self.logger = logging.getLogger(__name__)

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
            req.prepare_url(prefix + url, params)
            url = req.url[len(prefix):]

        results = self.get(url)
        yield results[key]

        while bool(results.pagination['has_more_items']):
            results = self.get(url, data={'continuation': results['pagination']['continuation']})
            yield results[key]

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

    def _raise_or_ok(self, response):
        """
        Raise exception if response is not OK
        """
        if response.ok:
            return response
        else:
            raise Exception(response)

    def _to_iso8061(self, dt, tz=None):
        """
        Returns full long ISO 8061 datetime with timezone.

        eg:
            '2018-09-12' -> '2018-09-12T00:00:00-04:00'
            '2018-09-12T00:00:00+00:30' -> '2018-09-11T19:30:00-04:00'
        """
        if isinstance(dt, datetime):
            return dt.astimezone(tz)
        else:
            return datetime.fromisoformat(dt).astimezone(tz)

    def create_event_from(self, event_id, title, start_date, end_date, tz, summary="[[SUMMARY]]"):
        """
        Copy and create an event from the event id.

        Parameters
        ----------
            event_id:   The template event id to copy from
            title:      Event title
            start_date: Event start date (iso8061)
            end_date:   Event end date (iso8061)
            tz:         Event timezone
            summary:    Event summary, default to [[SUMMARY]] to be updated later

        Returns
        -------
        event_id: Newly created event id

        Examples
        --------
        >>> create_event_from(config[templates]['fr_event_id'], 'my title', '2023-12-01T09:00:00', '2023-12-01T12:00:00', 'America/Toronto')
        9882121212121

        """
        start_date = self._to_iso8061(start_date)
        end_date = self._to_iso8061(end_date)

        # Eventbrite requires the dates in UTC
        obj = {
            "name": title,
            "start_date": start_date.astimezone(timezone.utc).strftime(self.UTC_FMT),
            "end_date": end_date.astimezone(timezone.utc).strftime(self.UTC_FMT),
            'timezone': tz,
            "summary": summary,
        }

        # Create the event
        response = self.post(f"/events/{event_id}/copy/", data=obj)
        if response.ok:
            self.logger.debug(f"Created event {response['id']}")
            print(f'Successfully created {response["name"]["text"]} {response["start"]["local"]} {response["end"]["local"]}')
        else:
            self.logger.error(f'Error creating event! Got {response}')
            raise Exception(response)

        return response["id"]

    def update_tickets(self, event_id, sales_start=None, sales_end=None):
        """
        Update tickets class.

        Parameters
        ----------
        event_id:    Event id to update
        sales_start: Sales start date time, default None -> unchange
        sales_end:   Sales end date time, default None -> end at event start time

        Returns
        -------
        None
        """
        event = eb.get_event(event_id)
        sales_start = self._to_iso8061(sales_start).astimezone(timezone.utc).strftime(self.UTC_FMT) if sales_start else ""
        sales_end = self._to_iso8061(sales_end if sales_end else event['start']['local']).astimezone(timezone.utc).strftime(self.UTC_FMT)
        ticket_classes_response = self._raise_or_ok(self.get(f"/events/{event_id}/ticket_classes/"))

        for ticket_class in ticket_classes_response['ticket_classes']:
            obj = {
                "ticket_class": {
                    "sales_start": sales_start,
                    "sales_end": sales_end
                }
            }
            self._raise_or_ok(self.post(f"/events/{event_id}/ticket_classes/{ticket_class['id']}/", data=obj))

        print(f'Successfully updated {event_id} ticket classes')

    def get_event_description(self, event_id):
        """
        Get the template event description section.
        Calls specific html endpoint, this contains the summary and the description in html.

        Parameters
        ----------
        event_id: template id

        Returns
        -------
        HTML object representing the description
        """
        return self._raise_or_ok(self.get(f'/events/{event_id}/description/'))

    def delete_event(self, event_id):
        """
        Delete an event.

        Parameters
        ----------
        event_id: Event id to delete

        Returns
        -------
        Json object containing deleted true or false
        """
        return self._raise_or_ok(super(EventbriteInterface, self).delete(f'/events/{event_id}'))

    def get_event_attendees(self, event_id):
        """
        Get the attendees for this event, in one list.
        *Override eventbrite.get_event_attendees which is paginated.*

        Parameters
        ----------
        event_id: Event id

        Returns
        -------
        attendees
        """
        return self.get_unpaginated(f"/events/{event_id}/attendees/", key='attendees')

    def update_event_description(self, event_id, description):
        """
        Update the event description.
        This does not contain the summary, only the description in html.

        Parameters
        ----------
        event_id: Event id to update
        description: Event HTML description

        Returns
        -------
        None
        """
        obj = {
            "modules": [{
                "type": "text", "data": {"body": {"text": description, }}}
            ],
            "publish": "true",
            "purpose": "listing"
        }

        get_structed_content = self._raise_or_ok(self.get(f"/events/{event_id}/structured_content/"))
        version = int(get_structed_content["page_version_number"])

        return self._raise_or_ok(self.post(f"/events/{event_id}/structured_content/{version+1}/", data=obj))

    def get_event_attendees_by_status(self, event_id, status_filter=None, fields = None):
        """
        Get attendees information for the event.
        By default, returns information for all attendees regardless of their status.

        Parameters
        ----------
        event_id: Event id
        status_filter: status to filter, default : None
        fields: name of the fields to keep in the information returned

        Returns
        -------
        attendees: a dictionary mapping email addresses the attendee information
        """
        attendees = self.get_event_attendees(event_id)

        if status_filter:
            lambda_filter = lambda x: x['status'].lower() in status_filter
            attendees = filter(lambda_filter, attendees)

        # transform into a dictionary
        attendees = {attendee['profile']['email']: attendee for attendee in attendees}

        # keep only fields requested
        if fields:
            filtered_view = {}
            for email, info in attendees.items():
                filtered_info = {}
                for field in fields:
                    # check if the field is in the root level
                    if field in info:
                        filtered_info[field] = info[field]
                    # flatten if it is part of a sub dictionary
                    else:
                        for subdict in info.keys():
                            if isinstance(info[subdict], dict) and field in info[subdict]:
                                filtered_info[field] = info[subdict][field]
                filtered_view[email] = filtered_info
            attendees = filtered_view

        return attendees


    def get_event_attendees_registered(self, event_id, fields = None):
        """
        Get information for attendees that are attending, that is that have their status to `attending`.
        Discard refunded, cancelled or transferred attendees.

        Parameters
        ----------
        event_id: Event id

        Returns
        -------
        attendees: a dictionary mapping email addresses the attendee information
        """
        return self.get_event_attendees_by_status(event_id, status_filter=('attending'))


    def get_event_attendees_present(self, event_id):
        """
        Get information for attendees that participated, that is that have their status to `checked in` or `attended`.

        Parameters
        ----------
        event_id: Event id

        Returns
        -------
        attendees: a dictionary mapping email addresses the attendee information
        """
        return self.get_event_attendees_by_status(event_id, status_filter=('checked in', 'attended'))

if __name__ == '__main__':
    from glob import glob

    config = configparser.ConfigParser()
    config.read(
        glob(os.path.join(os.environ.get('CQORC_CONFIG_DIR', '.'), '*.cfg')) +
        glob(os.path.join(os.environ.get('CQORC_SECRET_DIR', '.'), '*.cfg'))
    )

    eb = EventbriteInterface(config['eventbrite']['api_key'])
    lang = 'fr'

    # Test get template event
    fr_template = eb.get_event(config['eventbrite.templates'][f'{lang}_event_id'])

    print(fr_template['name'])
    print('OK')
