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


    def create_meeting(self, topic, duration, start_date, start_time, settings = {}):
        headers = self.get_authorization_header()

        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetingCreate
        payload = {
            "topic": topic,
            "duration": duration,
            'start_time': f'{start_date}T{start_time}',
            "timezone": self.timezone,
            "type": 2,
        }

        # optionally define various settings
        for key, value in settings.items():
            payload[key] = value

        resp = requests.post(f"{self.api_base_url}/users/{self.user}/meetings",
                             headers=headers,
                             json=payload)

        if resp.status_code!=201:
            print("Unable to generate meeting link")
        response_data = resp.json()
        return response_data

    def delete_meeting(self, meeting_id):
        headers = self.get_authorization_header()

        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetingDelete
        resp = requests.delete(f"{self.api_base_url}/meetings/{meeting_id}",
                               headers=headers)

        if resp.status_code!=204:
            print("Unable to delete meeting")
            print(f"{resp}")

        return

    def get_meetings(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetings
        pass

    def get_meeting_participants(self):
        # to be done
        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/reportMeetingParticipants
        pass


    def create_webinar(self, topic, duration, start_date, start_time, settings = {}):
        headers = self.get_authorization_header()

        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarCreate
        payload = {
            "topic": topic,
            "duration": duration,
            'start_time': f'{start_date}T{start_time}',
            "timezone": self.timezone,
            "type": 5,
        }

        # optionally define various settings
        for key, value in settings.items():
            payload[key] = value

        resp = requests.post(f"{self.api_base_url}/users/{self.user}/webinars",
                             headers=headers,
                             json=payload)

        if resp.status_code!=201:
            print("Unable to generate webinar link")
        response_data = resp.json()
        return response_data

    def delete_webinar(self, webinar_id):
        headers = self.get_authorization_header()

        # https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarDelete
        print(f"{self.api_base_url}/webinars/{webinar_id}")
        resp = requests.delete(f"{self.api_base_url}/webinars/{webinar_id}",
                               headers=headers)

        if resp.status_code!=204:
            print("Unable to delete webinar")
            print(f"{resp}")

        return


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


    def update_webinar(self, webinar_id, params):
        '''Update the webinar specified by ID

        Reference:
            https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webinarUpdate

        Arguments:
            webinar_id -- int or string. To specify the webinar by ID.
            params -- dictionary. Contains parameters to send.
        '''
        response = requests.patch(
            f'{self.api_base_url}/webinars/{webinar_id}',
            json=params,
            headers=self.get_authorization_header(),
        )

        assert response.status_code == 204, response.content
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
    # Create one webinar
    '''
    webinar = zoom.create_webinar("Meeting test", "60", "2024-10-10", "13:00:00")
    print(f"Created:{webinar}")
    '''
    # Overview of all webinars : ID Local-Start-Time End-of-topic
    webinars = zoom.get_webinars()
    print(f'{len(webinars)} webinar(s):')
    print(f"{'Webinar-ID':11} {'Date':10} {'Time':5}",
          'Session topic (last 48 characters)')
    for w in webinars:
        start_time = datetime.fromisoformat(w['start_time']).astimezone(tzinfo)
        print(w['id'], str(start_time)[:-9], w['topic'][-48:])

    '''
    print(f"Deleting webinar {webinar['id']}")
    zoom.delete_webinar(webinar['id'])
    '''
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


