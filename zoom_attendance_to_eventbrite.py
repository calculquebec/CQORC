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
# each participant can be listed more than once, these are records
participants_records = zoom.get_webinar_participants(webinar['id'])
zoom_participants = {p['user_email']: {'user_email': p['user_email'], 'name': p['name'], 'duration': 0} for p in participants_records}
# calculating the total attendance duration for each attendee
for r in participants_records:
    zoom_participants[r['user_email']]['duration'] += r['duration']

# retrieve the maximum duration
max_duration = max([v['duration'] for k,v in zoom_participants.items()])

# keep only attendees which have attended for more than a threshold
threshold = float(global_config['script.presence']['presence_threshold'])
zoom_participants = {k: v for k,v in zoom_participants.items() if v['duration'] > threshold * max_duration}

# initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])
# retrieve event from EventBrite
event = None
if args.eventbrite_id:
    event = eb.get_event(args.eventbrite_id)
else:
    events = eb.get_events(global_config['eventbrite']['organization_id'], time_filter="past", flattened=True, order_by="start_desc")
    for e in events:
        if args.date and to_iso8061(e['start']['local']).date() == to_iso8061(args.date).date():
            event = e
            break

if not event:
    print("Error, no EventBrite event found")
    exit(1)

eb_registrants = eb.get_event_attendees_by_status(event['id'], fields = ['email', 'first_name', 'last_name', 'status', 'name'])
eb_attendees = eb.get_event_attendees_present(event['id'], fields = ['email', 'first_name', 'last_name', 'status', 'name'])

# match by email
missing_in_eb = [email for email in zoom_participants.keys() if email not in eb_attendees.keys()]
should_not_in_eb = [email for email in eb_attendees.keys() if email not in zoom_participants.keys()]

# match by name, emails in zoom but not EventBrite
for index, email in enumerate(missing_in_eb):
    name = zoom_participants[email]['name']
    # find if a registrant has the same name
    eb_email = [k for k,v in eb_registrants.items() if v['name'] == name]
    # if one email is found, replace the email for the eb_email
    if len(eb_email) == 1:
        print(f"{name} used email {email} in Zoom, but {eb_email[0]} in EventBrite, replacing")
        if eb_email[0] not in eb_attendees.keys():
            missing_in_eb[index] = eb_email[0]
        else:
            missing_in_eb.remove(email)
        # if the eb_email was in the list of should not be in eb, remove it from there
        if eb_email[0] in should_not_in_eb:
            should_not_in_eb.remove(eb_email[0])

print("\nThe following people attended the Zoom event, but are not in EventBrite")
for email in missing_in_eb:
    if email not in eb_registrants:
        print(f"{email}: {zoom_participants[email]['name']}")
# remove filtered domains from missing_in_eb
ignored_email_domains = global_config['script.presence']['ignored_email_domains']
for domain in ignored_email_domains:
    missing_in_eb = [email for email in missing_in_eb if domain not in email]


print("\nThe following people attended the Zoom event, but are not checked in in EventBrite")
for email in missing_in_eb:
    if email in eb_registrants:
        print(f"{eb_registrants[email]['name']}: {email}")

print("\nThe following people are marked as Checked in in EventBrite, but did not attend long enough in Zoom")
for email in should_not_in_eb:
    if email in eb_registrants:
        print(f"{eb_registrants[email]['name']}: {email}")




