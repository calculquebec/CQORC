import argparse
import yaml
from datetime import datetime, timedelta, timezone
import os
import re
from git import Repo
from bs4 import BeautifulSoup
import configparser
from glob import glob
import interfaces.eventbrite.EventbriteInterface as eventbrite
from common import UTC_FMT, valid_date, to_iso8061, Trainers


def actualize_repo(url, local_repo):
    """
    Clones or pulls the repo at `url` to `local_repo`.
    """
    repo = (
        Repo(local_repo)
        if os.path.exists(local_repo)
        else Repo.clone_from(url, local_repo)
    )
    # pull in latest changes if any, expects remote to be named `origin`
    repo.remotes.origin.pull()


def update_html(description, content, instructor_name):
    """
    Updates the HTML description with the content and instructor.

    The HTML description is a template with the following tags:
        [[SUMMARY]]
        [[DESCRIPTION]]
        [[PREREQS]]
        [[PLAN]]
        [[INSTRUCTOR]]

    The content is a dictionary with the following keys:
        summary
        description
        prerequisites
        plan
    """
    soup = BeautifulSoup(description, "html.parser")

    # Find elements!

    # Remove the summary which is not used
    summary = soup.select_one("div")
    summary.decompose()

    desc = soup.find("p", string="[[DESCRIPTION]]")
    prerequis = soup.find("p", string="[[PREREQS]]")
    plan = soup.find("p", string="[[PLAN]]")
    instructor = soup.find("p", string=re.compile("\\[\\[INSTRUCTOR\\]\\]"))

    # Update them
    # summary.string = summary.string.replace("[[SUMMARY]]", content["summary"])
    desc.string = desc.string.replace("[[DESCRIPTION]]", content["description"])

    new_prereqs = soup.new_tag("ul")
    for i in content["prerequisites"]:
        new_li = soup.new_tag("li")
        new_li.string = i
        new_prereqs.append(new_li)
    prerequis.replace_with(new_prereqs)

    new_plan = soup.new_tag("ul")
    for i in content["plan"]:
        new_li = soup.new_tag("li")
        new_li.string = i
        new_plan.append(new_li)
    plan.replace_with(new_plan)

    # Update instructor
    instructor.string = instructor.string.replace("[[INSTRUCTOR]]", instructor_name)

    return soup


def get_default_config():
    """
    Returns the default configuration file path.

    Reads from the environment variable EVENTBRITE_CFG_FILE, or defaults to
    the file `eventbrite.cfg` in the current working directory, or specified by CQORC_CONFIG_DIR environment variable.
    """
    return os.environ.get(
        "EVENTBRITE_CFG_FILE",
        os.path.join(os.environ.get("CQORC_CONFIG_DIR", "."), "*.cfg"),
    )


def get_default_secrets():
    """
    Returns the default secrets file path.

    Reads from the environment variable EVENTBRITE_SECRET_FILE, or defaults to
    the file `secrets.cfg` in the current working directory, or specified by CQORC_SECRET_DIR environment variable.
    """
    return os.environ.get(
        "EVENTBRITE_SECRET_FILE",
        os.path.join(os.environ.get("CQORC_SECRET_DIR", "."), "*.cfg"),
    )


if __name__ == "__main__":

    config = configparser.ConfigParser()

    parser = argparse.ArgumentParser(description="Create a new event from a template.")

    parser.add_argument("--config", metavar="CFG_FILE", default=get_default_config(), help="Configuration file name")
    parser.add_argument("--secret", metavar="SECRET_FILE", default=get_default_secrets(), help="Secrets file name")

    subparsers = parser.add_subparsers(help="sub-command help")

    event_parser = subparsers.add_parser("event", help="Create a new event from a template.")
    event_parser.add_argument("--template", type=int, required=True)
    event_parser.add_argument("--title", required=True)
    event_parser.add_argument("--start-date", metavar="YYYY-MM-DD HH:MM", required=True, type=valid_date, help="Start datetime",)
    event_parser.add_argument("--end-date", metavar="YYYY-MM-DD HH:MM", required=True, type=valid_date, help="End datetime",)
    event_parser.add_argument("--language", required=True, help="Workshop language")
    event_parser.add_argument("--instructor", required=True, help="Instructor for the workshop")
    event_parser.add_argument("--duration", required=True, type=float, default=3.0, help="Duration of the workshop in hours")
    event_parser.add_argument("--workshop-code", required=True, help="ID for the workshop")

    events_parser = subparsers.add_parser("events", help="Create events from a calendar.")
    events_parser.add_argument("files", metavar="FILE", nargs="+", type=argparse.FileType("r"), help="files to read")

    args = parser.parse_args()
    print(vars(args))

    config.read([args.secret, args.config])

    actualize_repo(config["descriptions"]["repo_url"], config["descriptions"]["local_repo"])

    eb = eventbrite.EventbriteInterface(config["eventbrite"]["api_key"])

    instructor = Trainers(config['global']["trainers_db"]).fullname(args.instructor)

    if len(args.workshop_code):
        # Read the description from the repo
        with open(os.path.join(config["descriptions"]["local_repo"], f"{args.workshop_code}-{args.language}.yaml")) as f:
            event_description = yaml.safe_load(f)
    else:
        event_description = None
        print("Empty workshop code, skipping updating description")

    # Create the event
    eventid = eb.create_event_from(
        event_id=args.template,
        title=args.title,
        start_date=args.start_date,
        end_date=args.end_date,
        tz=config["global"]["timezone"],
        summary=event_description["summary"] if event_description else "",
    )
    print(f'Successfully created {args.title}({eventid}) {args.start_date} {args.end_date}')

    if event_description:
        # Update the description
        eb.update_event_description(eventid, str(update_html(
            eb.get_event_description(eventid)['description'],
            event_description,
            instructor,
        )))
        print(f'Successfully updated {eventid} description')

    # Update tickets classes
    hours = int(config["eventbrite"]["close_hours_before_event"])
    eb.update_tickets(eventid, "", (args.start_date - timedelta(hours=hours)).astimezone(timezone.utc).strftime(UTC_FMT))
    print(f'Successfully updated {eventid} ticket classes')
