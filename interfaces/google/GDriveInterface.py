#!/usr/bin/env python3
import datetime
import logging
import os

try:
    from interfaces.google.GoogleInterface import GoogleInterface
except:
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


    def copy_file(self, original_id, newtitle, parent_folder_id):
        # https://developers.google.com/drive/api/reference/rest/v3/files/copy
        try:
            # Retrieve the existing parents to remove
            newfile = {'name': newtitle, 'parents': [ {"id": parent_folder_id } ] }
            file = self.get_service().files().copy(fileId=original_id, body=newfile, supportsAllDrives=True).execute()
            return file

        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return None


    def get_file(self, file_id, fields):
        # https://developers.google.com/drive/api/reference/rest/v3/files/get
        try:
            file = self.get_service().files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()
            return file

        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return None


    def get_file_ids(self, folder_id, title):
        # https://developers.google.com/drive/api/guides/search-files
        try:
            page_token = None
            files = self.get_service().files().list(
                        q=f'name="{title}" and "{folder_id}" in parents and trashed=false',
                        fields="files(id, name)",
                        spaces='drive',
                        supportsAllDrives=True,
                        pageSize=20,
                        pageToken=page_token,
                        corpora='allDrives',
                        includeItemsFromAllDrives=True,
                        orderBy='createdTime desc',
                    ).execute()


            if files:
                return [file['id'] for file in files['files']]
            else:
                return None

        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return None


    def get_file_id(self, folder_id, title):
        file_ids = self.get_file_ids(folder_id, title)
        if len(file_ids) != 1:
            self.logger.error(f"{len(file_ids)} files were found, expected exactly 1")
            return None
        else:
            return file_ids[0]


    def get_file_url(self, file_id):
        return self.get_file(file_id, "webViewLink")["webViewLink"]


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
    gdrive = GDriveInterface(credentials_file_path)

    # These are to uncomment when you want to test something
#    source_file_id = "1eURwPuPMDkL2C0R7ZD4e6qHLl8DNaGxtwYLgsfZ79Ec"
#    gdrive.copy_file(source_file_id, "Ceci est un test", "1xluiw761tnHq_khln7N5Jk-dBV59XJlB")
#    files = gdrive.get_file_id('1xluiw761tnHq_khln7N5Jk-dBV59XJlB', "2023-11-21 - online - Introduction to Quantum Programming with Snowflurry [online] - Usernames")
#    files = gdrive.get_file_id('1xluiw761tnHq_khln7N5Jk-dBV59XJlB', "2023-11-23 - CIP201 - Maitriser les systèmes de l'Alliance [en ligne, CIP201] - Nom d'utilisateurs")
#    print(f"{str(files)}")


if __name__ == "__main__":
    main()


