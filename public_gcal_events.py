#!/bin/env python3
import os, argparse, datetime

import interfaces.google.GCalInterface as GCalInterface
import interfaces.eventbrite.EventbriteInterface as Eventbrite
import yaml
from CQORCcalendar import Calendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import actualize_repo

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--all", default=False, action='store_true', help="Act for all events")
parser.add_argument("--create", default=False, action='store_true', help="Create events")
parser.add_argument("--update", default=False, action='store_true', help="Update events")
parser.add_argument("--delete", default=False, action='store_true', help="Delete events")
parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
args = parser.parse_args()

# read configuration files
config = get_config(args)

secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
credentials_file = config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
gcal = GCalInterface.GCalInterface(credentials_file_path, config['google.calendar']['public_calendar_id'], timezone)

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(config['eventbrite']['api_key'])

def get_eb_event_by_date(query_date):
    # retrieve event from EventBrite
    eb_event = None
    eb_events = eb.get_events(config['eventbrite']['organization_id'], time_filter="current_future", flattened=True, order_by="start_asc")
    for e in eb_events:
        if to_iso8061(e['start']['local']).date() == query_date:
            eb_event = e
            break
    return eb_event

# get the events from the working calendar in the Google spreadsheets
events = Calendar(config, args).get_all_sessions()

# keep only events on the date listed
if args.date:
    events = [event for event in events if args.date.date().isoformat() in event['start_date']]

send_updates = "none"

# ensure descriptions are up to date
actualize_repo(config["descriptions"]["repo_url"], config["descriptions"]["local_repo"])

for event in events:
    try:
        if len(event['code']):
            # Read the description from the repo
            with open(os.path.join(config["descriptions"]["local_repo"], f"{event['code']}-{event['langue']}.yaml")) as f:
                event_description = yaml.safe_load(f)
        else:
            event_description = None
            print("Empty workshop code, skipping updating description")        

        start_time = to_iso8061(event['start_date'])
        end_time = to_iso8061(event['end_date'])
        duration = int(event['hours'])

        eb_event = get_eb_event_by_date(start_time.date())
        if eb_event:
            eb_event_id = eb_event['id']

        registration_url = eval('f' + repr(config['eventbrite']['registration_url']))
        registration_url = f"""<a href="{registration_url}">{registration_url}</a>"""

        attendees = None
        if event_description:
            title = event_description['title']
            summary = f"""{event_description['summary']}

{event_description['description']}"""
            plan = "\n* ".join([''] + event_description['plan'])
        else:
            title = event['title']
            plan = "-"
            summary = "-"

        # take the EventBrite title in priority
        if eb_event:
            title = eb_event['name']['text']

        if event['langue'] == "FR":
            description = f"""Inscriptions: {registration_url}

{summary}

Plan:
{plan}
"""
        else:
            description = f"""Registration:: {registration_url}

{summary}

Plan:
{plan}
"""

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
    except Exception as e:
        print(f"Error encountered when processing event {event}: {e}")



