#!/bin/env python3
import os, argparse, datetime

import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.slack.SlackInterface as SlackInterface
import CQORCcalendar

from common import valid_date, to_iso8061, ISO_8061_FORMAT, get_config
from common import extract_course_code_from_title
from common import get_survey_link
from common import get_trainer_keys
from common import Trainers

parser = argparse.ArgumentParser()
parser.add_argument("--course_id", default=None, help="Manage only for this course id")
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default="./secrets", help="Directory that holds the configuration files")
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
calendar = CQORCcalendar.Calendar(config, args)

# function to add the @ sign and <> to the user_id of the analyst before to post in slack.
def format_tag(analysts):
    tag = [f"<@{user_id.strip()}>" for user_id in analysts]
    return (
    tag[0] if len(tag) == 1 else
    " et ".join(tag) if len(tag) == 2 else
    ", ".join(tag[:-1]) + " et " + tag[-1]
    )

# keep only events on the date listed
if args.course_id:
    if args.course_id in calendar.keys():
        courses = [calendar[args.course_id]]
    else:
        print(f"Course {args.course_id} not found")
        exit(1)
else:
    courses = calendar.get_courses()

for course in courses:
    try:
        first_session = course['sessions'][0]

        # no course code, continue
        if not 'code' in first_session:
            continue

        date = to_iso8061(first_session['start_date']).date()
        course_code = first_session['code']
        locale = first_session['language']
        title = first_session['title']

        survey_link = get_survey_link(config, locale, title, date)

        post_mortem_link = config['slack']['post_mortem_link']

        # if is documented, use that, otherwise create it
        slack_channel_name = first_session['slack_channel']
        if not slack_channel_name:
            slack_channel_name = eval('f' + repr(config['global']['slack_channel_template']))
            slack_channel_name = slack_channel_name.lower()

        if args.create:
            if args.dry_run:
                cmd = f"slack.create_channel({slack_channel_name})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.create_channel(slack_channel_name)
                calendar.set_slack_channel(first_session['course_id'], slack_channel_name)

        if args.invites:
            attendees = [trainers.slack_email(key) for key in get_trainer_keys(course, ['instructor', 'host', 'assistants', 'equipe_techno'])]
            if args.dry_run:
                cmd = f"slack.invite_to_channel({slack_channel_name}, {attendees})"
                print(f"Dry-run: would run {cmd}")
            else:
                slack.invite_to_channel(slack_channel_name, attendees)

        if args.bookmarks:
            if first_session['zoom_id']:
                webinar = zoom.get_webinar(webinar_id = first_session['zoom_id'])
            else:
                start_time = to_iso8061(first_session['start_date'])
                webinar = zoom.get_webinars(date = start_time.date())
                if webinar:
                    webinar = zoom.get_webinar(webinar_id = webinar[0]['id'])

            bookmarks = [
                {'title': 'Magic Castle', 'link': f'https://{course_code.lower()}.calculquebec.cloud'}
                ]
            if webinar:
                bookmarks += [{'title': 'Zoom URL Participants', 'link': webinar['join_url']}]
            if survey_link:
                bookmarks += [{'title': 'Survey', 'link': survey_link}]
            if post_mortem_link:
                bookmarks += [{'title': 'Post Mortem des formations', 'link': post_mortem_link}]

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
            magic_castle_link = slack.get_channel_bookmark_link(slack_channel_name, "Magic Castle")
            zoom_user_link = slack.get_channel_bookmark_link(slack_channel_name, "Zoom URL Participants")
            survey_link = slack.get_channel_bookmark_link(slack_channel_name, "Survey")
            message_prefixes = []
            for key in config['slack']:
                key_parts = key.split('_')
                if len(key_parts) == 3 and key_parts[0] == "message" and key_parts[2] == "template":
                    message_prefixes += ['_'.join(key_parts[0:2])]

            messages = []
            equipe_techno_email = [trainers.slack_email(key.split()[0]) for key in get_trainer_keys(course, ['equipe_techno'])]
            equipe_techno_id_list = []
        
            for email in equipe_techno_email:
                equipe_techno_id = ''.join(slack.get_user_id(email, next_cursor=None))
                equipe_techno_id_list.append(equipe_techno_id)

            analysts_tagged = format_tag(equipe_techno_id_list)

            for prefix in message_prefixes:
                # Evalutate text message
                text = eval('f' + repr(config['slack'][f'{prefix}_template']))

                for session in course['sessions']:
                    # Evaluate the condition
                    if f'{prefix}_condition' in config['slack']:
                        if not eval(config['slack'][f'{prefix}_condition']):
                            continue

                    start_time = to_iso8061(session['start_date'])
                    end_time = to_iso8061(session['end_date'])

                    if start_time == to_iso8061(first_session['start_date']) or config['slack'][f'{prefix}_multidays'] == "True":
                        time = start_time
                        # Applying offsets
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
        print(f"Error encountered when processing course {course}: \n\n{e}")


if not args.dry_run:
    calendar.update_spreadsheet()


