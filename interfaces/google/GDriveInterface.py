#!/usr/bin/env python3
import datetime
import logging
import os

from GoogleInterface import GoogleInterface
from googleapiclient.errors import HttpError

class GDriveInterface(GoogleInterface):
    def __init__(self, key_file, credentials_type='user'):
        # liste des scopes https://developers.google.com/identity/protocols/oauth2/scopes#drive
        super(GDriveInterface, self).__init__(key_file, credentials_type, 'drive', 'v3', ['https://www.googleapis.com/auth/drive.file'])
        self.logger = logging.getLogger(__name__)


    def move_file_to_folder(self, file_id, folder_id):
        # https://developers.google.com/drive/api/guides/folder#move_files_between_folders
        try:
            # Retrieve the existing parents to remove
            file = self.get_service().files().get(fileId=file_id, fields="parents").execute()
            previous_parents = ",".join(file.get("parents"))
            # Move the file to the new folder
            file = (
                    self.get_service().files()
                    .update(
                        fileId=file_id,
                        addParents=folder_id,
                        removeParents=previous_parents,
                        fields="id, parents",
                        # necessary to support shared drives
                        supportsAllDrives=True,
                    )
                    .execute()
                    )
            return file.get("parents")

        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return None


def main():
    import configparser
    import os
    secrets = configparser.ConfigParser()
    secrets_path = os.getenv('GDRIVE_SECRETS') or '../../secrets.cfg'
    secrets.read_file(open(secrets_path))
    secrets = secrets['google.drive']
    gdrive = GDriveInterface(secrets['credentials_file'])


if __name__ == "__main__":
    main()


