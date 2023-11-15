#!/bin/env python3

import os, argparse, glob, configparser, datetime

import interfaces.eventbrite.EventbriteInterface as Eventbrite
import interfaces.google.GDriveInterface as GDriveInterface
import interfaces.google.GSheetsInterface as GSheetsInterface

from common import valid_date, to_iso8061, ISO_8061_FORMAT

parser = argparse.ArgumentParser()
parser.add_argument("--event_id", help="EventBrite event id")
parser.add_argument("--next", default=False, action='store_true', help="Generate for the next event after now")
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--course_code", help="Code for the course (i.e. HPC101)")
parser.add_argument("--password", help="Password to access the cluster")
parser.add_argument("--url", help="URL to access the cluster")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--create_template_file", default=False, action='store_true', help="Create a spreadsheet to act as template file")
args = parser.parse_args()

global_config = configparser.ConfigParser()
config_dir = os.environ.get('CQORC_CONFIG_DIR', args.config_dir)
secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
print("Reading config files: %s" % str(config_files))
global_config.read(config_files)


# take the credentials file either from google.sheets or from google section
credentials_file = global_config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
# initialize the Google Drive interface
gdrive = GDriveInterface.GDriveInterface(credentials_file_path)
gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)

# this script's config
config = global_config['script.usernames']
if args.create_template_file:
    sheet = gsheets.create_spreadsheet("Template", [[]], config['google_drive_folder_id'])
    print("Template created: %s" % gdrive.get_file_url(sheet))
    exit(0)

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])
# retrieve event from EventBrite
if args.event_id:
    event = eb.get_event(args.event_id)
else:
    events = eb.get_events(global_config['eventbrite']['organization_id'], time_filter="current_future", flattened=True, order_by="start_asc")
    for e in events:
        if args.next and to_iso8061(e['start']['local']) > to_iso8061(datetime.datetime.now()):
            event = e
            break
        elif args.date and  to_iso8061(e['start']['local']).date() == to_iso8061(args.date).date():
            event = e
            break

# retrieve list of attendees
attendees = None
attendees = eb.get_event_attendees_registered(event['id'])

date = to_iso8061(event["start"]["local"]).date()
title = event["name"]["text"]
locale = event["locale"].split('_')[0]

if args.course_code:
    course_code = args.course_code
else:
    course_code = eval('f' + repr(config['course_code_template']))

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

# create the spreadsheet
source_file_id = config.get("template_%s" % locale, config["template_en"])
new_file = gdrive.copy_file(source_file_id, new_file_name, config['google_drive_folder_id'])
sheet_id = new_file['id']

# update the spreadsheet
header = [[url], [password]]
header_range = config['header_range']
gsheets.update_values(sheet_id, header_range, header)

data = [[eval('f' + repr(config['username_template'])), attendee] for user_index, attendee in enumerate(attendees)]
data_range = config['data_range']
gsheets.update_values(sheet_id, data_range, data)

print("URL: %s" % gdrive.get_file_url(new_file['id']))

