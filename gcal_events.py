#!/bin/env python3
import os, argparse, datetime

import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.google.GCalInterface as GCalInterface

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import get_events_from_sheet_calendar
from common import Trainers

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--all", default=False, action='store_true', help="Act for all events")
parser.add_argument("--create", default=False, action='store_true', help="Create events")
parser.add_argument("--update", default=False, action='store_true', help="Update events")
parser.add_argument("--delete", default=False, action='store_true', help="Delete events")
parser.add_argument("--no-notifications", default=False, action='store_true', help="Do not send update notifications to attendees")
parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
args = parser.parse_args()

# read configuration files
config = get_config(args)
trainers = Trainers(config['global']['trainers_db'])

secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
credentials_file = config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
gcal = GCalInterface.GCalInterface(credentials_file_path, config['google.calendar']['calendar_id'], timezone)
zoom_user = config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(config['zoom']['account_id'], config['zoom']['client_id'], config['zoom']['client_secret'], config['global']['timezone'], zoom_user)

# get the events from the working calendar in the Google spreadsheets
events = get_events_from_sheet_calendar(config, args)

# keep only events on the date listed
if args.date:
    events = [event for event in events if args.date.date().isoformat() in event['start_date']]

if args.no_notifications:
    send_updates = "none"
else:
    send_updates = "all"

for event in events:
    try:
        title = f"{event['code']} - {event['title']}"
        attendees_keys = []
        if event['instructor']: attendees_keys += [event['instructor']]
        if event['host']: attendees_keys += [event['host']]
        if event['assistants']: attendees_keys += event['assistants'].split(',')
        attendees = [trainers.calendar_email(key) for key in attendees_keys]

        start_time = to_iso8061(event['start_date'])
        end_time = to_iso8061(event['end_date'])
        duration = int(event['hours'])

        webinar = zoom.get_webinars(date = start_time.date())
        webinar = zoom.get_webinar(webinar_id = webinar[0]['id'])
        description = ''
        if webinar:
            description = f"""
Start URL: {webinar['start_url']}
Join URL: {webinar['join_url']}"""

        # events on two days
        two_day_events = False
        if start_time.date() != end_time.date():
            two_day_events = True
            duration = duration/2.

        original_start_time = start_time
        original_end_time = end_time

        for date in set([start_time.date(), end_time.date()]):
            if date == original_start_time.date():
                start_time = original_start_time
                end_time = original_start_time + datetime.timedelta(hours=duration)
            elif date == original_end_time.date():
                start_time = original_end_time - datetime.timedelta(hours=duration)
                end_time = original_end_time

            if args.create:
                if args.dry_run:
                    cmd = f"gcal.create_event({start_time.isoformat()}, {end_time.isoformat()}, {title}, {description}, {attendees}, send_updates={send_updates})"
                    print(f"Dry-run: would run {cmd}")
                else:
                    gcal.create_event(start_time.isoformat(), end_time.isoformat(), title, description, attendees, send_updates=send_updates)
            elif args.update:
                existing_events = gcal.get_events_by_date(start_time)
                if len(existing_events) != 1:
                    print("Number of existing events found different than 1. Case not handled. Exiting")
                    exit(1)

                event_id = existing_events[0]['id']
                if args.dry_run:
                    cmd = f"gcal.update_event({event_id}, {start_time.isoformat()}, {end_time.isoformat()}, {title}, {description}, {attendees}, send_updates={send_updates})"
                    print(f"Dry-run: would run {cmd}")
                else:
                    gcal.update_event(event_id, start_time.isoformat(), end_time.isoformat(), title, description, attendees, send_updates=send_updates)
            elif args.delete:
                existing_events = gcal.get_events_by_date(start_time)
                if len(existing_events) != 1:
                    print("Number of existing events found different than 1. Case not handled. Exiting")
                    exit(1)

                event_id = existing_events[0]['id']

                if args.dry_run:
                    cmd = f"gcal.delete_event({event_id}, send_updates={send_updates})"
                    print(f"Dry-run: would run {cmd}")
                else:
                    gcal.delete_event(event_id, send_updates=send_updates)
    except:
        print(f"Error encountered when processing event {event}")



