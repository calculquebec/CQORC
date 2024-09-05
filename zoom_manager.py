#!/bin/env python3
import os, argparse, datetime
import pprint

import interfaces.zoom.ZoomInterface as ZoomInterface
import CQORCcalendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import get_trainer_keys
from common import Trainers
from common import get_survey_link

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_id", help="Handle course specified by course_id")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default="./secrets", help="Directory that holds the configuration files")
parser.add_argument("--create", default=False, action='store_true', help="Create webinar")
parser.add_argument("--delete", default=False, action='store_true', help="Delete webinar")
parser.add_argument("--list-panelists", default=False, action='store_true', help="List panelists")
parser.add_argument("--update", default=False, action='store_true', help="Update webinar settings, panelists and hosts")
parser.add_argument("--update-hosts", default=False, action='store_true', help="Update webinar hosts")
parser.add_argument("--update-panelists", default=False, action='store_true', help="Update webinar panelists")
parser.add_argument("--update-settings", default=False, action='store_true', help="Update webinar settings")
parser.add_argument("--show", default=False, action='store_true', help="Show webinar")
parser.add_argument("--invites", default=False, action='store_true', help="Invite trainers")
parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
args = parser.parse_args()

# read configuration files
config = get_config(args)
trainers = Trainers(config['global']['trainers_db'])

timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
zoom_user = config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(config['zoom']['account_id'], config['zoom']['client_id'], config['zoom']['client_secret'], config['global']['timezone'], zoom_user)


# get the courses from the working calendar in the Google spreadsheets
calendar = CQORCcalendar.Calendar(config, args)
courses = calendar.get_courses()

# keep only courses that start on the date listed
if args.date:
    courses = [courses for course in courses if args.date.date().isoformat() in course['sessions'][0]['start_date']]
# keep only the course for the course_id specified
if args.course_id:
    courses = [calendar[args.course_id]]

for course in courses:
#    try:
        # no course code, continue
        first_session = course['sessions'][0]
        if not 'code' in first_session:
            continue

        date = to_iso8061(first_session['start_date']).date()
        course_code = first_session['code']
        locale = first_session['language']
        title = first_session['title']

        # for multi-session courses, the duration of the webinar must be from the start to the end
        start_time = min([to_iso8061(session['start_date']) for session in course['sessions']])
        end_time = max([to_iso8061(session['end_date']) for session in course['sessions']])
        duration = (end_time - start_time).total_seconds()/3600

        if args.create:
            if first_session['zoom_id']:
                print(f"Zoom ID already exists for this session {first_session['zoom_id']}, not creating")
            else:
                webinar = zoom.create_webinar(first_session['title'], duration, start_time.date(), start_time.time())
                if webinar and 'id' in webinar:
                    calendar.set_zoom_id(first_session['course_id'], webinar['id'])

        if first_session['zoom_id']:
            webinar = zoom.get_webinar(first_session['zoom_id'])
        else:
            webinars = zoom.get_webinars(date = start_time.date())
            if webinars:
                webinar = zoom.get_webinar(webinar_id = webinars[0]['id'])
                calendar.set_zoom_id(first_session['course_id'], webinar['id'])

        if args.delete:
            print(f"Deleting webinar {webinar['id']}")
            zoom.delete_webinar(webinar['id'])
            calendar.set_zoom_id(first_session['course_id'], '')

        if args.update_panelists or args.update:
            attendee_keys = get_trainer_keys(course, ['assistants', 'instructor', 'host'])
            panelists = zoom.get_panelists(webinar['id'])
            for key in attendee_keys:
                if trainers.zoom_email(key) not in [x['email'] for x in panelists]:
                    zoom.add_panelist(webinar['id'], trainers.zoom_email(key), trainers.fullname(key))

        if args.update_hosts or args.update:
            params = {}
            settings = {}
            settings['alternative_hosts'] = ','.join([trainers.zoom_email(k) for k in get_trainer_keys(course, ['host'])])
            params['settings'] = settings
            zoom.update_webinar(webinar['id'], params)

        if args.update_settings or args.update:
            params = {}
            settings = {}
            settings['attendees_and_panelists_reminder_email_notification'] = {'enable': True, 'type': 1}
            settings['email_language'] = 'fr-FR' if locale.lower() == 'fr' else 'en-US'
            settings['contact_email'] = 'formation@calculquebec.ca'
            settings['registrants_confirmation_email'] = True
            settings['registrants_email_notification'] = True
            settings['post_webinar_survey'] = True
            settings['survey_url'] = get_survey_link(config, locale, title, date)
            settings['question_and_answer'] = {'allow_submit_questions': True, 'enable': True, 'attendees_can_upvote': True, 'attendees_can_comment': True, 'allow_anonymous_questions':False }
            params['settings'] = settings
            params['duration'] = str(int(duration*60))
            params['start_time'] = start_time.astimezone(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
            pp = pprint.PrettyPrinter(indent=4)
            print("Params:")
            pp.pprint(params)
            zoom.update_webinar(webinar['id'], params)

        if args.list_panelists:
            panelists = zoom.get_panelists(webinar['id'])
            pp = pprint.PrettyPrinter(indent=4)
            print("Panelists:")
            pp.pprint(panelists)

        if args.show:
            pp = pprint.PrettyPrinter(indent=4)
            print("Webinar:")
            pp.pprint(webinar)

#    except Exception as e:
#        print(f"Error encountered when processing event {event}: \n\n{e}")

calendar.update_spreadsheet()


