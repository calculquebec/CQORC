from datetime import datetime
import argparse, configparser, os, glob
import yaml
ISO_8061_FORMAT = "YYYY-MM-DD[THH:MM:SS[±HH:MM]]"

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

def get_config(args):
    global_config = configparser.ConfigParser()
    config_dir = os.environ.get('CQORC_CONFIG_DIR', args.config_dir)
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
    config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
    global_config.read(config_files)
    return global_config

def extract_course_code_from_title(config, title):
    return eval('f' + repr(config['global']['course_code_template']))


class Trainers:
    def __init__(file_name):
        with open(file_name, 'r') as file:
            self.trainers = yaml.safe_load(file)

    def __getitem__(self, key):
        return self.trainers[key]

    def zoom_email(self, key):
        return self.trainers[key].get('zoom_email', self.trainers[key]['email'])

    def slack_email(self, key):
        return self.trainers[key].get('slack_email', self.trainers[key]['email'])

    def calendar_email(self, key)
        return self.trainers[key].get('calendar_email', self.trainers[key]['email'])

    def home_institution(self, key):
        return self.trainers[key]['home_institution']

    def fullname(self, keys):
        return "%s %s" % (self.firstname(key), self.lastname(keyÉ))

    def firstname(self, keys):
        return self.trainers[key]['firstname']

    def lastname(self, keys):
        return self.trainers[key]['lastname']


