#!/usr/bin/env python3

import logging
import os
# Import WebClient from Python SDK (github.com/slackapi/python-slack-sdk)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackInterface:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        # WebClient instantiates a client that can call API methods
        # When using Bolt, you can use either `app.client` or the `client` passed to listeners.
        self.client = WebClient(token=self.bot_token)
        self.logger = logging.getLogger(__name__)
        self.channel_dict = {}
        self.user_dict = {}


    def create_channel(self, name):
        try:
            result = self.client.conversations_create(
                    # The name of the conversation
                    name=name
                    )
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error("Error creating conversation: {}".format(e))


    def get_channel_id(self, name, next_cursor=None):
        # if we already know the channel ID, don't check again
        if name in self.channel_dict:
            return self.channel_dict[name]

        try:
            if next_cursor is None:
                result = self.client.conversations_list(limit=100, exclude_archived=True)
            else:
                result = self.client.conversations_list(limit=100, exclude_archived=True, cursor=next_cursor)

            # if we find the channel, it ends here
            for channel in result['channels']:
                if channel['name'] == name:
                    self.channel_dict[name] = channel['id']
                    return channel['id']

            # if it was not found, check next cursor
            # at the end, next_cursor will be an empty string
            next_cursor = result["response_metadata"]["next_cursor"]
            if next_cursor != "":
                return self.get_channel_id(name, next_cursor)
            else:
                return None
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error("Error listing conversations: {}".format(e))


    def get_user_id(self, email, next_cursor=None):
        # if we already know the user ID, don't check again
        if email in self.user_dict:
            return self.user_dict[email]

        try:
            if next_cursor is None:
                result = self.client.users_list(limit=100, exclude_archived=True)
            else:
                result = self.client.users_list(limit=100, exclude_archived=True, cursor=next_cursor)

            # if we find the user, it ends here
            for user in result['members']:
                if 'profile' in user and 'email' in user['profile'] and user['profile']['email'] == email:
                    self.user_dict[email] = user['id']
                    return user['id']

            # if it was not found, check next cursor
            # at the end, next_cursor will be an empty string
            next_cursor = result["response_metadata"]["next_cursor"]
            if next_cursor != "":
                return self.get_user_id(email, next_cursor)
            else:
                return None
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error("Error listing users: {}".format(e))


    def invite_to_channel(self, channel_name, user_emails):
        try:
            channel= self.get_channel_id(channel_name)
            if isinstance(user_emails, str):
                user_emails = user_emails.split(',')
                user_emails = [email.strip() for email in user_emails]

            users = ",".join([self.get_user_id(email) for email in user_emails])

            result = self.client.conversations_invite(
                    # The name of the conversation
                    channel=channel,
                    users=users
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error("Error inviting to conversation: {}".format(e))


def main():
    import configparser
    import os
    secrets = configparser.ConfigParser()
    secrets_path = os.getenv('SLACK_SECRETS') or '../../secrets.cfg'
    secrets.read_file(open(secrets_path))
    secrets = secrets['slack']
    slack = SlackInterface(secrets['bot_token'])
#    slack.create_channel("ceci-est-un-test")
    slack.invite_to_channel("ceci-est-un-test", "maxime.boissonneault@calculquebec.ca, charles.coulombe@calculquebec.ca")
#    slack.create_reminder("maxime.boissonneault@calculquebec.ca", "ceci est un test", "in 2 minutes")

if __name__ == "__main__":
    main()


