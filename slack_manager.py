#!/bin/env python3
import os, argparse, datetime

import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.slack.SlackInterface as SlackInterface
from CQORCcalendar import Calendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import get_survey_link
from common import Trainers

parser = argparse.ArgumentParser()
parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--create", default=False, action='store_true', help="Create channel")
parser.add_argument("--invites", default=False, action='store_true', help="Invite trainers")
parser.add_argument("--bookmarks", default=False, action='store_true', help="Update bookmarks on channel")
parser.add_argument("--messages", default=False, action='store_true', help="Update scheduled messages on channel")
parser.add_argument("--wipe-messages", default=False, action='store_true', help="Wipe scheduled messages from channel")
parser.add_argument("--list-messages", default=False, action='store_true', help="List scheduled messages from channel")
parser.add_argument("--archive", default=False, action='store_true', help="Archive channel")
parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
args = parser.parse_args()

# read configuration files
config = get_config(args)
trainers = Trainers(config['global']['trainers_db'])

secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
credentials_file = config['google']['credentials_file']
credentials_file_path = os.path.join(secrets_dir, credentials_file)
timezone = config['google.calendar'].get('timezone', config['global']['timezone'])
slack = SlackInterface.SlackInterface(config['slack']['bot_token'])
zoom_user = config['zoom']['user']
zoom = ZoomInterface.ZoomInterface(config['zoom']['account_id'], config['zoom']['client_id'], config['zoom']['client_secret'], config['global']['timezone'], zoom_user)


# get the events from the working calendar in the Google spreadsheets
events = Calendar(config, args).get_all_sessions()

# keep only events on the date listed
if args.date:
    events = [event for event in events if args.date.date().isoformat() in event['start_date']]

for event in events:
    try:
        # no course code, continue
        if not 'code' in event:
            continue

        date = to_iso8061(event['start_date']).date()
        course_code = event['code']
        locale = event['langue']
        title = event['title']

        survey_link = get_survey_link(config, locale, title, date)
        slack_channel_name = eval('f' + repr(config['global']['slack_channel_template']))
        slack_channel_name = slack_channel_name.lower()

        attendees_keys = []
        if event['instructor']: attendees_keys += [event['instructor']]
        if event['host']: attendees_keys += [event['host']]
        if event['assistants']: attendees_keys += event['assistants'].split(',')
        attendees = [trainers.slack_email(key) for key in attendees_keys]
        attendees = list(set(attendees))

        start_time = to_iso8061(event['start_date'])
        end_time = to_iso8061(event['end_date'])
        duration = int(event['hours'])

        webinar = zoom.get_webinars(date = start_time.date())
        if webinar:
            webinar = zoom.get_webinar(webinar_id = webinar[0]['id'])
        description = ''
        if webinar:
            description = f"""
Start URL: {webinar['start_url']}
Join URL: {webinar['join_url']}"""

        original_start_time = start_time
        original_end_time = end_time

        if args.create:
            if args.dry_run:
                cmd = f"slack.create_channel({slack_channel_name})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.create_channel(slack_channel_name)

        if args.invites:
            if args.dry_run:
                cmd = f"slack.invite_to_channel({slack_channel_name}, {attendees})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.invite_to_channel(slack_channel_name, attendees)

        if args.bookmarks:
            bookmarks = [
                {'title': 'Magic Castle', 'link': f'https://{course_code.lower()}.calculquebec.cloud'}
                ]
            if webinar:
                bookmarks += [{'title': 'Zoom URL Participants', 'link': webinar['join_url']}]
            if survey_link:
                bookmarks += [{'title': 'Survey', 'link': survey_link}]

            if args.dry_run:
                cmd = f"slack.update_channel_bookmarks({slack_channel_name}, {bookmarks})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.update_channel_bookmarks(slack_channel_name, bookmarks)


        if args.archive:
            if args.dry_run:
                cmd = f"slack.archive_channel({slack_channel_name})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.archive_channel(slack_channel_name)

        if args.wipe_messages:
            if args.dry_run:
                cmd = f"slack.wipe_channel_scheduled_messages({slack_channel_name})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.wipe_channel_scheduled_messages(slack_channel_name)

        if args.list_messages:
            if args.dry_run:
                cmd = f"slack.list_channel_scheduled_messages({slack_channel_name})"
                print(f"Dry-run: would run {cmd}")
            else:
                print(f"{slack.list_channel_scheduled_messages(slack_channel_name)}")

        if args.messages:
            # events on two days
            if start_time.date() != end_time.date():
                duration = duration/2.

            magic_castle_link = slack.get_channel_bookmark_link(slack_channel_name, "Magic Castle")
            zoom_user_link = slack.get_channel_bookmark_link(slack_channel_name, "Zoom URL Participants")
            survey_link = slack.get_channel_bookmark_link(slack_channel_name, "Survey")

            message_prefixes = []
            for key in config['slack']:
                key_parts = key.split('_')
                if len(key_parts) == 3 and key_parts[0] == "message" and key_parts[2] == "template":
                    message_prefixes += ['_'.join(key_parts[0:2])]

            messages = []
            for prefix in message_prefixes:
                text = eval('f' + repr(config['slack'][f'{prefix}_template']))
                for date in set([start_time.date(), end_time.date()]):
                    if date == original_start_time.date():
                        start_time = original_start_time
                        end_time = original_start_time + datetime.timedelta(hours=duration)
                    elif date == original_end_time.date():
                        start_time = original_end_time - datetime.timedelta(hours=duration)
                        end_time = original_end_time

                    if date == original_start_time.date() or config['slack'][f'{prefix}_multidays'] == "True":
                        time = start_time
                        if f'{prefix}_offset_start' in config['slack']:
                            time = start_time + datetime.timedelta(minutes=int(config['slack'][f'{prefix}_offset_start']))
                        elif f'{prefix}_offset_end' in config['slack']:
                            time = end_time + datetime.timedelta(minutes=int(config['slack'][f'{prefix}_offset_end']))
                        elif f'{prefix}_offset_now' in config['slack']:
                            time = datetime.datetime.now() + datetime.timedelta(minutes=int(config['slack'][f'{prefix}_offset_now']))

                        messages += [{'time': time, 'message': text}]

            for message in messages:
                if args.dry_run:
                    cmd = f"slack.post_to_channel({slack_channel_name}, {message['message']}, {message['time']})"
                    print(f"Dry-run: would run {cmd}")
                else:
                    slack.post_to_channel(slack_channel_name, message['message'], message['time'])



    except Exception as e:
        print(f"Error encountered when processing event {event}: \n\n{e}")



