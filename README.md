# Calcul Québec One Ring Coordinator
CQORC: Calcul Québec One Ring Coordinator, lets you pop the cork and enjoy wine while it coordinates your training logistics.

# Setup
## Installing the scripts
After cloning the current repository, do the following:

1. Create a virtual env.
```bash
virtualenv --clear venv
source venv/bin/activate
```

2. Install requirements
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

# Source spreadsheet
The scripts in this repository all take a single Google Spreadsheet as input. Beside the header line, each line from the
spreadsheet corresponds to one session of a course. Courses can have one or multiple sessions.
The spreadsheet should have the following columns:
| Column title | Description |
| --- | --- |
| course_id | Identifier of a course. Can be repeated if the course is composed of multiple sessions |
| template | EventBrite ID of an event which is used as template for creating the event |
| title | Title of the course. |
| code | 6 character code for the course (i.e. PYT101) |
| start_date | Start date and time of the session. |
| end_date | End date and time of the session. |
| instructor | Key identifying the instructor in the trainer database. |
| host | Key identifying the host in the trainer database. |
| assistants | Comma-separated list of keys identifying the teaching assistants in the trainer database. |
| language | Language of the course (FR/EN) |
| hours | Duration of the session, in hours |
| eventbrite_id | ID of the EventBrite event for the course. Will be filled by the scripts |
| zoom_id | ID of the Zoom event for the course. Will be filled by the scripts |
| slack_channel | Name of the Slack channel for the course. Will be filled by the scripts |
| public_gcal_id | ID of the public Google Calendar event for the session. Will be filled by the scripts. |
| private_gcal_id | ID of the private Google Calendar event for the session. Will be filled by the scripts |

# Trainers database
A "database" file containing the list of trainers is used. It is stored in YAML format. One entry for a trainer should
look like:
```
Key:
  firstname: First name of the trainer
  lastname: Last name of the trainer
  email: Email address of the trainer
  home_institution: Home institution of the trainer
  zoom_email: Email address associated with the trainer's Zoom account (if undefined, email is used)
  slack_email: Email address associated with the trainer's Slack account (if undefined, email is used)
  calendar_email: Email address associated with the trainer's prefered email for calendar invitations (if undefined, email is used)
```

# Configuring the scripts
The scripts in this repository are designed to read and combine all `*.cfg` files in the directories specified by
environment variables `CQORC_CONFIG_DIR` and `CQORC_SECRETS_DIR`. Two directories are used so that you can split
configuration files in a public and a private repository. You can choose to use a single `*.cfg` file, or use as many
as you would like. In the sections below, `[email]` identifies that the parameters below are in the `[email]` section.

## Configuring authentication parameters
### `[email]`
This section is used to authenticate against a Google Gmail account to send certificates. See https://knowledge.workspace.google.com/kb/how-to-create-app-passwords-000009237
for more information on creating an app password.
| Key | Description |
| `user` | Email address of the account to use to send emails |
| `password` | Password of the account to use to send emails. We recommend creating an app password for this. |

### `[eventbrite]`
This section is used to interact with EventBrite. See https://www.eventbrite.com/platform/docs/authentication for more information
about getting your private token. The values are:
| Key    | Description |
| ------ | ----------------------------------------- |
| `api_key` | Your private token |
| `organization_id` | The ID of the organization which will host your events |

### `[slack]`
This section is used to interact with Slack. It uses a bot token. See https://api.slack.com/tutorials/tracks/getting-a-token
for more information on bot tokens. The values are:
| Key    | Description |
| ------ | ----------------------------------------- |
| `bot_token` | The bot token to use |

### `[zoom]`
For Zoom, you will want to create a Server-to-Server OAuth app. More information on this here: https://developers.zoom.us/docs/internal-apps/s2s-oauth/
This will give you an Account ID, Client ID and Client Secret, which you will need. The values for the configuration section are:
| Key    | Description |
| ------ | ----------------------------------------- |
| `account_id` | The Account ID |
| `client_id` | The client ID |
| `client_secret` | The client secret |
| `user` | The email of the user who will own the webinars |

### `[google]`
Google APIs are used for accessing Google Sheets, Google Drive and Google Calendar. When the scripts which use such API are first called,
it will open a browser asking you to authorize the application to use some scopes within each. It will save the authorization in a local
json file. This file is named based on the following configuration parameter:
| Key    | Description |
| ------ | ----------------------------------------- |
| `credentials_file` | Name of the file (i.e. `google_client_secret.json`) |

It will also save tokens for each API that is used, `token_calendar_v3.json`, `token_drive_v3.json`, `token_sheets_v4.json`. The client
secret file identifies the application, while the token files are proof that you have given that application the permission to access
some of the data. Once these JSON files are generated, you could share them internally.

## Configuring script behavior
TODO

# Running the scripts
Various scripts are provided in this repository:
| Script | Description |
| --- | --- |
| `zoom_manager.py` | Creates, updates and deletes Zoom webinars, and invite trainers. |
| `eventbrite_manager.py` | Creates, updates and deletes EventBrite events |
| `gcal_events.py` | Creates, updates and deletes Google calendar events in a private Google calendar, and invite trainers. |
| `public_gcal_events.py` | Creates, updates and delete Google calendar events in a public Google calendar. |
| `slack_manager.py` | Creates, updates and archives Slack channels, and invite trainers to it. |
| `create_usernames_spreadsheet.py` | Creates a list of usernames from the EventBrite registrant lists, and writes it to a Google spreadsheet |
| `zoom_attendance_to_eventbrite.py` | Reconciles the attendance of an event between Zoom participation records and the EventBrite attendees list, highlighting potential errors. |
| `create_events.py` (legacy) | Creates EventBrite events manually, by passing options as arguments. |

## Common arguments
Most of the above scripts have some common arguments which can be specified: 

| Argument | Description |
| --- | --- |
|  `-h, --help` | show this help message and exit |
| `--date YYYY-MM-DD[THH:MM:SS[±HH:MM]]` | Manage the first event on this date |
| `--course_id COURSE_ID` | Handle course specified by `COURSE_ID`, corresponding to the `course_id` in the spreadsheet |
| `--config_dir CONFIG_DIR` | Directory that holds the configuration files |
| `--secrets_dir SECRETS_DIR` | Directory that holds the configuration files |
| `--create` | Creates events/webinar/channel |
| `--update` | Updates events/webinar/channel |
| `--delete` | Deletes events/webinar |


# Typical order to run the scripts
## At the beginning of the term
Since EventBrite events are linked to Zoom events, and public Google calendar events display the EventBrite registration, you want to run the scripts in this order:
1. `zoom_manager.py` 
2. `eventbrite_manager.py`
3. `public_gcal_events.py` 
4. `slack_manager.py` 
5. `gcal_events.py` 

## The day before each event
Once the registration period on EventBrite is closed, one can use the script `create_usernames_spreadsheet.py` to create a spreadsheet with usernames for the
Magic Castle

## After the event
After the event, one can run the script `zoom_attendance_to_eventbrite.py` to reconcile attendance between the Zoom participation records and the EventBrite
attendees list. 

Then, one can use the `create_certificate.py` script to create and send certificates to attendees. 


