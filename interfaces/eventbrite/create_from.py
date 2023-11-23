#!/bin/env python3

from datetime import datetime, timedelta, timezone
import re, os, json, yaml, argparse
from git import Repo
from bs4 import BeautifulSoup
import EventbriteInterface as Eventbrite
from pprint import pprint
from configparser import ConfigParser


def to_iso8061(dt, tz=None):
    """
    Returns full long ISO 8061 datetime with timezone.

    eg:
        '2018-09-12' -> '2018-09-12T00:00:00-04:00'
        '2018-09-12T00:00:00+00:30' -> '2018-09-11T19:30:00-04:00'
    """
    if isinstance(dt, datetime):
        return dt.astimezone(tz)
    else:
        return datetime.fromisoformat(dt).astimezone(tz)


def valid_date(d):
    """ Validate date is in ISO 8061 format, otherwise raise. """
    try:
        return to_iso8061(d)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid ISO 8061 date value: {d!r}.")


def actualize_repo(url, local_repo='./descs'):
    repo = Repo(local_repo) if os.path.exists(local_repo) else Repo.clone_from(url, local_repo)
    # pull in latest changes if any, expects remote to be named `origin`
    repo.remotes.origin.pull()


def update_html(description, content, instructor):
    soup = BeautifulSoup(description, 'html.parser')

    # Find elements!
    summary = soup.find("div", string="[[SUMMARY]]")
    desc = soup.find("p", string="[[DESCRIPTION]]")
    prerequis = soup.find("p", string="[[PREREQS]]")
    plan = soup.find("p", string="[[PLAN]]")
    instructor = soup.find("p", string=re.compile('\\[\\[INSTRUCTOR\\]\\]'))

    # Update them
    summary.string = summary.string.replace("[[SUMMARY]]", content['summary'])
    desc.string = desc.string.replace("[[DESCRIPTION]]", content['description'])

    new_prereqs = soup.new_tag("ul")
    for i in content['prerequisites']:
        new_li = soup.new_tag("li")
        new_li.string = i
        new_prereqs.append(new_li)
    prerequis.replace_with(new_prereqs)

    new_plan = soup.new_tag("ul")
    for i in content['plan']:
        new_li = soup.new_tag("li")
        new_li.string = i
        new_plan.append(new_li)
    plan.replace_with(new_plan)

    # Update instructor
    instructor.string = instructor.string.replace("[[INSTRUCTOR]]", instructor)

    return soup


config = configparser.ConfigParser()

parser = argparse.ArgumentParser()

parser.add_argument('--from-template', type=int, required=True)
parser.add_argument('--title', required=True)
parser.add_argument("--start-date", metavar=ISO_8061_FORMAT, required=True, type=valid_date, help="Start datetime in ISO 8601.")
parser.add_argument("--end-date", metavar=ISO_8061_FORMAT, required=True, type=valid_date, help="End datetime in ISO 8601.")
parser.add_argument("--config", metavar="CFG_FILE", default="eventbrite.cfg", help="Configuration file name")

args = parser.parse_args()

config.read([os.environ.get('EVENTBRITE_SECRETS', '../secrets.cfg'), args.config])

eb = Eventbrite(config['api_key'])

# actualize_repo(url="git@github.com:calculquebec/eventbrite_descriptions.git")

# with open('.descs/README.md') as f:
#     print(f.readlines())
