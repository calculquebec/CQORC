#!/usr/bin/env python3

import logging
import os
from datetime import datetime, timedelta
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
                # populate channel_dict for all channels retrieved
                self.channel_dict[channel['name']] = channel['id']

            if name in self.channel_dict:
                return self.channel_dict[name]

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


    def join_channel(self, channel_name):
        try:
            channel= self.get_channel_id(channel_name)
            result = self.client.conversations_join(
                    # The name of the conversation
                    channel=channel,
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error joining conversation: {e}")


    def is_member(self, channel_name):
        try:
            channel= self.get_channel_id(channel_name)
            result = self.client.conversations_info(
                    # The name of the conversation
                    channel=channel,
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)
            return result['channel']['is_member']

        except SlackApiError as e:
            self.logger.error(f"Error joining conversation: {e}")


    def post_to_channel(self, channel_name, message, schedule=None):
        try:
            channel= self.get_channel_id(channel_name)

            if schedule:
                schedule_timestamp = schedule.strftime('%s')
                result = self.client.chat_scheduleMessage(
                        # The name of the conversation
                        channel=channel,
                        text=message,
                        post_at=schedule_timestamp
                        )
                # Log the result which includes information like the ID of the conversation
                self.logger.info(result)
            else:
                result = self.client.chat_postMessage(
                        # The name of the conversation
                        channel=channel,
                        text=message
                        )
                # Log the result which includes information like the ID of the conversation
                self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error posting message: {e}")


    def list_channel_scheduled_messages(self, channel_name):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.chat_scheduledMessages_list(
                        # The name of the conversation
                        channel=channel
                        )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)
            return result['scheduled_messages']

        except SlackApiError as e:
            self.logger.error(f"Error listing scheduled messages: {e}")


    def delete_channel_scheduled_messages(self, channel_name, message_id):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.chat_deleteScheduledMessage(
                        # The name of the conversation
                        channel=channel,
                        scheduled_message_id=message_id
                        )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error deleting scheduled messages: {e}")


    def wipe_channel_scheduled_messages(self, channel_name):
        for message in self.list_channel_scheduled_messages(channel_name):
            self.delete_channel_scheduled_messages(channel_name, message['id'])


    def add_bookmark_to_channel(self, channel_name, title, link):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.bookmarks_add(
                    # The name of the conversation
                    channel_id=channel,
                    type='link',
                    title=title,
                    link=link
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error adding bookmark: {e}")


    def list_channel_bookmarks(self, channel_name):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.bookmarks_list(
                    # The name of the conversation
                    channel_id=channel,
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)
            return result['bookmarks']

        except SlackApiError as e:
            self.logger.error(f"Error listing bookmark: {e}")


    def delete_bookmark_from_channel(self, channel_name, bookmark_id):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.bookmarks_remove(
                    # The name of the conversation
                    channel_id=channel,
                    bookmark_id=bookmark_id,
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error removing bookmark: {e}")


    def get_channel_bookmark_link(self, channel_name, bookmark_title):
        for bookmark in self.list_channel_bookmarks(channel_name):
            if bookmark['title'] == bookmark_title:
                return bookmark['link']
        return None


    def update_channel_bookmarks(self, channel_name, bookmarks):
        # delete existing bookmarks if their title match
        for bookmark in self.list_channel_bookmarks(channel_name):
            if bookmark['title'] in [b['title'] for b in bookmarks]:
                self.delete_bookmark_from_channel(channel_name, bookmark['id'])

        # add new bookmarks
        for bookmark in bookmarks:
            self.add_bookmark_to_channel(channel_name, bookmark['title'], bookmark['link'])


    def archive_channel(self, channel_name):
        try:
            channel= self.get_channel_id(channel_name)

            result = self.client.conversations_archive(
                    # The name of the conversation
                    channel=channel
                    )
            # Log the result which includes information like the ID of the conversation
            self.logger.info(result)

        except SlackApiError as e:
            self.logger.error(f"Error archiving channel: {e}")



def main():
    import configparser
    import os
    import glob
    config = configparser.ConfigParser()
    config_dir = os.environ.get('CQORC_CONFIG_DIR', '.')
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', '.')
    config_files = glob.glob(os.path.join(config_dir, '*.cfg')) + glob.glob(os.path.join(secrets_dir, '*.cfg'))
    print("Reading config files: %s" % str(config_files))
    config.read(config_files)

    slack = SlackInterface(config['slack']['bot_token'])
#    slack.create_channel("ceci-est-un-test")
#    slack.invite_to_channel("ceci-est-un-test", "maxime.boissonneault@calculquebec.ca, charles.coulombe@calculquebec.ca")
#    slack.create_reminder("maxime.boissonneault@calculquebec.ca", "ceci est un test", "in 2 minutes")
    slack.post_to_channel("ceci-est-un-test", "ceci est un message")
    slack.post_to_channel("ceci-est-un-test", "ceci est un message programmé", datetime.now() + timedelta(minutes=1))
    slack.add_bookmark_to_channel("ceci-est-un-test", "Google", "https://www.google.ca")
#    slack.archive_channel("ceci-est-un-test")

if __name__ == "__main__":
    main()


