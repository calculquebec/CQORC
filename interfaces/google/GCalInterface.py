#!/usr/bin/env python3
import datetime
import logging
import os

from GoogleInterface import GoogleInterface
from googleapiclient.errors import HttpError

class GCalInterface(GoogleInterface):
    def __init__(self, key_file, calendar_id, credentials_type='user', timezone = "America/Montreal"):
        super(GCalInterface, self).__init__(key_file, credentials_type, 'calendar', 'v3', ['https://www.googleapis.com/auth/calendar.events'])
        self.logger = logging.getLogger(__name__)
        self.calendar_id = calendar_id
        self.timezone = timezone

    def get_events(self, start_time, limit=10):
        try:
            events_result = self.get_service().events().list(calendarId=self.calendar_id, timeMin=start_time,
                                              maxResults=limit, singleEvents=True,
                                              orderBy='startTime').execute()
            events = events_result.get('items', [])
            return events

        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


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
            self.logger.info("Event created: %s" % (event.get('htmlLink')))
        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)



def main():
    import configparser
    import os
    import glob
    config = configparser.ConfigParser()
    config_dir = os.environ.get('CQORC_CONFIG_DIR', '.')
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', '.')
    config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
    print("Reading config files: %s" % str(config_files))
    config.read(config_files)

    # take the credentials file either from google.calendar or from google section
    credentials_file = config['google.calendar'].get('credentials_file', config['google']['credentials_file'])
    credentials_file_path = os.path.join(secrets_dir, credentials_file)

    timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
    gcal = GCalInterface(credentials_file_path, config['google.calendar']['calendar_id'], timezone)

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
