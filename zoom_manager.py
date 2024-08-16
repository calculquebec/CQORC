#!/bin/env python3
import os, argparse, datetime
import pprint

import interfaces.zoom.ZoomInterface as ZoomInterface

from CQORCcalendar import Calendar
from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import Trainers
from common import get_survey_link

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
#parser.add_argument("--create-webinar", default=False, action='store_true', help="Create webinar")
parser.add_argument("--list-panelists", default=False, action='store_true', help="List panelists")
parser.add_argument("--update-webinar", default=False, action='store_true', help="Update webinar settings, panelists and hosts")
parser.add_argument("--update-webinar-hosts", default=False, action='store_true', help="Update webinar hosts")
parser.add_argument("--update-webinar-panelists", default=False, action='store_true', help="Update webinar panelists")
parser.add_argument("--update-webinar-settings", default=False, action='store_true', help="Update webinar settings")
parser.add_argument("--show-webinar", default=False, action='store_true', help="Show webinar")
parser.add_argument("--invites", default=False, action='store_true', help="Invite trainers")
parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
args = parser.parse_args()

# read configuration files
config = get_config(args)
trainers = Trainers(config['global']['trainers_db'])

secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
credentials_file = config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
zoom_user = config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(config['zoom']['account_id'], config['zoom']['client_id'], config['zoom']['client_secret'], config['global']['timezone'], zoom_user)


# get the courses from the working calendar in the Google spreadsheets
courses = Calendar(config, args).get_courses()

# keep only courses that start on the date listed
if args.date:
    courses = [courses for course in courses if args.date.date().isoformat() in course['sessions'][0]['start_date']]

for course in courses:
#    try:
        # no course code, continue
        first_session = course['sessions'][0]
        if not 'code' in first_session:
            continue

        date = to_iso8061(first_session['start_date']).date()
        course_code = first_session['code']
        locale = first_session['langue']
        title = first_session['title']

        start_time = to_iso8061(first_session['start_date'])
        duration = sum([float(session['hours']) for session in courses['sessions'])

        if first_session['zoom_id']:
            webinar = zoom.get_webinar(first_session['zoom_id'])
        else:
            webinars = zoom.get_webinars(date = start_time.date())
            if webinars:
                webinar = zoom.get_webinar(webinar_id = webinars[0]['id'])

        if args.update_webinar_panelists or args.update_webinar:
            panelists = zoom.get_panelists(webinar['id'])
            for session in course['sessions']:
                for k in session['assistants'].split(',') + [session['instructor']] + session['host'].split(','):
                    key = k.strip()
                    if trainers.zoom_email(key) not in [x['email'] for x in panelists]:
                        zoom.add_panelist(webinar['id'], trainers.zoom_email(key), trainers.fullname(key))

        if args.update_webinar_hosts or args.update_webinar:
            params = {}
            settings = {}
            settings['alternative_hosts'] = ','.join(set([trainers.zoom_email(k) for k in session['host'].split(',') for session in course['sessions']]))
            params['settings'] = settings
            zoom.update_webinar(webinar['id'], params)

        if args.update_webinar_settings or args.update_webinar:
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

        if args.show_webinar:
            pp = pprint.PrettyPrinter(indent=4)
            print("Webinar:")
            pp.pprint(webinar)

#        if args.create_webinar:
#            if args.dry_run:
#                cmd = f"slack.create_channel({slack_channel_name})"
#                print(f"Dry-run: would run {cmd}")
#            else:
#                slack.create_channel(slack_channel_name)

#        if args.invites:
#            if args.dry_run:
#                cmd = f"slack.invite_to_channel({slack_channel_name}, {attendees})"
#                print(f"Dry-run: would run {cmd}")
#            else:
#                slack.invite_to_channel(slack_channel_name, attendees)



#    except Exception as e:
#        print(f"Error encountered when processing event {event}: \n\n{e}")


