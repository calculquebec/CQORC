from datetime import datetime
import interfaces.google.GSheetsInterface as GSheetsInterface
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
        try:
            date = datetime.fromisoformat(dt).astimezone(tz)
        except:
            date = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S').astimezone(tz)
        return date

def valid_date(d):
    """ Validate date is in ISO 8061 format, otherwise raise. """
    try:
        return to_iso8061(d)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid ISO 8061 date value: {d!r}.")


def get_config(args, debug_level:int=0):
    '''Read all configuration files (*.cfg) from configuration directories

    Arguments:
        args -- An argparse.Namespace object or any object with at least two
                default directories as attributes:
            .config_dir -- String. It is used if CQORC_CONFIG_DIR is not set
            .secrets_dir -- String. It is used if CQORC_SECRETS_DIR is not set
        debug_level -- Integer <= 2
            If 0 (default), quiet mode
            If 1, print the list of configuration files (all *.cfg)
            If 2, print all the above, plus configuration section names

    Returns: a ConfigParser object with parsed configurations from *.cfg files
    '''

    config_dir = os.environ.get('CQORC_CONFIG_DIR', args.config_dir)
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)

    config_files = \
        glob.glob(os.path.join(config_dir, '*.cfg')) + \
        glob.glob(os.path.join(secrets_dir, '*.cfg'))
    if debug_level >=1:
        print('Reading config files:\n-', '\n- '.join(config_files))

    global_config = configparser.ConfigParser()
    global_config.read(config_files)
    if debug_level >= 2:
        print('Config sections:\n-', '\n- '.join(global_config.sections()))

    return global_config


def extract_course_code_from_title(config, title):
    return eval('f' + repr(config['global']['course_code_template']))

def get_events_from_sheet_calendar(global_config, args):
    # take the credentials file either from google section
    credentials_file = global_config['google']['credentials_file']
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
    credentials_file_path = os.path.join(secrets_dir, credentials_file)

    # initialize the Google Drive interface
    gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)

    list_of_events = gsheets.get_values(global_config['google']['calendar_file'], "A:Z", global_config['google']['calendar_sheet_name'])
    header = list_of_events[0]
    dict_of_events = [{header[i]: item[i] if i < len(item) else None for i in range(len(header))} for item in list_of_events[1:]]
    return dict_of_events


class Trainers:
    def __init__(self, file_name):
        with open(file_name, 'r') as file:
            self._trainers = yaml.safe_load(file)

    def __getitem__(self, key):
        return self._trainers[key]

    def trainers(self):
        return self._trainers.keys()

    def email(self, key):
        return self._trainers[key]['email']

    def emails(self):
        return [self.email(k) for k in self.trainers()]

    def all_emails(self):
        return set([self.email(k) for k in self.trainers()] +
                   [self.zoom_email(k) for k in self.trainers()] +
                   [self.slack_email(k) for k in self.trainers()] +
                   [self.calendar_email(k) for k in self.trainers()])

    def zoom_email(self, key):
        return self._trainers[key].get('zoom_email', self.email(key))

    def slack_email(self, key):
        return self._trainers[key].get('slack_email', self.email(key))

    def calendar_email(self, key):
        return self._trainers[key].get('calendar_email', self.email(key))

    def home_institution(self, key):
        return self._trainers[key]['home_institution']

    def fullname(self, keys):
        return "%s %s" % (self.firstname(key), self.lastname(key))

    def firstname(self, keys):
        return self._trainers[key]['firstname']

    def lastname(self, keys):
        return self._trainers[key]['lastname']


