#!/bin/env python3

import argparse
import cairosvg
import unidecode
import os
import jinja2
import yaml
import getpass
import smtplib

from datetime import datetime
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import interfaces.eventbrite.EventbriteInterface as Eventbrite

from common import get_config
from common import to_iso8061

ATTESTATION_CQ_TEMPLATE = "Attestation_CQ_{}_{}_{}.pdf"


"""
Usage:

python3 create_certificate.py --event_id 778466443087
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
        

    # Set template name:
    for file in os.listdir(certificate_svg_tplt_dir):
        if file == f"attestation_template_sample_{language}_logo.svg":
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
        date = datetime.strptime(event['start']['local'], "%Y-%m-%dT%H:%M:%S")
        date = date.strftime("%Y-%m-%d")


    # Set language:
    if not language:
        language = event['locale'].split("_")[0]
        

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

    filename_template = os.path.join(certificate_dir,  ATTESTATION_CQ_TEMPLATE)

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

def create_email(gmail_user, guest, email_tplt, send_self, self_email, attach_certificate=True):
    """
    Create email, attatch body and PDF certificate

    Parameters
    ----------
    gmail_user : str
        Gmail username

    guest : dict
        Attendees that participated, that is that have their status to `checked in` or `attended`.
        get_event_attendees_present(eb_event['id'], fields = ['title', 'email', 'first_name', 'last_name', 'status', 'name', 'order_id'])

    email_tplt : dict
        Ditionnary with email template.

    send_self : bool
        Send to yourself.

    self_email: str
        Email to send tests to
    
    attach_certificate : bool
        If we want certificate to be attached to the email.

    """
    # Create email
    outer = MIMEMultipart()
    outer['From'] = gmail_user
    if send_self:
        if self_email:
            outer['To'] = self_email
        else:
            outer['To'] = gmail_user
    else:
        outer['To'] = guest['email']
    outer['Reply-to'] = email_tplt['replyto']
    
    outer['Subject'] = Header(email_tplt['subject'])

    # Attach body
    body = MIMEText(email_tplt['message'].format(**guest), 'plain')
    outer.attach(body)

    # Attach PDF Certificate
    if attach_certificate:
        msg = MIMEBase('application', "octet-stream")
        with open(guest['filename'], 'rb') as file_:
            msg.set_payload(file_.read())
        encoders.encode_base64(msg)
        msg.add_header('Content-Disposition', 'attachment', filename=os.path.basename(guest['filename']))
        outer.attach(msg)

    return outer


def send_email(event, guests, email_tplt_dir, send_self, number_to_send, language, gmail_user=None, gmail_password=None, self_email=None, attach_certificate=True):
    """
    Create email, attatch body and PDF certificate

    Parameters
    ----------
    event : str
        EventBrite event id

    guests : dict
        Get information for attendees that participated, that is that have their status to `checked in` or `attended`.
        get_event_attendees_present(eb_event['id'], fields = ['title', 'email', 'first_name', 'last_name', 'status', 'name', 'order_id'])  

    email_tplt_dir : directory
        Directory containing email template in french and english.

    send_self : bool
        Send to yourself.

    number_to_send : int
        Number of certificate to send.

    language : str
        Event language. en = english ; fr = french

    gmail_user : str
        Gmail username

    gmail_password : str
        Gmail password
    
    self_email : str
        Email to use if sending to self.

    attach_certificate : bool
        Parameter to attach or not the certificate to the email.

    """

    if not language:
        language = event['locale'].split("_")[0]
    
    for file in os.listdir(email_tplt_dir):
        if file == f"email_certificates_{language}.yml":
            email_tplt_file = email_tplt_dir + "/" + file


    email_tplt = {}

    with open(email_tplt_file, 'rt', encoding='utf8') as f:
        email_tplt = yaml.load(f, Loader=yaml.FullLoader)

    if not gmail_user:
        gmail_user = input('gmail username: ')
    if not gmail_password:
        gmail_password = getpass.getpass('gmail password: ')
    if not self_email:
        self_email = gmail_user

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, gmail_password)
        nsent = 0

        for guest in guests:
                email = create_email(gmail_user, guest, email_tplt, args.send_self, args.self_email, attach_certificate)

                # Send email
                if send_self:
                    print('sending email to YOU about: {first_name} ({email})...'.format(**guest))
                else:
                    print('sending email to: {first_name} {last_name} ({email})...'.format(**guest))

                try:
                    server.sendmail(email['From'], email['To'], email.as_string())
                except smtplib.SMTPAuthenticationError as e:
                    # If the GMail account is now allowing secure apps, the script will fail.
                    # read : http://stackabuse.com/how-to-send-emails-with-gmail-using-python/
                    print('Go to https://myaccount.google.com/lesssecureapps and Allow less secure apps.')
                    sys.exit(1)
                nsent = nsent + 1
                if nsent == number_to_send:
                    break
    

if __name__ == '__main__':


    parser = argparse.ArgumentParser()
    parser.add_argument("--config_dir", default=".", help="Directory that holds the configuration files")
    parser.add_argument("--secrets_dir", default=".", help="Directory that holds the configuration files")
    parser.add_argument("--title", default=None, help="Event title")
    parser.add_argument("--date", default=None, help="Event date (iso8061) XXXX-XX-XX ; year-month-day")
    parser.add_argument("--duration", default=None, help="Event duration in hour")
    parser.add_argument("--language", default=None, choices=['fr', 'en'],  help="Event language. en = english ; fr = french")
    parser.add_argument("--certificate_dir", default="./certificates", help="Directory to write the certificates.")
    parser.add_argument("--event_id", help="EventBrite event id", required=True)
    parser.add_argument("--certificate_svg_tplt_dir",default="./Attestation_template", help="Directory that holds certificate templates.")
    parser.add_argument("--gmail_user", help="Gmail username", type=str, default=None)
    parser.add_argument("--gmail_password", help="Gmail password", type=str, default=None)
    parser.add_argument("--email_tplt_dir", help="Email template directory", default="./email_template")
    parser.add_argument("--send_self", default=False, help="Send to yourself", action="store_true")
    parser.add_argument("--send_atnd", default=False, help="Send the certificate to each attendee", action="store_true")
    parser.add_argument("--self_email", help="Email to send tests to", type=str, default=None)
    parser.add_argument('--number_to_send', help="Total number of certificates to send", type=int, default=-1)
    args = parser.parse_args()


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

    # Get email config:
    self_email = global_config['email']['self_email']
    gmail_user = global_config['email']['gmail_user']
    gmail_password = global_config['email']['gmail_password']

    # Create email:
    if args.send_atnd or args.send_self:
        send_email(eb_event, attended_guest, args.email_tplt_dir, args.send_self, args.number_to_send, args.language, gmail_user=gmail_user, gmail_password=gmail_password, self_email=self_email, attach_certificate=True)

