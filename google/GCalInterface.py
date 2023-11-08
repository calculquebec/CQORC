#!/usr/bin/env python3
import datetime
import logging
import os

from GoogleInterface import GoogleInterface
from googleapiclient.errors import HttpError

class GCalInterface(GoogleInterface):
    def __init__(self, key_file, calendar_id, credentials_type='user'):
        super(GCalInterface, self).__init__(key_file, credentials_type, 'calendar', 'v3', ['https://www.googleapis.com/auth/calendar.events'])
        self.logger = logging.getLogger(__name__)
        self.calendar_id = calendar_id
        self.timezone = "America/Montreal"

    def get_events(self, start_time, limit=10):
        try:
            events_result = self.get_service().events().list(calendarId=self.calendar_id, timeMin=start_time,
                                              maxResults=limit, singleEvents=True,
                                              orderBy='startTime').execute()
            events = events_result.get('items', [])
            return events

        except HttpError as error:
            print('An error occurred: %s' % error)


    def create_event(self, start_time, end_time, summary, description, attendees):
        # create an event
        # documentation: https://developers.google.com/calendar/api/v3/reference/events/insert
        try:
            # reference for fields of an event
            # https://developers.google.com/calendar/api/v3/reference/events#resource
            event_dict = {}
            event_dict['start'] = {'dateTime': start_time, 'timeZone': self.timezone}
            event_dict['end'] = {'dateTime': end_time, 'timeZone': self.timezone}
            event_dict['summary'] = summary
            event_dict['description'] = description
            if isinstance(attendees, str):
                attendees = [{'email': x.strip()} for x in attendees.split(',')]
            event_dict['attendees'] = attendees

            event = self.get_service().events().insert(
                        calendarId=self.calendar_id,
                        body=event_dict
                        ).execute()
            print("Event created: %s" % (event.get('htmlLink')))
        except HttpError as error:
            print('An error occurred: %s' % error)



def main():
    import configparser
    import os
    secrets = configparser.ConfigParser()
    secrets_path = os.getenv('GCAL_SECRETS') or '../secrets.cfg'
    secrets.read_file(open(secrets_path))
    secrets = secrets['gcal']
    gcal = GCalInterface(secrets['credentials_file'], secrets['calendar_id'])

    # Call the Calendar API
    now_dt = datetime.datetime.utcnow()
#    gcal.create_event(now_dt.isoformat() + 'Z', (now_dt + datetime.timedelta(hours=3)).isoformat() + 'Z', "ceci est un test", "ceci est une description", "maxime.boissonneault@calculquebec.ca, charles.coulombe@calculquebec.ca")
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events = gcal.get_events(now, 20)
    if not events:
        print('No upcoming events found.')
        return

    # Prints the start and name of the next 10 events
    for event in events:
        #        print(str(event))
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event.get('summary', ''), event.get('description', ''))

if __name__ == "__main__":
    main()

