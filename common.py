from datetime import datetime
import argparse, configparser, os, glob
import urllib
import yaml
from git import Repo

ISO_8061_FORMAT = "YYYY-MM-DD[THH:MM:SS[±HH:MM]]"
UTC_FMT = '%Y-%m-%dT%H:%M:%SZ'


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
            if dt.endswith('Z'):
                dt = dt.replace('Z', '+00:00')
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

def get_trainer_keys(course_or_session, roles):
    if roles is str:
        roles = [roles]

    course = {}
    if 'sessions' in course_or_session.keys():
        course = course_or_session
    else:
        # we received just a session instead of a course dictionary
        # create a fake course that has only one session
        course = {'sessions': [course_or_session]}

    keys = []
    for role in roles:
        for session in course['sessions']:
            if role in session.keys() and session[role]:
                keys += [key.strip() for key in session[role].split(',')]

    return list(set(keys))

def extract_course_code_from_title(config, title):
    return eval('f' + repr(config['global']['course_code_template']))

def get_survey_link(config, locale, title, date):
    survey_template = config['survey'][f"survey_link_template_{locale}"]
    link = eval('f' + repr(survey_template))
    return link

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

class Trainers:
    def __init__(self, file_name):
        with open(file_name, 'r') as file:
            self._trainers = yaml.safe_load(file)

    def __getitem__(self, key):
        key = key.strip()
        return self._trainers[key]

    def trainers(self):
        return self._trainers.keys()

    def email(self, key):
        return self[key]['email']

    def emails(self):
        return [self.email(k) for k in self.trainers()]

    def all_emails(self):
        return set([self.email(k) for k in self.trainers()] +
                   [self.zoom_email(k) for k in self.trainers()] +
                   [self.slack_email(k) for k in self.trainers()] +
                   [self.calendar_email(k) for k in self.trainers()])

    def zoom_email(self, key):
        return self[key].get('zoom_email', self.email(key))

    def slack_email(self, key):
        return self[key].get('slack_email', self.email(key))

    def calendar_email(self, key):
        return self[key].get('calendar_email', self.email(key))

    def home_institution(self, key):
        return self[key]['home_institution']

    def fullname(self, key):
        return "%s %s" % (self.firstname(key), self.lastname(key))

    def firstname(self, key):
        return self[key]['firstname']

    def lastname(self, key):
        return self[key]['lastname']
