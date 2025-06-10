import os
import interfaces.google.GSheetsInterface as GSheetsInterface

class Calendar:
    def __init__(self, global_config, args):
        # take the credentials file either from google section
        credentials_file = global_config['google']['credentials_file']
        secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
        credentials_file_path = os.path.join(secrets_dir, credentials_file)

        # initialize the Google Drive interface
        self.gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)

        self.spreadsheet_id = global_config['google']['calendar_file']
        self.sheet_name = global_config['google']['calendar_sheet_name']
        list_of_sessions = self.gsheets.get_values(self.spreadsheet_id, "A:Z", self.sheet_name)

        self.header = list_of_sessions[0]
        sessions = [{self.header[i]: item[i] if i < len(item) else None for i in range(len(self.header))} for item in list_of_sessions[1:]]

        self.courses = {}
        for session in sessions:
            course_id = session['course_id']
            if course_id not in self.courses:
                self.courses[course_id] = {'sessions': []}

            self.courses[course_id]['sessions'] += [session]


    # equivalent of former events_from_sheet_calendar
    def get_all_sessions(self):
        return [session for course in self.courses.values() for session in course['sessions']]

    def get_courses(self):
        return self.courses.values()
    
    def get_equipe_techno(self, course_id):
        for session in self.courses[course_id]['sessions']:
            return session['equipe_techno']

    def keys(self):
        return self.courses.keys()

    def items(self):
        return self.courses.items()

    def __getitem__(self, course_id):
        return self.courses[course_id]

    def set_eventbrite_id(self, course_id, eventbrite_id):
        for session in self.courses[course_id]['sessions']:
            session['eventbrite_id'] = eventbrite_id

    def set_zoom_id(self, course_id, zoom_id):
        for session in self.courses[course_id]['sessions']:
            session['zoom_id'] = zoom_id

    def set_slack_channel(self, course_id, slack_channel):
        for session in self.courses[course_id]['sessions']:
            session['slack_channel'] = slack_channel

    def set_public_gcal_id(self, course_id, session_start_date, public_gcal_id):
        for session in self.courses[course_id]['sessions']:
            if session['start_date'] == session_start_date:
                session['public_gcal_id'] = public_gcal_id

    def set_private_gcal_id(self, course_id, session_start_date, private_gcal_id):
        for session in self.courses[course_id]['sessions']:
            if session['start_date'] == session_start_date:
                session['private_gcal_id'] = private_gcal_id

    def update_spreadsheet(self):
        values = [self.header]
        for course in self.courses.values():
            for session in course['sessions']:
                session_line = [session[k] for k in self.header]
                values += [session_line]

        self.gsheets.update_values(self.spreadsheet_id, "A:Z", values, self.sheet_name)

