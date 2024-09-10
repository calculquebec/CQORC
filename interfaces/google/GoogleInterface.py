import logging
import os

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from oauth2client.service_account import ServiceAccountCredentials
from google.auth.transport.requests import Request

class GoogleInterface:
    def __init__(self, key_file, credentials_type, service_name, service_version, scopes):
        assert credentials_type in ["user", "service"], f'credentials_type should be either "user" or "service", found {credentials_type}'
        assert os.path.exists(key_file), f'key file should exist, {key_file} does not exist'
        assert isinstance(service_name, str), f"service_name should be a string, found {service_name}"
        assert isinstance(service_version, str), f"service_version should be a string, found {service_version}"
        assert isinstance(scopes, list), f"scopes should be a list, found {scopes}"
        self.key_file = key_file
        self.logger = logging.getLogger(__name__)
        self.scopes = scopes
        self.credentials = None
        self.service = None
        self.credentials_type = credentials_type
        self.service_name = service_name
        self.service_version = service_version
        token_file_name = "token_%s_%s.json" % (self.service_name, self.service_version)
        self.token_file = os.path.join(os.getenv('CQORC_SECRETS_DIR', './secrets'), token_file_name)


    def get_credentials(self):
        if self.credentials_type == "user":
            return self.get_user_credentials()
        elif self.credentials_type == "service":
            return self.get_service()


    def get_user_credentials(self):
        if not self.credentials or not self.credentials.valid:
            # The file token.json stores the user's access and refresh tokens, and is
            # created automatically when the authorization flow completes for the first
            # time.
            print(self.token_file)
            print(os.path.exists(self.token_file))
            if os.path.exists(self.token_file):
                self.credentials = Credentials.from_authorized_user_file(self.token_file, self.scopes)
            # If there are no (valid) credentials available, let the user log in.
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                            self.key_file, self.scopes
                            )
                    self.credentials = flow.run_local_server(port=0)
                # Save the credentials for the next run
                with open(self.token_file, "w") as token:
                    token.write(self.credentials.to_json())

        return self.credentials


    def get_service_credentials(self):
        """Creates a Credential object with the correct OAuth2 authorization.
        Uses the service account key stored in self.key_file
        Returns:
            Credentials, the user's credential.
        """
        if not self.credentials:
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.key_file, self.scopes)

            if not creds or creds.invalid:
                print('Unable to authenticate using service account key.')
                sys.exit()
            else:
                self.credentials = creds

        return self.credentials


    def get_service(self):
        if not self.service:
            try:
                service = build(self.service_name, self.service_version, credentials=self.get_credentials())
                self.service = service
            except HttpError as error:
                print('An error occurred: %s' % error)

        return self.service



