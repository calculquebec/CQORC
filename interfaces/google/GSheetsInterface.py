#!/usr/bin/env python3
import datetime
import logging
import os

from GoogleInterface import GoogleInterface
from GDriveInterface import GDriveInterface
from googleapiclient.errors import HttpError

class GSheetsInterface(GoogleInterface):
    def __init__(self, key_file, credentials_type='user'):
        # liste des scopes https://developers.google.com/identity/protocols/oauth2/scopes#sheets
        super(GSheetsInterface, self).__init__(key_file, credentials_type, 'sheets', 'v4', ['https://www.googleapis.com/auth/spreadsheets'])
        # maximum of 26 columns to update
        self.default_range = "A:Z"
        self.logger = logging.getLogger(__name__)
        self.gdrive = None


    def get_gdrive(self):
        if not self.gdrive:
            self.gdrive = GDriveInterface(self.key_file)
        return self.gdrive


    def create_spreadsheet(self, title, content=None, folder_id=None):
        # https://developers.google.com/sheets/api/guides/create
        try:
            spreadsheet = {"properties": {"title": title}}
            spreadsheet = (
                self.get_service().spreadsheets()
                .create(body=spreadsheet, fields="spreadsheetId")
                .execute()
            )
            self.logger.info(f"Spreadsheet ID: {(spreadsheet.get('spreadsheetId'))}")
            spreadsheet_id = spreadsheet.get('spreadsheetId')
            if content:
                self.update_values(spreadsheet_id, self.default_range, content)
            if folder_id:
                self.get_gdrive().move_file_to_folder(spreadsheet_id, folder_id)

            return spreadsheet_id
        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return error


    def update_values(self, spreadsheet_id, range_name, values):
        # https://developers.google.com/sheets/api/guides/values
        """
        Creates the batch_update the user has access to.
        """
        try:
            value_input_option = "USER_ENTERED"
            body = {"values": values}
            result = (
                self.get_service().spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption=value_input_option,
                        body=body,
                )
                .execute()
            )
            self.logger.info(f"{result.get('updatedCells')} cells updated.")
            return result
        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return error


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

    # take the credentials file either from google.calendar or from google section
    credentials_file = config['google.sheets'].get('credentials_file', config['google']['credentials_file'])
    credentials_file_path = os.path.join(secrets_dir, credentials_file)
    gsheets = GSheetsInterface(credentials_file_path)
    content = [['1', '2'], ['3', '4', '5', '8'], ['x']]
    folder_id = config['script.usernames']['google_drive_folder_id']
    gsheets.create_spreadsheet("Ceci est un test", content, folder_id)



if __name__ == "__main__":
    main()

