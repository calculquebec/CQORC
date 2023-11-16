#!/bin/env python3
import os, argparse, datetime

import interfaces.eventbrite.EventbriteInterface as Eventbrite
import interfaces.zoom.ZoomInterface as ZoomInterface

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config

parser = argparse.ArgumentParser()
parser.add_argument("--eventbrite_id", help="EventBrite event id")
parser.add_argument("--zoom_id", help="EventBrite event id")
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
args = parser.parse_args()

# read configuration files
global_config = get_config(args)

# initialize Zoom interface
zoom_user = global_config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(global_config['zoom']['account_id'], global_config['zoom']['client_id'], global_config['zoom']['client_secret'], global_config['global']['timezone'], zoom_user)

webinars = []
if args.zoom_id:
    webinars = zoom.get_webinars(ids = [int(args.zoom_id)])
elif args.date:
    webinars = zoom.get_webinars(date = to_iso8061(args.date).date())

if len(webinars) != 1:
    print(f"Error, number of webinars found is not 1: {len(webinar)}")
    exit(1)

# get the list of participants to the webinar
webinar = webinars[0]
participants = zoom.get_webinar_participants(webinar['id'])
attendance_duration = {}
# calculating the total attendance duration for each attendee
for p in participants:
    attendance_duration[p['user_email']] = attendance_duration.get(p['user_email'], 0) + p['duration']

# retrieve the maximum duration
email_max_duration = max(attendance_duration, key=attendance_duration.get)
max_duration = attendance_duration[email_max_duration]

# keep only attendees which have attended for more than a threshold
threshold = float(global_config['script.presence']['presence_threshold'])
attendees = [email for email in attendance_duration.keys() if attendance_duration[email] > threshold * max_duration]

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])
# retrieve event from EventBrite
event = None
if args.eventbrite_id:
    event = eb.get_event(args.eventbrite_id)
else:
    events = eb.get_events(global_config['eventbrite']['organization_id'], time_filter="past", flattened=True, order_by="start_asc")
    for e in events:
        if args.date and to_iso8061(e['start']['local']).date() == to_iso8061(args.date).date():
            event = e
            break

if not event:
    print("Error, no EventBrite event found")
    exit(1)

registrants = eb.get_event_attendees_by_status(event['id'])
for r in registrants:
    print(str(r))
#print(str(registrants))

