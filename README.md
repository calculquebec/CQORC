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

## Trainers database
TODO
