#!/bin/env python3

import argparse
import cairosvg
import unidecode
import os
import jinja2
import click
from datetime import datetime
import interfaces.eventbrite.EventbriteInterface as Eventbrite

from common import get_config
from common import to_iso8061

parser = argparse.ArgumentParser()
parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
parser.add_argument("--title", default=None, help="Event title")
parser.add_argument("--date", default=None, help="Event date (iso8061) XXXX-XX-XX ; year-month-day")
parser.add_argument("--duration", default=None, help="Event duration in hour")
parser.add_argument("--language", default=None, help="Event language. en = english ; fr = french")
parser.add_argument("--certificate_dir", default="./certificates", help="Directory to write the certificates.")
parser.add_argument("event_id", help="EventBrite event id")
parser.add_argument("--certificate_svg_tplt_dir",default="./Attestation_template", help="Directory that holds certificate templates.")
args = parser.parse_args()

"""
Usage:

python3 create_certificate.py 778466443087
"""

def write_certificates(event, guests, certificate_svg_tplt_dir, language, certificate_dir):
    """
    Generates one PDF per attendee
    
    Parameters
    ----------
    event : str 
        EventBrite event id

    guests : dict
        Get information for attendees that participated, that is that have their status to `checked in` or `attended`.
        get_event_attendees_present(eb_event['id'], fields = ['title', 'email', 'first_name', 'last_name', 'status', 'name', 'order_id'])

    certificate_svg_tplt_dir : directory
        Directory that contain the template for the french and english certificate.

    language : str
        Event language. en = english ; fr = french

    certificate_dir : directory
        Directory to write the certificates.

    Returns
    -------
    One certificate for each participant in french or english depending on the event language.

    """
    print("--- Generating PDFs ---")
    try:
        os.mkdir(certificate_dir)
    except OSError:
        pass

    # Set language:
    if not language:
        language = event['locale'].split("_")[0]
        
    elif ((language != "en") and (language != "fr")):
        print("write_certificates: We do not support other languages than French and English to create a certificate.")
        exit(1)

    # Set template name:
    if language == "en":
        for file in os.listdir(certificate_svg_tplt_dir):
            if file == "attestation_template_sample_english_logo.svg":
                tpl_name = file
    elif language == "fr":
        for file in os.listdir(certificate_svg_tplt_dir):
            if file == "attestation_template_sample_french_logo.svg":
                tpl_name = file
    
    tpl = jinja2.Environment(loader=jinja2.FileSystemLoader(certificate_svg_tplt_dir)).get_template(tpl_name)

    for guest in guests:
        print(f"Generating: {guest['filename']}")
        cairosvg.svg2pdf(bytestring=tpl.render(guest).encode('utf-8'), 
                         write_to=guest['filename'])

def safe_filename(filename):
    rules = {"!" : ".",
             "@" : "_at_",
             "#" : "_no_",
             "$" : "S",
             "%" : "_per_",
             "?" : ".",
             "&" : "_and_",
             "+" : "_and_",
             "*" : "_",
             "~" : "_in_",
             ";" : ".",
             ":" : ".",
             "," : ".",
             "/" : "-",
             "|" : "-",
             "\\": "-",
             " " : "_",
             "'" : "_",
             '"' : "_"    }

    filename = unidecode.unidecode(filename)

    for old, new in rules.items():
        filename = filename.replace(old, new)

    return filename.upper()

def safe_name(name):
    rules = {"&" : " and ",
             "\\": "/"    }

    for old, new in rules.items():
        name = name.replace(old, new)

    return name.upper()

def build_registrant_list(event, guests, title, duration, date, language, certificate_dir):
    """
    Generate a registration list.    

    Parameters
    ----------
    event : str
        EventBrite event id
    
    guests : dict
        Get information for attendees that participated, that is that have their status to `checked in` or `attended`.
        get_event_attendees_present(eb_event['id'], fields = ['title', 'email', 'first_name', 'last_name', 'status', 'name', 'order_id'])  

    title : str
        Event title

    duration : float
        Event duration in hour

    date : date
        Event date (iso8061) XXXX-XX-XX ; year-month-day

    language : str
        Event language. en = english ; fr = french

    certificate_dir : directory
        Directory to write the certificates.
    
    ----------
    Returns - Python dictionary with formatted attendees information
    """
  
    # Set title:
    if not title:
        title = event['name']['text'].strip()

    # Set duration:
    if not duration:
        time_start = datetime.strptime(event['start']['local'], '%Y-%m-%dT%H:%M:%S')
        time_end   = datetime.strptime(event['end']['local'], '%Y-%m-%dT%H:%M:%S')
        duration = (time_end - time_start).total_seconds() / 3600

    # Set date:
    if not date:
        date = to_iso8061(event['start']['local']).date()

    # Set language:
    if not language:
        language = event['locale'].split("_")[0]
        
    elif ((language != "en") and (language != "fr")):
        print("build_registrant_list: write_certificates: We do not support other languages than French and English to create a certificate.")
        exit(1)
    
    # Set filename_template:
    filename_template = str(certificate_dir) + "/Attestation_CQ_{}_{}_{}.pdf"

    # Complete duration with the right term for time spelling:
    if language == "en":
        if duration <= 1.0:
            duration = str(duration) + " hour."
        else:
            duration = str(duration) + " hours."

    elif language == "fr":
        if duration <= 1.0:
            duration = str(duration) + " heure."
        else:
            duration = str(duration) + " heures."

    attended_guests = []

    for guest in guests:

        first_name = guests[guest]['first_name']
        last_name = guests[guest]['last_name']
        email = guests[guest]['email']
        order_id = guests[guest]['order_id']
        context = {'workshop' : title, 
                   'first_name' : safe_name(first_name),
                   'last_name'  : safe_name(last_name),
                   'email' : email,
                   'date' : date,
                   'duration' : duration,
                   'order_id' : order_id,
                   'filename' : filename_template.format(safe_filename(first_name),
                                                         safe_filename(last_name),
                                                         order_id)     
        }
        attended_guests.append(context)
   
    return attended_guests


# Read configuration files:
global_config = get_config(args)

# Initialize EventBrite interface:
eb = Eventbrite.EventbriteInterface(global_config['eventbrite']['api_key'])

# Get event information:
eb_event = eb.get_event(args.event_id)

# Get information for attendees that participated, that is that have their status to `checked in` or `attended`:
eb_attendees = eb.get_event_attendees_present(eb_event['id'], fields = ['title', 'email', 'first_name', 'last_name', 'status', 'name', 'order_id'])

# Generate a registration list:
attended_guest = build_registrant_list(eb_event, eb_attendees, args.title, args.duration, args.date, args.language, args.certificate_dir)

# Write the certificates:
write_certificates(eb_event, attended_guest, args.certificate_svg_tplt_dir, args.language, args.certificate_dir)
