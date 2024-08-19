#!/bin/env python3
import os, argparse, datetime

import interfaces.eventbrite.EventbriteInterface as Eventbrite
import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.slack.SlackInterface as SlackInterface
import CQORCcalendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import Trainers
from statistics import mean

parser = argparse.ArgumentParser()
parser.add_argument("--eventbrite_id", help="EventBrite event id")
parser.add_argument("--zoom_id", help="EventBrite event id")
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_id", help="ID of the course")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--noslack", default=False, action='store_true', help="Do not post to Slack")
parser.add_argument("--verbose", default=False, action='store_true', help="Print lists of users")
args = parser.parse_args()

# read configuration files
global_config = get_config(args)

# get the events from the working calendar in the Google spreadsheets
calendar = CQORCcalendar.Calendar(config, args)
course = None
if args.course_id:
    course = calendar[args.course_id]

# initialize Zoom interface
zoom_user = global_config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(global_config['zoom']['account_id'], global_config['zoom']['client_id'], global_config['zoom']['client_secret'], global_config['global']['timezone'], zoom_user)

webinars = []
if args.zoom_id:
    webinars = zoom.get_webinars(ids = [int(args.zoom_id)])
elif course:
    webinars = zoom.get_webinar(ids = [int(course[0]['zoom_id'])])
elif args.date:
    webinars = zoom.get_webinars(date = to_iso8061(args.date).date())

if len(webinars) != 1:
    print(f"Error, number of webinars found is not 1: {len(webinar)}")
    exit(1)

# get the list of participants to the webinar
webinar = webinars[0]
# each participant can be listed more than once, these are records
participants_records = zoom.get_webinar_participants(webinar['id'])
if args.verbose:
    print("Raw Zoom records:")
    for v in participants_records:
        print(f"{v}")
    print("===============")

zoom_participants = {p['user_email']: {'user_email': p['user_email'], 'name': p['name'], 'duration': 0} for p in participants_records}
# calculating the total attendance duration for each attendee
for r in participants_records:
    zoom_participants[r['user_email']]['duration'] += r['duration']

# retrieve the maximum duration
mean_duration = mean([v['duration'] for k,v in zoom_participants.items()])

# keep only attendees which have attended for more than a threshold
threshold = float(global_config['script.presence']['presence_threshold'])
if args.verbose:
    print("List from Zoom before filtering:")
    for k,v in zoom_participants.items():
        print(f"{k}:{v}")
    print("===============")
    print(f"Max duration:{mean_duration}")
    print(f"Threshold duration:{threshold * mean_duration}")

zoom_participants = {k: v for k,v in zoom_participants.items() if v['duration'] > threshold * mean_duration}
if args.verbose:
    print("List from Zoom after filtering:")
    for k,v in zoom_participants.items():
        print(f"{k}:{v}")
    print("===============")

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])
# retrieve event from EventBrite
eb_event = None
if args.eventbrite_id:
    eb_event = eb.get_event(args.eventbrite_id)
elif course:
    eb_event = eb.get_event(course[0]['eventbrite_id'])
else:
    eb_events = eb.get_events(global_config['eventbrite']['organization_id'], time_filter="past", flattened=True, order_by="start_desc")
    todays_events = []
    for e in eb_events:
        if args.date and to_iso8061(e['start']['local']).date() == to_iso8061(args.date).date():
            todays_events += [e]
        if len(todays_events) > 1:
            print(f"Error, number of EventBrite event found is not 1: {len(todays_events)}, use --zoom_id and --eventbrite_id")
            exit(1)
    eb_event = todays_events[0]


if not eb_event:
    print("Error, no EventBrite event found")
    exit(1)

eb_registrants = eb.get_event_attendees_by_status(eb_event['id'], fields = ['email', 'first_name', 'last_name', 'status', 'name'])
eb_attendees = eb.get_event_attendees_present(eb_event['id'], fields = ['email', 'first_name', 'last_name', 'status', 'name'])

if args.verbose:
    print("List from EventBrite:")
    for k,v in eb_attendees.items():
        print(f"{k}:{v}")
    print("===============")


# match by email
missing_in_eb = [email for email in zoom_participants.keys() if email not in eb_attendees.keys()]
should_not_in_eb = [email for email in eb_attendees.keys() if email not in zoom_participants.keys()]


message = ""

# match by name, emails in zoom but not EventBrite
for index, email in enumerate(missing_in_eb):
    name = zoom_participants[email]['name']
    # find if a registrant has the same name
    eb_email = [k for k,v in eb_registrants.items() if v['name'] == name]
    # if one email is found and is different from the one in zoom, replace the email for the eb_email
    if len(eb_email) == 1 and eb_email[0] != email:
        message += f"{name} used email {email} in Zoom, but {eb_email[0]} in EventBrite, replacing\n"
        if eb_email[0] not in eb_attendees.keys():
            missing_in_eb[index] = eb_email[0]
        else:
            missing_in_eb.remove(email)
        # if the eb_email was in the list of should not be in eb, remove it from there
        if eb_email[0] in should_not_in_eb:
            should_not_in_eb.remove(eb_email[0])

# remove trainers from missing_in_eb
trainers = Trainers(global_config['global']['trainers_db'])
missing_in_eb = [email for email in missing_in_eb if email not in trainers.all_emails()]

# remove filtered domains from missing_in_eb
ignored_email_domains = global_config['script.presence']['ignored_email_domains'].split(',')
for domain in ignored_email_domains:
    missing_in_eb = [email for email in missing_in_eb if domain not in email]


if missing_in_eb:
    message += "\nThe following people attended the Zoom event, but are not in EventBrite:\n"
    for email in missing_in_eb:
        if email not in eb_registrants:
            message += f"{email}: {zoom_participants[email]['name']}\n"

    message += "\nThe following people attended the Zoom event, but are not checked in in EventBrite:\n"
    for email in missing_in_eb:
        if email in eb_registrants:
            message += f"{eb_registrants[email]['name']}: {email}\n"

if should_not_in_eb:
    message += "\nThe following people are marked as Checked in in EventBrite, but did not attend long enough in Zoom:\n"
    for email in should_not_in_eb:
        if email in eb_registrants:
            message += f"{eb_registrants[email]['name']}: {email}\n"

if not message:
    message = "No mistake found in EventBrite checked-in attendees"

event_id = eb_event['id']
eventbrite_checkin_url = eval('f' + repr(global_config['script.presence']['eventbrite_checkin_url']))

message += f"\nManage check-ins here: {eventbrite_checkin_url}"
print(message)

# post to Slack
if not args.noslack:
    slack = SlackInterface.SlackInterface(global_config['slack']['bot_token'])

    date = to_iso8061(eb_event['start']['local']).date()
    locale = eb_event['locale'].split('_')[0]
    course_code = extract_course_code_from_title(global_config, eb_event["name"]["text"])
    channel_name = eval('f' + repr(global_config['global']['slack_channel_template']))

    if not slack.is_member(channel_name):
        slack.join_channel(channel_name)

    slack.post_to_channel(channel_name, message)

