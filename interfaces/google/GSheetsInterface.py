#!/usr/bin/env python3
import datetime
import logging
import os

try:
    from interfaces.google.GoogleInterface import GoogleInterface
    from interfaces.google.GDriveInterface import GDriveInterface
except:
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


    def update_values(self, spreadsheet_id, range_name, values, sheet_name=None):
        # https://developers.google.com/sheets/api/guides/values
        """
        Creates the batch_update the user has access to.
        """
        try:
            value_input_option = "USER_ENTERED"
            body = {"values": values}
            if sheet_name:
                range_name = f"'{sheet_name}'!{range_name}"
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


    def append_values(self, spreadsheet_id, range_name, values, sheet_name=None):
        # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets.values/append
        # https://developers.google.com/sheets/api/guides/values
        try:
            value_input_option = "USER_ENTERED"
            body = {"values": values}
            if sheet_name:
                range_name = f"'{sheet_name}'!{range_name}"
            result = (
                self.get_service().spreadsheets()
                    .values()
                    .append(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption=value_input_option,
                        body=body,
                )
                .execute()
            )
            self.logger.info(f"{result.get('updatedCells')} cells appended.")
            return result
        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return error


    def get_spreadsheet_metadata(self, sheet_id):
        # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/get
        try:
            spreadsheet = (
                self.get_service().spreadsheets().get(spreadsheetId=sheet_id).execute()
            )
            self.logger.info(f"Spreadsheet ID: {(spreadsheet.get('spreadsheetId'))}")
            return spreadsheet
        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return error


    def copy_protection(self, src_sheet_id, dst_sheet_id, sheet_id=0, wipe_dst_protection=True):
        src_metadata = self.get_spreadsheet_metadata(src_sheet_id)
        src_protected_ranges = src_metadata['sheets'][sheet_id].get('protectedRanges', None)
        dst_metadata = self.get_spreadsheet_metadata(dst_sheet_id)
        dst_protected_ranges = dst_metadata['sheets'][sheet_id].get('protectedRanges', None)

        requests = []
        if wipe_dst_protection and dst_protected_ranges:
            # https://developers.google.com/sheets/api/samples/ranges
            # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#deleteprotectedrangerequest
            requests += [{"deleteProtectedRange": {"protectedRangeId": p['protectedRangeId']}} for p in dst_protected_ranges]

        if src_protected_ranges:
            # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#addprotectedrangerequest
            # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/sheets#ProtectedRange
            requests += [{"addProtectedRange": {"protectedRange": p}} for p in src_protected_ranges]

        if requests:
            try:
                body = {"requests": requests}
                result = (
                        self.get_service().spreadsheets()
                        .batchUpdate(
                            spreadsheetId=dst_sheet_id,
                            body=body,
                            )
                        .execute()
                        )
                print(f"Result:{result}")
                self.logger.info(f"{result}")
            except HttpError as error:
                self.logger.error(f"An error occurred: {error}")
                return error
        else:
            self.logger.info(f"No changes needed in protected ranges")



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
    credentials_file = config['google']['credentials_file']
    credentials_file_path = os.path.join(secrets_dir, credentials_file)
    gsheets = GSheetsInterface(credentials_file_path)
    content = [['1', '2'], ['3', '4', '5', '8'], ['x']]
#    folder_id = config['script.usernames']['google_drive_folder_id']
#    gsheets.create_spreadsheet("Ceci est un test", content, folder_id)
#    dst = "1upq1zrendsgQLumDwIfR11Ck9xol4uKkc5BeZ5Pt4gA"
#    src = "1btl9MFm4bXCkLM3yaHkm901phTEAwWEr6y9zP6oH9L0"
#    gsheets.copy_protection(src, dst)

#    values = [["A", "2", "3"]]
#    gsheets.append_values(dst, "A1", values, sheet_name='2023-24')



if __name__ == "__main__":
    main()

