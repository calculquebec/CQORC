#!/usr/bin/env python3

import requests
import configparser


class ZoomInterface:
    # constants
    auth_token_url = "https://zoom.us/oauth/token"
    api_base_url = "https://api.zoom.us/v2"

    def __init__(self):
        self.load_secrets()

    def load_secrets(self):
        self.secrets = configparser.ConfigParser()
        self.secrets.read_file(open('secrets.cfg'))

    def get_authorization_header(self):
        # vient de https://www.makeuseof.com/generate-server-to-server-oauth-zoom-meeting-link-python/
        account_id = self.secrets['zoom']['account_id']
        client_id = self.secrets['zoom']['client_id']
        client_secret = self.secrets['zoom']['client_secret']

        data = {
            "grant_type": "account_credentials",
            "account_id": account_id,
            "client_secret": client_secret
        }
        response = requests.post(self.auth_token_url,
                                 auth=(client_id, client_secret),
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
            "timezone": "America/Montreal"
            "type": 2,
        }

        resp = requests.post(f"{self.api_base_url}/users/me/meetings",
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

    def get_meeting_participants(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/reportMeetingParticipants

    def create_webinar(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarCreate

    def add_panelist(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarPanelistCreate

    def list_webinars(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinars

    def update_webinar(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarUpdate

    def get_webinar_participants(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/reportWebinarParticipants

def main():
    zoom = ZoomInterface()
    print(str(zoom.get_authorization_header()))

    print(str(zoom.create_meeting("Meeting test", "60", "2023-11-01", "13:00:00")))

if __name__ == "__main__":
    main()


