#!/usr/bin/env python3

import logging
import os
# Import WebClient from Python SDK (github.com/slackapi/python-slack-sdk)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackInterface:
    # constants
    def __init__(self, bot_token):
        self.bot_token = bot_token
        # WebClient instantiates a client that can call API methods
        # When using Bolt, you can use either `app.client` or the `client` passed to listeners.
        self.client = WebClient(token=self.bot_token)
        self.logger = logging.getLogger(__name__)

    def create_channel(self, name):
        try:
            # Call the conversations.create method using the WebClient
            # conversations_create requires the channels:manage bot scope
            result = self.client.conversations_create(
                    # The name of the conversation
                    name=name
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error("Error creating conversation: {}".format(e))


def main():
    import configparser
    import os
    secrets = configparser.ConfigParser()
    secrets_path = os.getenv('SLACK_SECRETS') or '../secrets.cfg'
    secrets.read_file(open(secrets_path))
    secrets = secrets['slack']
    slack = SlackInterface(secrets['bot_token'])
    slack.create_channel("ceci-est-un-test")

if __name__ == "__main__":
    main()


