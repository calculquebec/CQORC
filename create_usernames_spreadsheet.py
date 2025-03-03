#!/bin/env python3

import os, argparse, datetime

import interfaces.eventbrite.EventbriteInterface as Eventbrite
import interfaces.google.GDriveInterface as GDriveInterface
import interfaces.google.GSheetsInterface as GSheetsInterface
import interfaces.slack.SlackInterface as SlackInterface
import CQORCcalendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title

parser = argparse.ArgumentParser()
parser.add_argument("--course_id", default=None, help="Manage only for this course id")
parser.add_argument("--event_id", help="EventBrite event id")
parser.add_argument("--next", default=False, action='store_true', help="Generate for the next event after now")
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_code", help="Code for the course (i.e. HPC101)")
parser.add_argument("--password", help="Password to access the cluster")
parser.add_argument("--url", help="URL to access the cluster")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default="./secrets", help="Directory that holds the configuration files")
parser.add_argument("--create_template_file", default=False, action='store_true', help="Create a spreadsheet to act as template file")
parser.add_argument("--update", default=False, action='store_true', help="Update existing spreadsheet instead of creating a new one")
args = parser.parse_args()

# read configuration files
global_config = get_config(args)

# take the credentials file either from google.sheets or from google section
credentials_file = global_config['google']['credentials_file']
secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
credentials_file_path = os.path.join(secrets_dir, credentials_file)
# initialize the Google Drive interface
gdrive = GDriveInterface.GDriveInterface(credentials_file_path)
gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)
calendar = CQORCcalendar.Calendar(global_config, args)

if args.course_id:
    if args.course_id in calendar.keys():
        course = calendar[args.course_id]
    else:
        print(f"Course {args.course_id} not found")
        exit(1)

# this script's config
config = global_config['script.usernames']
if args.create_template_file:
    sheet = gsheets.create_spreadsheet("Template", [[]], config['google_drive_folder_id'])
    print("Template created: %s" % gdrive.get_file_url(sheet))
    exit(0)

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])

eventbrite_id =None
if course:
    eventbrite_id = course['sessions'][0]['eventbrite_id']
elif args.event_id:
    eventbrite_id = args.event_id

# retrieve event from EventBrite
if eventbrite_id:
    event = eb.get_event(eventbrite_id)
else:
    events = eb.get_events(global_config['eventbrite']['organization_id'], time_filter="current_future", flattened=True, order_by="start_asc")
    for e in events:
        if args.next and to_iso8061(e['start']['local']) > to_iso8061(datetime.datetime.now()):
            event = e
            break
        elif args.date and  to_iso8061(e['start']['local']).date() == to_iso8061(args.date).date():
            event = e
            break
    eventbrite_id = event['id']

# course was not specified, find it from eventbrite_id
if not course:
    courses = [course for course in calendar.get_courses() if course['sessions'][0]['eventbrite_id'] == eventbrite_id]
    course = courses[0]

# retrieve list of attendees
attendees = eb.get_event_attendees_registered(eventbrite_id, fields = ['email', 'name'])

date = to_iso8061(event["start"]["local"]).date()
title = event["name"]["text"]
locale = event["locale"].split('_')[0]

if args.course_code:
    course_code = args.course_code
else:
    course_code = course['sessions'][0]['code']

if args.url:
    url = args.url
elif 'url_template' in config:
    url = eval('f' + repr(config['url_template']))

if args.password:
    password = args.password
elif 'password_template' in config:
    password = eval('f' + repr(config['password_template']))

# load the template for filename, based on the locale
filename_template = config.get(f"filename_template_{locale}", config.get('filename_template_en'))
new_file_name = eval('f' + repr(filename_template))

# create or update the spreadsheet
source_file_id = config.get("template_%s" % locale, config["template_en"])
if args.update:
    sheet_id = gdrive.get_file_id(config['google_drive_folder_id'], new_file_name)
else:
    new_file = gdrive.copy_file(source_file_id, new_file_name, config['google_drive_folder_id'])
    sheet_id = new_file['id']

# update the spreadsheet
header = [[url], [password]]
header_range = config['header_range']
gsheets.update_values(sheet_id, header_range, header)


# Create the data to be inserted, sort by name alphabetically

if locale == "fr":
    start_username=0;
else:
    start_username=100;

data = [
    [eval('f' + repr(config['username_template'])), attendee['name']]
    for user_index, attendee in enumerate(sorted(attendees.values(), key=lambda x: x['name'].casefold()), start=start_username)
]

data_range = config['data_range']
gsheets.update_values(sheet_id, data_range, data)

# clone the spreadsheet protection
gsheets.copy_protection(source_file_id, sheet_id)

sheet_url = gdrive.get_file_url(sheet_id)

print(f"URL: {sheet_url}")

# post to Slack
slack = SlackInterface.SlackInterface(global_config['slack']['bot_token'])

channel_name = course['sessions'][0]['slack_channel']

if not slack.is_member(channel_name):
    slack.join_channel(channel_name)


if filename_template == config.get('filename_template_en'):
    message = f"To connect to the platform, select your username (beside your name) here: {sheet_url}"
else:
    message = f"Pour vous connecter à la plateforme, sélectionner votre nom d'utilisateur (associé à votre nom) ici: {sheet_url}"

start = to_iso8061(event['start']['local'])

# post now
slack.post_to_channel(channel_name, message)

# post a reminder 30 minutes before start
# post_time = start + datetime.timedelta(minutes=-30)
# slack.post_to_channel(channel_name, message, post_time)

# add a bookmark
if args.update:
    slack.update_channel_bookmarks(channel_name, slack.list_channel_bookmarks(channel_name))
else:
    slack.add_bookmark_to_channel(channel_name, "Username spreadhseet", sheet_url)
