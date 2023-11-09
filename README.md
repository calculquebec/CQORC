# Calcul Québec One Ring Coordinator
CQORC: Calcul Québec One Ring Coordinator, lets you pop the cork and enjoy wine while it coordinates your training logistics.

# Setup
Create your credentials file : `secrets.cfg` with the following structure
```ini
[eventbrite]
api_key = YOUR PRIVATE API KEY

[zoom]
account_id = YOUR ACCOUNT ID
client_id = YOUR CLIENT ID
client_secret = YOUR CLIENT SECRET

[slack]
bot_token = YOUR SLACK BOT TOKEN
```

# Development
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
