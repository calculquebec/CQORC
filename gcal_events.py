#!/bin/env python3
import os, argparse, datetime

import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.google.GCalInterface as GCalInterface
import CQORCcalendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import get_trainer_keys
from common import Trainers

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_id", help="Generate events for the course specified by the course_id")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default="./secrets", help="Directory that holds the configuration files")
parser.add_argument("--all", default=False, action='store_true', help="Act for all events")
parser.add_argument("--create", default=False, action='store_true', help="Create events")
parser.add_argument("--update", default=False, action='store_true', help="Update events")
parser.add_argument("--delete", default=False, action='store_true', help="Delete events")
parser.add_argument("--course", default=False, action='store_true', help="Course event")
parser.add_argument("--post_mortem", default=False, action='store_true', help="Post_mortem event")
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

start_offset_minutes = int(config['google.calendar']['start_offset_minutes'])

# get the events from the working calendar in the Google spreadsheets
calendar = CQORCcalendar.Calendar(config, args)
sessions = calendar.get_all_sessions()

# keep only sessions on the date listed
if args.date:
    sessions = [session for session in sessions if args.date.date().isoformat() in session['start_date']]
# keep only sessions for the given course_id
if args.course_id:
    sessions = [session for session in sessions if args.course_id == session['course_id']]

if args.no_notifications:
    send_updates = "none"
else:
    send_updates = "all"

for session in sessions:
    try:
        attendees = [trainers.calendar_email(key) for key in get_trainer_keys(session, ['instructor', 'host', 'assistants'])]
        webinar = zoom.get_webinar(webinar_id = session['zoom_id'])
        zoom_link = webinar['join_url']
        event_dict = {
            "course": {
                "status": args.course,
                "title": f"{session['code']} - {session['title']}",
                "start_time": to_iso8061(session['start_date']) + datetime.timedelta(minutes=start_offset_minutes),
                "end_time": to_iso8061(session['end_date']),
                "description": f"""Voyez l'invitation envoyée par Zoom, ou encore le canal sur Slack pour les liens""",
                "session_id": 'private_gcal_id',
                "set_function": calendar.set_private_gcal_id
            },
            "post_mortem": {
                "status": args.post_mortem,
                "title": f"{session['code']} - {session['title']} - post mortem",
                "start_time": to_iso8061(session['end_date']),
                "end_time":  to_iso8061(session['end_date']) + datetime.timedelta(minutes=30),
                "description": f"""Voici le lien Zoom <a href="{zoom_link}">{zoom_link}</a>, ou encore le canal sur Slack pour les liens et le google doc post mortem""",
                "session_id": 'post_mortem_private_gcal_id',
                "set_function": calendar.set_post_mortem_private_gcal_id
            }
        }

        if args.create:
            for key, value in event_dict.items():
                if value['status']:
                    if session[value['session_id']]:
                        event_id = session[value['session_id']]
                        print(f"Calendar ID found: {session[value['session_id']]}, not creating a new event")
                    elif args.dry_run:
                        cmd = f"gcal.create_event({value['start_time'].isoformat()}, {value['end_time'].isoformat()}, {value['title']}, {value['description']}, {attendees}, send_updates={send_updates})"
                        print(f"Dry-run: would run {cmd}")
                    else:
                        event = gcal.create_event(value['start_time'].isoformat(), value['end_time'].isoformat(), value['title'], value['description'], attendees, send_updates=send_updates)                            
                        value['set_function'](session['course_id'], session['start_date'], event['id'])
                        calendar.update_spreadsheet()

        elif args.update:
            for key, value in event_dict.items():
                if value['status']:
                    if session[value['session_id']]:
                        event_id = session[value['session_id']]
                    else:
                        existing_events = gcal.get_events_by_date(value['start_time'])
                        if len(existing_events) != 1:
                            print("Number of existing events found different than 1. Case not handled. Exiting")
                            exit(1)
                        event_id = existing_events[0]['id']

                    if args.dry_run:
                        cmd = f"gcal.update_event({event_id}, {value['start_time'].isoformat()}, {value['end_time'].isoformat()}, {value['title']}, {value['description']}, {attendees}, send_updates={send_updates})"
                        print(f"Dry-run: would run {cmd}")
                    else:
                        gcal.update_event(event_id, value['start_time'].isoformat(), value['end_time'].isoformat(), value['title'], value['description'], attendees, send_updates=send_updates)

        elif args.delete:
            for key, value in event_dict.items():
                if value['status']:
                    if session[value['session_id']]:
                        event_id = session[value['session_id']]
                    else:
                        existing_events = gcal.get_events_by_date(value['start_time'])
                        if len(existing_events) != 1:
                            print("Number of existing events found different than 1. Case not handled. Exiting")
                            exit(1)

                        event_id = existing_events[0]['id']

                    if args.dry_run:
                        cmd = f"gcal.delete_event({event_id}, send_updates={send_updates})"
                        print(f"Dry-run: would run {cmd}")
                    else:
                        gcal.delete_event(event_id, send_updates=send_updates)
                        value['set_function'](session['course_id'], session['start_date'], '')
                        calendar.update_spreadsheet()   

    except Exception as error:
        print(f"Error encountered when processing session {session}: %s" % error)


if not args.dry_run:
    calendar.update_spreadsheet()

