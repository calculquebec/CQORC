#!/usr/bin/env python3
import datetime
import logging
import os
import pytz

try:
    from interfaces.google.GoogleInterface import GoogleInterface
except:
    from GoogleInterface import GoogleInterface
from googleapiclient.errors import HttpError

class GCalInterface(GoogleInterface):
    def __init__(self, key_file, calendar_id, timezone = "America/Montreal", credentials_type='user'):
        super(GCalInterface, self).__init__(key_file, credentials_type, 'calendar', 'v3', ['https://www.googleapis.com/auth/calendar.events'])
        self.logger = logging.getLogger(__name__)
        self.calendar_id = calendar_id
        self.timezone = timezone
        self.tzinfo = pytz.timezone(self.timezone)


    def get_event(self, event_id):
        try:
            event = self.get_service().events().get(calendarId=self.calendar_id, eventId=event_id).execute()
            return event

        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


    def get_events(self, start_time, limit=10, end_time=None):
        try:
            if end_time:
                events_result = self.get_service().events().list(calendarId=self.calendar_id, timeMin=start_time,
                                              timeMax=end_time,
                                              maxResults=limit, singleEvents=True,
                                              orderBy='startTime').execute()
            else:
                events_result = self.get_service().events().list(calendarId=self.calendar_id, timeMin=start_time,
                                              maxResults=limit, singleEvents=True,
                                              orderBy='startTime').execute()
            events = events_result.get('items', [])
            return events

        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


    def get_events_by_date(self, date, limit=10):
        try:
            # get the start of day
            start_time = date.replace(hour=0, minute=0, second=0)
            end_time = date.replace(hour=23, minute=59, second=59)
            if start_time.tzinfo is None:
                start_time = self.tzinfo.localize(start_time).astimezone(pytz.utc)
                end_time = self.tzinfo.localize(end_time).astimezone(pytz.utc)
            start_time = start_time.isoformat()
            end_time = end_time.isoformat()
            events = self.get_events(start_time, limit=limit, end_time=end_time)
            return events

        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


    def create_event(self, start_time, end_time, summary, description, attendees, send_updates="all"):
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
            event_dict['transparency'] = 'opaque'
            if isinstance(attendees, str):
                attendees = [{'email': x.strip()} for x in attendees.split(',')]
            if isinstance(attendees, list) and isinstance(attendees[0], str):
                attendees = [{'email': x} for x in attendees]
            event_dict['attendees'] = attendees

            event = self.get_service().events().insert(
                        calendarId=self.calendar_id,
                        body=event_dict,
                        sendUpdates=send_updates
                        ).execute()
            self.logger.info("Event created: %s" % (event.get('htmlLink')))
            return event
        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


    def update_event(self, event_id, start_time=None, end_time=None, summary=None, description=None, attendees=None, send_updates="all"):
        # update an event
        # documentation: https://developers.google.com/calendar/api/v3/reference/events/update
        try:
            # reference for fields of an event
            # https://developers.google.com/calendar/api/v3/reference/events#resource
            event = self.get_event(event_id)
            if start_time: event['start'] = {'dateTime': start_time, 'timeZone': self.timezone}
            if end_time: event['end'] = {'dateTime': end_time, 'timeZone': self.timezone}
            if summary: event['summary'] = summary
            if description: event['description'] = description
            event['transparency'] = 'opaque'

            if isinstance(attendees, str):
                attendees = [{'email': x.strip()} for x in attendees.split(',')]
            if isinstance(attendees, list) and isinstance(attendees[0], str):
                attendees = [{'email': x} for x in attendees]
            if attendees: event['attendees'] = attendees

            event = self.get_service().events().update(
                        calendarId=self.calendar_id,
                        eventId=event_id,
                        body=event,
                        sendUpdates=send_updates
                        ).execute()
            self.logger.info("Event updated: %s" % (event.get('htmlLink')))
            return event
        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


    def add_attendees(self, event_id, attendees):
        # update an event
        # documentation: https://developers.google.com/calendar/api/v3/reference/events/update
        event = self.get_event(event_id)
        if isinstance(attendees, str):
            attendees = [{'email': x.strip()} for x in attendees.split(',')]
        attendees += event['attendees']
        return self.update_event(event_id, attendees = attendees)


    def delete_event(self, event_id, send_updates="all"):
        # delete an event
        # documentation: https://developers.google.com/calendar/api/v3/reference/events/delete
        try:
            event = self.get_service().events().delete(
                        calendarId=self.calendar_id,
                        eventId=event_id,
                        sendUpdates=send_updates,
                        ).execute()
            self.logger.info(f"Event deleted: {event_id}")
        except HttpError as error:
            self.logger.error('An error occurred: %s' % error)


def main():
    import configparser
    import os
    import glob
    import time
    config = configparser.ConfigParser()
    config_dir = os.environ.get('CQORC_CONFIG_DIR', '.')
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', '.')
    config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
    print("Reading config files: %s" % str(config_files))
    config.read(config_files)

    # take the credentials file either from google.calendar or from google section
    credentials_file = config['google']['credentials_file']
    credentials_file_path = os.path.join(secrets_dir, credentials_file)

    timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
    gcal = GCalInterface(credentials_file_path, config['google.calendar']['calendar_id'], timezone)

    # Call the Calendar API
    now_dt = datetime.datetime.utcnow()
    event = gcal.create_event(now_dt.isoformat() + 'Z', (now_dt + datetime.timedelta(hours=3)).isoformat() + 'Z', "ceci est un test", "ceci est une description", "maxime.boissonneault@calculquebec.ca")
    print(str(event))

    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events = gcal.get_events(now, 20)
    events = gcal.get_events_by_date(datetime.datetime.today())
    print(str(events))
    time.sleep(30)
    event = gcal.update_event(event['id'], start_time=((datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat()+"Z"),
                                    end_time=((datetime.datetime.utcnow() + datetime.timedelta(hours=2)).isoformat()+"Z"),
                                    summary="un nouveau résumé2",
                                    description="une nouvelle description",
                                    attendees="charles.coulombe@calculquebec.ca")
    print(str(event))
    time.sleep(30)
    event = gcal.add_attendees(event['id'], "maxime.boissonneault@calculquebec.ca")
    print(str(event))

    time.sleep(30)
    gcal.delete_event(event['id'])
    print(str(events))
#    events = gcal.get_events(now, 20)
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

