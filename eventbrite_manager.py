import argparse
import yaml
from datetime import datetime, timedelta, timezone
import os
import re
from git import Repo
from bs4 import BeautifulSoup
import configparser
from glob import glob
#import interfaces.zoom.ZoomInterface as ZoomInterface
import interfaces.eventbrite.EventbriteInterface as eventbrite
from common import UTC_FMT, valid_date, to_iso8061, ISO_8061_FORMAT, Trainers, get_config
import CQORCcalendar


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
    if desc:
        desc.string = desc.string.replace("[[DESCRIPTION]]", content["description"])

    if prerequis:
        new_prereqs = soup.new_tag("ul")
        for i in content["prerequisites"]:
            new_li = soup.new_tag("li")
            new_li.string = i
            new_prereqs.append(new_li)
        prerequis.replace_with(new_prereqs)

    if plan:
        new_plan = soup.new_tag("ul")
        for i in content["plan"]:
            new_li = soup.new_tag("li")
            new_li.string = i
            new_plan.append(new_li)
        plan.replace_with(new_plan)

    # Update instructor
    if instructor:
        instructor.string = instructor.string.replace("[[INSTRUCTOR]]", instructor_name)

    return soup

if __name__ == "__main__":

    config = configparser.ConfigParser()

    parser = argparse.ArgumentParser(description="Create a new event from a template.")

    parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
    parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
    parser.add_argument("--date", metavar=ISO_8061_FORMAT, type=valid_date, help="Generate for the first event on this date")
    parser.add_argument("--course_id", help="Handle course specified by course_id")
    parser.add_argument("--dry-run", default=False, action='store_true', help="Dry-run")
    parser.add_argument("--create", default=False, action='store_true', help="Create event")
    parser.add_argument("--update", default=False, action='store_true', help="Update event")
    parser.add_argument("--delete", default=False, action='store_true', help="Delete event")

    args = parser.parse_args()
    print(vars(args))

    config = get_config(args)
    trainers = Trainers(config['global']['trainers_db'])
    #zoom_user = config['zoom']['user']
    #zoom = ZoomInterface.ZoomInterface(config['zoom']['account_id'], config['zoom']['client_id'], config['zoom']['client_secret'], config['global']['timezone'], zoom_user)

    # no need to actualize the repo if we are not creating or updating the event
    if args.create or args.update:
        actualize_repo(config["descriptions"]["repo_url"], config["descriptions"]["local_repo"])
    eb = eventbrite.EventbriteInterface(config["eventbrite"]["api_key"])

    # get the courses from the working calendar in the Google spreadsheets
    calendar = CQORCcalendar.Calendar(config, args)
    courses = calendar.get_courses()

    # keep only courses that start on the date listed
    if args.date:
        courses = [courses for course in courses if args.date.date().isoformat() in course['sessions'][0]['start_date']]
    # keep only the course for the course_id specified
    if args.course_id:
        courses = [calendar[args.course_id]]

    for course in courses:
        first_session = course['sessions'][0]
        instructor = ','.join([trainers.fullname(session['instructor']) for session in course['sessions']])

        if first_session['code']:
            # Read the description from the repo
            with open(os.path.join(config["descriptions"]["local_repo"], f"{first_session['code']}-{first_session['language']}.yaml")) as f:
                event_description = yaml.safe_load(f)
        else:
            event_description = None
            print("Empty workshop code, skipping updating description")

        # Create the event
        if args.create:
            # for multi-session courses, the duration of the webinar must be from the start to the end
            start_date = min([to_iso8061(session['start_date']) for session in course['sessions']])
            end_date = max([to_iso8061(session['end_date']) for session in course['sessions']])

            eventid = eb.create_event_from(
                event_id=first_session['template'],
                title=first_session['title'],
                start_date=start_date,
                end_date=end_date,
                tz=config["global"]["timezone"],
                summary=event_description["summary"] if event_description else "",
            )
            calendar.set_eventbrite_id(first_session['course_id'], eventid)
            print(f"Successfully created {first_session['title']}({eventid}) {start_date} {end_date}")
        else:
            eventid = first_session['eventbrite_id']


        # Update the event
        if args.update or args.create:
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
            eb.update_tickets(eventid, "", (to_iso8061(first_session['start_date']) - timedelta(hours=hours)).astimezone(timezone.utc).strftime(UTC_FMT))
            print(f'Successfully updated {eventid} ticket classes')

            # Update Zoom webinar
            # Note: This merely creates a generic webinar, not a Zoom connection
#            if first_session['zoom_id']:
#                webinar = zoom.get_webinar(first_session['zoom_id'])
#                eb.update_webinar_url(eventid, webinar['join_url'])

        # Delete the event
        if args.delete:
            eb.delete_event(eventid)
            calendar.set_eventbrite_id(first_session['course_id'], '')
            print(f'Successfully deleted {eventid}')

    calendar.update_spreadsheet()
