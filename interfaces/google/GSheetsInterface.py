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
    secrets = configparser.ConfigParser()
    secrets_path = os.getenv('GSHEETS_SECRETS') or '../../secrets.cfg'
    secrets.read_file(open(secrets_path))
    secrets = secrets['google.sheets']
    gsheets = GSheetsInterface(secrets['credentials_file'])
    content = [['1', '2'], ['3', '4', '5', '8'], ['x']]
    folder_id = "1xluiw761tnHq_khln7N5Jk-dBV59XJlB"
    gsheets.create_spreadsheet("Ceci est un test", content, folder_id)



if __name__ == "__main__":
    main()

