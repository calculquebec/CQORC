#!/usr/bin/env python3
import datetime
import logging

from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GCalInterface:
    def __init__(self, service_account_key_file, calendar_id):
        self.key_file = service_account_key_file
        self.calendar_id = calendar_id
        self.logger = logging.getLogger(__name__)
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        self.credentials = None
        self.service = None

    def get_credentials(self):
        """Creates a Credential object with the correct OAuth2 authorization.
        Uses the service account key stored in self.key_file
        Returns:
            Credentials, the user's credential.
        """
        if not self.credentials:
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.key_file, self.scopes)

            if not creds or creds.invalid:
                print('Unable to authenticate using service account key.')
                sys.exit()
            else:
                self.credentials = creds

        return self.credentials

    def get_service(self):
        if not self.service:
            try:
                service = build('calendar', 'v3', credentials=self.get_credentials())
                self.service = service
            except HttpError as error:
                print('An error occurred: %s' % error)

        return self.service

    def get_events(self, start_time, limit=10):
        try:
            events_result = self.get_service().events().list(calendarId=self.calendar_id, timeMin=start_time,
                                              maxResults=limit, singleEvents=True,
                                              orderBy='startTime').execute()
            events = events_result.get('items', [])
            return events

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
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events = gcal.get_events(now, 20)
    if not events:
        print('No upcoming events found.')
        return

    # Prints the start and name of the next 10 events
    for event in events:
        #        print(str(event))
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event['summary'], event.get('description', ''))

if __name__ == "__main__":
    main()

# Refer to the Python quickstart on how to setup the environment:
# https://developers.google.com/calendar/quickstart/python
# Change the scope to 'https://www.googleapis.com/auth/calendar' and delete any
# stored credentials.

event = {
  'summary': 'Google I/O 2015',
  'location': '800 Howard St., San Francisco, CA 94103',
  'description': 'A chance to hear more about Google\'s developer products.',
  'start': {
    'dateTime': '2015-05-28T09:00:00-07:00',
    'timeZone': 'America/Los_Angeles',
  },
  'end': {
    'dateTime': '2015-05-28T17:00:00-07:00',
    'timeZone': 'America/Los_Angeles',
  },
  'recurrence': [
    'RRULE:FREQ=DAILY;COUNT=2'
  ],
  'attendees': [
    {'email': 'lpage@example.com'},
    {'email': 'sbrin@example.com'},
  ],
  'reminders': {
    'useDefault': False,
    'overrides': [
      {'method': 'email', 'minutes': 24 * 60},
      {'method': 'popup', 'minutes': 10},
    ],
  },
}
