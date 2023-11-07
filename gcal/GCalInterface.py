#!/usr/bin/env python3
import datetime
import logging
import os

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from oauth2client.service_account import ServiceAccountCredentials

class GCalInterface:
    def __init__(self, service_account_key_file, calendar_id, credential_type='user'):
        self.key_file = service_account_key_file
        self.calendar_id = calendar_id
        self.logger = logging.getLogger(__name__)
        self.scopes = ['https://www.googleapis.com/auth/calendar.events']
        self.credentials = None
        self.service = None
        self.timezone = "America/Montreal"
        self.credential_type = credential_type


    def get_credentials(self):
        if self.credential_type == "user":
            return self.get_user_credentials()
        elif self.credential_type == "service":
            return self.get_service()


    def get_user_credentials(self):
        if not self.credentials or not self.credentials.valid:
            # The file token.json stores the user's access and refresh tokens, and is
            # created automatically when the authorization flow completes for the first
            # time.
            if os.path.exists("token.json"):
                self.credentials = Credentials.from_authorized_user_file("token.json", self.scopes)
            # If there are no (valid) credentials available, let the user log in.
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                            self.key_file, self.scopes
                            )
                    self.credentials = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open("token.json", "w") as token:
                    token.write(self.credentials.to_json())

        return self.credentials


    def get_service_credentials(self):
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

