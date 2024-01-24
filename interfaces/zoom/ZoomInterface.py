#!/usr/bin/env python3

import requests
from datetime import datetime

class ZoomInterface:
    '''Constants

    References:
        https://developers.zoom.us/docs/integrations/oauth/
        https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/
    '''
    auth_token_url = "https://zoom.us/oauth/token"
    api_base_url = "https://api.zoom.us/v2"


    def __init__(self, account_id, client_id, client_secret, timezone = "America/Montreal", user = "me"):
        '''Initialize the Zoom interface object with API credentials

        Reference: https://developers.zoom.us/docs/zoom-rooms/s2s-oauth/

        Arguments:
            account_id -- string. Usually stored secretly
            client_id -- string. Usually stored secretly
            client_secret -- string. Usually stored secretly
            timezone -- string. Valid values are in all_timezones from pytz
                https://pythonhosted.org/pytz/#helpers
            user -- string. Zoom username, either email address or "me"
        '''

        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.timezone = timezone
        self.user = user


    def get_authorization_header(self):
        '''Get the OAuth temporary authorization token

        Reference:
            https://developers.zoom.us/docs/zoom-rooms/s2s-oauth/
            https://www.makeuseof.com/generate-server-to-server-oauth-zoom-meeting-link-python/

        Returns: dictionary with keys "Authorization" and "Content-Type"
        '''

        response = requests.post(
            self.auth_token_url,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "account_credentials",
                "account_id": self.account_id,
                "client_secret": self.client_secret
            })

        response_data = response.json()

        assert response.status_code == 200, response_data['message']

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

    def get_meetings(self):
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


    def add_panelist(self, webinar_id, email:str, name:str):
        '''Add one panelist to the specified webinar by ID

        Reference:
            https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarPanelistCreate

        Arguments:
            webinar_id -- int or string. To specify the webinar by ID.
            email -- string. Email address of the panelist
            name -- string. Full name of the panelist
        '''

        response = requests.post(
            f'{self.api_base_url}/webinars/{webinar_id}/panelists',
            json={'panelists': [{
                'email': email,
                'name': name
            }]},
            headers=self.get_authorization_header(),
        )

        assert response.status_code == 201, response.json()['message']


    def get_panelists(self, webinar_id):
        '''Get a list of all panelists, one dictionary per panelist

        Reference:
            https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarPanelists

        Arguments:
            webinar_id -- int or string. To specify the webinar by ID.

        Returns: a list of dictionaries with fields 'name' and 'email'
        '''

        response = requests.get(
            f'{self.api_base_url}/webinars/{webinar_id}/panelists',
            headers=self.get_authorization_header(),
        )
        response_data = response.json()

        assert response.status_code == 200, response_data['message']

        return response_data['panelists']


    def get_webinar(self, webinar_id):
        '''Get a single scheduled webinar by the ID

        Reference:
            https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinar

        Arguments:
            webinar_id -- int or string. To select the webinar by ID.

        Returns: a dictionary with the information of one webinar
        '''

        response = requests.get(
            f'{self.api_base_url}/webinars/{webinar_id}',
            headers=self.get_authorization_header())
        response_data = response.json()

        assert response.status_code == 200, response_data['message']

        return response_data


    def get_webinars(self, date = None, ids = None):
        '''Get the list of scheduled webinars, one dictionary per webinar

        Reference:
            https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinars

        Arguments:
            date -- datetime.datetime object, or None. Select by date.
            ids -- list or set of webinar ID codes, or None. Select by ids.

        Returns: list of webinars, one dictionary per webinar, or []
        '''

        url = f'{self.api_base_url}/users/{self.user}/webinars'
        payload = {'type': 'scheduled'}
        headers = self.get_authorization_header()

        all_webinars = []
        next_page_token = 'The first query is done without a real token'

        while next_page_token:
            response = requests.get(url, params=payload, headers=headers)
            response_data = response.json()
            assert response.status_code == 200, response_data['message']

            all_webinars += response_data.get('webinars', [])
            next_page_token = response_data.get('next_page_token', None)
            payload['next_page_token'] = next_page_token

        webinars = all_webinars
        if date:
            webinars = [w for w in all_webinars if datetime.fromisoformat(w['start_time']).date() == date]
        if ids:
            webinars = [w for w in all_webinars if w['id'] in ids]

        return webinars


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
    '''Simple demonstration of the Zoom Interface

    Usage from the root directory of the project:
    PYTHONPATH=$PWD python interfaces/zoom/ZoomInterface.py
    '''

    from common import get_config
    import pytz

    class DefaultArgs:
        '''Some attributes with default values for get_config()'''
        config_dir = '.'
        secrets_dir = '.'

    # Get all configured values
    config = get_config(DefaultArgs())
    zoom_cfg = config['zoom']
    tzinfo = pytz.timezone(config['global']['timezone'])

    # Create the Zoom interface object
    zoom = ZoomInterface(
        account_id = zoom_cfg['account_id'],
        client_id = zoom_cfg['client_id'],
        client_secret = zoom_cfg['client_secret'],
        timezone = config['global']['timezone'],
        user = zoom_cfg['user'])

    # Create one meeting
    '''
    print(str(zoom.create_meeting("Meeting test", "60", "2023-11-10", "13:00:00")))
    '''

    # Overview of all webinars : ID Local-Start-Time End-of-topic
    webinars = zoom.get_webinars()
    print(f'{len(webinars)} webinar(s):')
    print(f"{'Webinar-ID':11} {'Date':10} {'Time':5}",
          'Session topic (last 48 characters)')

    for w in webinars:
        start_time = datetime.fromisoformat(w['start_time']).astimezone(tzinfo)
        print(w['id'], str(start_time)[:-9], w['topic'][-48:])

    # Detailed view of a single webinar
    webinar_id = 82199833482
    webinar = zoom.get_webinar(webinar_id)

    '''
    for attribute, value in webinar.items():
        if attribute == 'settings':
            print(f'{attribute}:')
            for setting_name, setting_value in value.items():
                print(f'- {setting_name}: {setting_value}')
        else:
            print(f'{attribute}: {value}')
    '''

    # Add a panelist to a signle webinar
    '''
    zoom.add_panelist(
        webinar_id,
        'first_name.last_name@calculquebec.ca',
        'Full Name')
    '''

    # Print all panelists of a single webinar
    '''
    start_t = datetime.fromisoformat(webinar['start_time']).astimezone(tzinfo)
    print(f"Panelists of {str(start_t)[:-9]} - \"{webinar['topic']}\":")
    for p in zoom.get_panelists(webinar_id):
        print(f"- \"{p['name']}\" <{p['email']}>")
    '''


if __name__ == "__main__":
    main()


