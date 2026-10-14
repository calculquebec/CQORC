import os
import interfaces.google.GSheetsInterface as GSheetsInterface

class Calendar:
    def __init__(self, global_config, args, sheet_name=None):
        # take the credentials file either from google section
        credentials_file = global_config['google']['credentials_file']
        secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
        credentials_file_path = os.path.join(secrets_dir, credentials_file)

        # initialize the Google Drive interface
        self.gsheets = GSheetsInterface.GSheetsInterface(credentials_file_path)

        self.spreadsheet_id = global_config['google']['calendar_file']
        self.sheet_name = sheet_name or getattr(args, 'sheet_name', None) or getattr(args, 'from_sheet', None) or global_config['google']['calendar_sheet_name']
        list_of_sessions = self.gsheets.get_values(self.spreadsheet_id, "A:Z", self.sheet_name)
        if isinstance(list_of_sessions, Exception):
            raise RuntimeError(f"Failed to read sheet '{self.sheet_name}': {list_of_sessions}")
        if not list_of_sessions:
            raise RuntimeError(f"Sheet '{self.sheet_name}' is empty or does not exist.")

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

    def set_gcal_id(self, course_id, session_start_date, gcal_id,  gcal_id_type=""):
        for session in self.courses[course_id]['sessions']:
            if session['start_date'] == session_start_date:
                session[gcal_id_type] = gcal_id

    def set_sessions(self, sessions):
        self.courses = {}
        for session in sessions:
            course_id = session.get('course_id')
            if course_id not in self.courses:
                self.courses[course_id] = {'sessions': []}
            self.courses[course_id]['sessions'].append(session)

    def update_spreadsheet(self, sheet_name=None, clear=False):
        values = [self.header]
        for course in self.courses.values():
            for session in course['sessions']:
                session_line = [session.get(k) if session.get(k) is not None else "" for k in self.header]
                values += [session_line]

        target_sheet = sheet_name or self.sheet_name
        if clear:
            self.gsheets.clear_values(self.spreadsheet_id, "A:Z", target_sheet)
        self.gsheets.update_values(self.spreadsheet_id, "A:Z", values, target_sheet)

