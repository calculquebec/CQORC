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
parser.add_argument("--url", required=True, help="URL to access the cluster")
parser.add_argument("--course_code", required=True, help="Code for the course (i.e. HPC101)")
parser.add_argument("--password", required=True, help="Password to access the cluster")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")

args = parser.parse_args()

config = configparser.ConfigParser()
config_dir = os.environ.get('CQORC_CONFIG_DIR', args.config_dir)
secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
print("Reading config files: %s" % str(config_files))
config.read(config_files)


# take the credentials file either from google.sheets or from google section
credentials_file = config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
# initialize the Google Drive interface
gdrive = GDriveInterface.GDriveInterface(credentials_file_path)
gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(config['eventbrite']['api_key'])

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
locale = event["locale"].split('_')[0]
title = config['script.usernames'].get("title_%s" % locale, config['script.usernames']['template_en'])
new_file_name = f"{date} - {args.course_code} - {title}"

# create the spreadsheet
source_file_id = config['script.usernames'].get("template_%s" % locale, config['script.usernames']["template_en"])
new_file = gdrive.copy_file(source_file_id, new_file_name, config['script.usernames']['google_drive_folder_id'])
sheet_id = new_file['id']

# update the spreadsheet
header = [[args.url], [args.password]]
gsheets.update_values(sheet_id, "B1:B2", header)

data = [["user{:02d}".format(i+1), attendee] for i, attendee in enumerate(attendees)]
gsheets.update_values(sheet_id, "A5:B", data)

