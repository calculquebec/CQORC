#!/bin/env python3
import os, argparse, itertools
from datetime import datetime, timedelta, date
import pytz
import requests
import configparser


parser = argparse.ArgumentParser()
parser.add_argument("--calendar_id", help="Calendar ID to use")
parser.add_argument("--course", help="Search for event with corresponding course code in the title")
parser.add_argument("--delay", help="How many minutes in advance to check")
parser.add_argument("--apikey", help="Google API key to use to query calendar")
parser.add_argument("--config", help="Config file that contains secrets")
args = parser.parse_args()


if args.config:
    config = configparser.ConfigParser()
    config.read(args.config)
    calendar_id = args.calendar_id or config['DEFAULT']['calendar_id']
    apikey = args.apikey or config['DEFAULT']['apikey']
    course = args.course or config['DEFAULT']['course']
    course = course.lower()
    timezone = config['DEFAULT']['timezone'] or "America/Montreal"

tzinfo = pytz.timezone(timezone)


start_time = datetime.now()
end_time = start_time + timedelta(minutes = int(args.delay))
if start_time.tzinfo is None:
    start_time = tzinfo.localize(start_time).astimezone(pytz.utc)
    end_time = tzinfo.localize(end_time).astimezone(pytz.utc)

params = {
    'key': apikey,
    'timeMin': start_time.isoformat(),
    'timeMax': end_time.isoformat(),
    'maxResults': '10',
    'singleEvents': 'true',
    'orderBy': 'startTime',
    'alt': 'json',
}

response = requests.get(
    f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events',
    params=params,
)

events = response.json()['items']
for event in events:
    if course in event['summary'].lower():
        event_start_time = datetime.fromisoformat(event['start']['dateTime'])
        if start_time < event_start_time and event_start_time < end_time:
            exit(True)

exit(False)

