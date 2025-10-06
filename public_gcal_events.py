#!/bin/env python3
import os, argparse, datetime, itertools

import interfaces.google.GCalInterface as GCalInterface
import interfaces.eventbrite.EventbriteInterface as Eventbrite
import yaml
import CQORCcalendar
import re

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import actualize_repo

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_id", help="Generate events for the course specified by the course_id")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default="./secrets", help="Directory that holds the configuration files")
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
calendar = CQORCcalendar.Calendar(config, args)
sessions = calendar.get_all_sessions()

# keep only sessions on the date listed
if args.date:
    sessions = [session for session in sessions if args.date.date().isoformat() in session['start_date']]
# keep only sessions for the given course_id
if args.course_id:
    sessions = [session for session in sessions if args.course_id == session['course_id']]

send_updates = "none"

# ensure descriptions are up to date
actualize_repo(config["descriptions"]["repo_url"], config["descriptions"]["local_repo"])

for session in sessions:
    try:
        if len(session['code']):
            # Read the description from the repo
            with open(os.path.join(config["descriptions"]["local_repo"], f"{session['code']}-{session['language']}.yaml")) as f:
                event_description = yaml.safe_load(f)
        else:
            event_description = None
            print("Empty workshop code, skipping updating description")

        start_time = to_iso8061(session['start_date'])
        end_time = to_iso8061(session['end_date'])

        if session['eventbrite_id']:
            eb_event = eb.get_event(session['eventbrite_id'])
        else:
            eb_event = get_eb_event_by_date(start_time.date())
        eb_event_id = None
        if eb_event:
            eb_event_id = eb_event['id']

        registration_url = eval('f' + repr(config['eventbrite']['registration_url']))
        registration_url = f"""<a href="{registration_url}">{registration_url}</a>"""

        attendees = None
        if event_description:
            title = event_description['title']
            summary = f"""{event_description['summary']}

{event_description['description']}"""
            if isinstance(event_description['plan'], list) and isinstance(event_description['plan'][0], str):
                plan = "\n* ".join([''] + event_description['plan'])
            elif isinstance(event_description['plan'], list) and isinstance(event_description['plan'][0], list):
                # we flatten the 2d list
                plan = "\n* ".join([''] + list(itertools.chain.from_iterable(event_description['plan'])))
        else:
            title = session['title']
            plan = "-"
            summary = "-"

        # take the EventBrite title in priority
        if eb_event:
            title = eb_event['name']['text']

        if session['language'] == "FR":
            presence = re.search(r'\[\s*([^\],]+)', session['title']).group(1)
            description = f"""Inscriptions: {registration_url}

{summary}

Plan:
{plan}

Tags:
Presence: {presence}
Cost basis: {session['cost_basis']}
Language: francais
Registration URL: {registration_url}

"""
        else:
            presence = re.search(r'\[\s*([^\],]+)', session['title']).group(1)
            description = f"""Registration:: {registration_url}

{summary}

Plan:
{plan}

Tags:
Presence: {presence}
Cost basis: {session['cost_basis']}
Language: english
Registration URL: {registration_url}

"""
        if args.create:
            if session['public_gcal_id']:
                event_id = session['public_gcal_id']
                print(f"Calendar ID found: {session['public_gcal_id']}, not creating a new event")
            elif args.dry_run:
                cmd = f"gcal.create_event({start_time.isoformat()}, {end_time.isoformat()}, {title}, {description}, {attendees}, send_updates={send_updates})"
                print(f"Dry-run: would run {cmd}")
            else:
                event = gcal.create_event(start_time.isoformat(), end_time.isoformat(), title, description, attendees, send_updates=send_updates)
                calendar.set_gcal_id(session['course_id'], session['start_date'], event['id'], "public_gcal_id")
                calendar.update_spreadsheet()

        elif args.update:
            if session['public_gcal_id']:
                event_id = session['public_gcal_id']
            else:
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
            if session['public_gcal_id']:
                event_id = session['public_gcal_id']
            else:
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
                calendar.set_gcal_id(session['course_id'], session['start_date'], '', "public_gcal_id")
                calendar.update_spreadsheet()

    except Exception as e:
        print(f"Error encountered when processing session {session}: {e}")


if not args.dry_run:
    calendar.update_spreadsheet()

