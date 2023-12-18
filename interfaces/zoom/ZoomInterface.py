#!/usr/bin/env python3

import requests
from datetime import datetime

class ZoomInterface:
    # constants
    auth_token_url = "https://zoom.us/oauth/token"
    api_base_url = "https://api.zoom.us/v2"

    def __init__(self, account_id, client_id, client_secret, timezone = "America/Montreal", user = "me"):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.timezone = timezone
        self.user = user

    def get_authorization_header(self):
        # vient de https://www.makeuseof.com/generate-server-to-server-oauth-zoom-meeting-link-python/
        data = {
            "grant_type": "account_credentials",
            "account_id": self.account_id,
            "client_secret": self.client_secret
        }
        response = requests.post(self.auth_token_url,
                                 auth=(self.client_id, self.client_secret),
                                 data=data)

        if response.status_code!=200:
            print("Unable to get access token")
        response_data = response.json()
        access_token = response_data["access_token"]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        return headers

    def create_meeting(self, topic, duration, start_date, start_time):
        headers = self.get_authorization_header()

        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetingCreate
        payload = {
            "topic": topic,
            #"schedule_for": "user@a",
            #"alternative_hosts": "a,b,c,d",
            "duration": duration,
            #"host_video": true,
            #"jbh_time": 5,
            #"join_before_host": "true",
            'start_time': f'{start_date}T{start_time}',
            "timezone": self.timezone,
            "type": 2,
        }

        resp = requests.post(f"{self.api_base_url}/users/{self.user}/meetings",
                             headers=headers,
                             json=payload)

        if resp.status_code!=201:
            print("Unable to generate meeting link")
        response_data = resp.json()

        content = {
                    "meeting_url": response_data["join_url"],
                    "password": response_data["password"],
                    "meetingTime": response_data["start_time"],
                    "purpose": response_data["topic"],
                    "duration": response_data["duration"],
                    "message": "Success",
                    "status":1
        }
        return content

    def list_meetings(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetings
        pass

    def get_meeting_participants(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/reportMeetingParticipants
        pass

    def create_webinar(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarCreate
        pass

    def add_panelist(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarPanelistCreate
        pass


    def get_webinars(self, date = None, ids = None, next_page_token = None):
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinars
        headers = self.get_authorization_header()
        payload = {
            "type": "scheduled",
            "page_size": "300",
        }
        if next_page_token:
            payload['next_page_token'] = next_page_token

        resp = requests.get(f"{self.api_base_url}/users/{self.user}/webinars",
                             headers=headers,
                             params=payload)

        response = resp.json()
        all_webinars = response.get('webinars', None)
        # get next pages if there is any
        if response.get('next_page_token', None):
            all_webinars += self.get_webinars(response['next_page_token'])

        webinars = all_webinars
        if date:
            webinars = [w for w in all_webinars if datetime.fromisoformat(w['start_time']).date() == date]
        if ids:
            webinars = [w for w in all_webinars if w['id'] in ids]
        return webinars


    def get_webinar(self, webinar_id):
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinars
        headers = self.get_authorization_header()
        payload = {
            "type": "scheduled",
            "page_size": "300",
        }

        resp = requests.get(f"{self.api_base_url}/webinars/{webinar_id}",
                             headers=headers,
                             params=payload)

        response = resp.json()
        return response


    def update_webinar(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarUpdate
        pass


    def get_webinar_participants(self, webinarId, next_page_token = None):
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/reportWebinarParticipants
        headers = self.get_authorization_header()
        payload = {
            "page_size": "300",
        }
        if next_page_token:
            payload['next_page_token'] = next_page_token

        resp = requests.get(f"{self.api_base_url}/report/webinars/{webinarId}/participants",
                             headers=headers,
                             params=payload)

        response = resp.json()
        all_participants = response.get('participants', None)
        # get next pages if there is any
        if response.get('next_page_token', None):
            all_participants += self.get_webinar_participants(webinarId, response['next_page_token'])

        return all_participants


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

    secrets = config['zoom']
    zoom = ZoomInterface(secrets['account_id'], secrets['client_id'], secrets['client_secret'], config['global']['timezone'])

    print(str(zoom.create_meeting("Meeting test", "60", "2023-11-10", "13:00:00")))

if __name__ == "__main__":
    main()


