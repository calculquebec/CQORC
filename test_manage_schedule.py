import unittest
from datetime import date, datetime, timedelta
import manage_schedule

class TestManageSchedule(unittest.TestCase):
    def test_parse_session_name(self):
        self.assertEqual(manage_schedule.parse_session_name('A26'), ('A', 2026))
        self.assertEqual(manage_schedule.parse_session_name('a26'), ('A', 2026))
        self.assertEqual(manage_schedule.parse_session_name('H27'), ('H', 2027))
        self.assertEqual(manage_schedule.parse_session_name('h27'), ('H', 2027))
        self.assertEqual(manage_schedule.parse_session_name('A2026'), ('A', 2026))
        self.assertEqual(manage_schedule.parse_session_name('H2027'), ('H', 2027))

        with self.assertRaises(ValueError):
            manage_schedule.parse_session_name('XYZ')
        with self.assertRaises(ValueError):
            manage_schedule.parse_session_name('E26')

    def test_get_session_start_date(self):
        self.assertEqual(manage_schedule.get_session_start_date('A26'), date(2026, 9, 1))
        self.assertEqual(manage_schedule.get_session_start_date('H27'), date(2027, 1, 1))

    def test_get_first_monday(self):
        # 2026-09-01 is Tuesday -> first Monday is 2026-09-07
        self.assertEqual(manage_schedule.get_first_monday(date(2026, 9, 1)), date(2026, 9, 7))
        # 2027-01-01 is Friday -> first Monday is 2027-01-04
        self.assertEqual(manage_schedule.get_first_monday(date(2027, 1, 1)), date(2027, 1, 4))
        # 2025-09-01 is Monday -> first Monday is 2025-09-01
        self.assertEqual(manage_schedule.get_first_monday(date(2025, 9, 1)), date(2025, 9, 1))

    def test_calculate_shift_a26_to_h27(self):
        shift, m_from, m_to = manage_schedule.calculate_shift('A26', 'H27')
        self.assertEqual(m_from, date(2026, 9, 7))
        self.assertEqual(m_to, date(2027, 1, 4))
        self.assertEqual(shift, timedelta(days=119))
        self.assertEqual(shift.days % 7, 0)

        # Wednesday Sept 23, 2026 shifted by 119 days
        event_dt = datetime(2026, 9, 23, 10, 0, 0)
        shifted_dt = event_dt + shift
        self.assertEqual(shifted_dt, datetime(2027, 1, 20, 10, 0, 0))
        self.assertEqual(shifted_dt.weekday(), event_dt.weekday())

    def test_adjust_session(self):
        header = [
            'course_id', 'template', 'title', 'code', 'site',
            'start_date', 'end_date', 'instructor', 'host', 'assistants',
            'language', 'hours', 'eventbrite_id', 'zoom_id', 'slack_channel',
            'public_gcal_id', 'private_gcal_id', 'post_mortem_private_gcal_id',
            'equipe_techno', 'creation_grappe', 'destruction_grappe', 'cost_basis'
        ]
        sample = {
            'course_id': '2',
            'template': '12345',
            'title': 'Test Course',
            'code': 'PRV101',
            'site': 'en ligne',
            'start_date': '2026-09-23 10:00:00',
            'end_date': '2026-09-23 12:00:00',
            'instructor': 'Instructor Name',
            'host': 'Host Name',
            'assistants': 'Assistant 1',
            'language': 'FR',
            'hours': '2',
            'eventbrite_id': '99999',
            'zoom_id': '88888',
            'slack_channel': 'slack-test',
            'public_gcal_id': 'gcal-pub',
            'private_gcal_id': 'gcal-priv',
            'post_mortem_private_gcal_id': 'gcal-pm',
            'equipe_techno': 'techno-info',
            'creation_grappe': 'oui',
            'destruction_grappe': 'oui',
            'cost_basis': '100'
        }
        shift = timedelta(days=119)
        adjusted = manage_schedule.adjust_session(sample, header, shift)

        # Check preserved fields
        self.assertEqual(adjusted['course_id'], '2')
        self.assertEqual(adjusted['template'], '12345')
        self.assertEqual(adjusted['title'], 'Test Course')
        self.assertEqual(adjusted['code'], 'PRV101')
        self.assertEqual(adjusted['site'], 'en ligne')
        self.assertEqual(adjusted['instructor'], 'Instructor Name')
        self.assertEqual(adjusted['host'], 'Host Name')
        self.assertEqual(adjusted['assistants'], 'Assistant 1')
        self.assertEqual(adjusted['language'], 'FR')
        self.assertEqual(adjusted['hours'], '2')

        # Check shifted dates
        self.assertEqual(adjusted['start_date'], '2027-01-20 10:00:00')
        self.assertEqual(adjusted['end_date'], '2027-01-20 12:00:00')

        # Check blanked out fields
        for blank_field in [
            'eventbrite_id', 'zoom_id', 'slack_channel',
            'public_gcal_id', 'private_gcal_id', 'post_mortem_private_gcal_id',
            'equipe_techno', 'creation_grappe', 'destruction_grappe', 'cost_basis'
        ]:
            self.assertEqual(adjusted[blank_field], '', f"Expected {blank_field} to be empty string")

    def test_build_tentative_title(self):
        session = {
            'course_id': '4',
            'code': 'LNX101',
            'title': 'Introduction to Linux',
            'site': 'online',
            'instructor': 'Charles'
        }
        title = manage_schedule.build_tentative_title(session)
        self.assertTrue(title.startswith('[TENTATIVE]'))
        self.assertIn('Introduction to Linux', title)
        self.assertIn('LNX101', title)
        self.assertIn('Charles', title)

    def test_build_tentative_description(self):
        session = {
            'course_id': '4',
            'code': 'LNX101',
            'title': 'Introduction to Linux',
            'site': 'online',
            'language': 'EN',
            'hours': '3',
            'instructor': 'Charles',
            'host': 'Caroline',
            'assistants': 'John, Doe',
            'template': '12345'
        }
        desc = manage_schedule.build_tentative_description(session)
        self.assertIn('[TENTATIVE EVENT', desc)
        self.assertIn('Course ID: 4', desc)
        self.assertIn('Course Code: LNX101', desc)
        self.assertIn('Instructor: Charles', desc)
        self.assertIn('Host: Caroline', desc)
        self.assertIn('Assistants: John, Doe', desc)
        self.assertIn('No attendees are invited', desc)

    def test_date_formatting_roundtrip(self):
        tz_name = 'America/Toronto'
        # Winter date (EST: UTC-5)
        sheet_winter = '2027-01-20 10:00:00'
        gcal_winter = manage_schedule.format_dt_for_gcal(sheet_winter, tz_name)
        self.assertEqual(gcal_winter, '2027-01-20T10:00:00-05:00')
        back_winter = manage_schedule.format_gcal_dt_to_sheet(gcal_winter, tz_name)
        self.assertEqual(back_winter, sheet_winter)

        # Fall date (EDT: UTC-4)
        sheet_fall = '2026-09-23 10:00:00'
        gcal_fall = manage_schedule.format_dt_for_gcal(sheet_fall, tz_name)
        self.assertEqual(gcal_fall, '2026-09-23T10:00:00-04:00')
        back_fall = manage_schedule.format_gcal_dt_to_sheet(gcal_fall, tz_name)
        self.assertEqual(back_fall, sheet_fall)

    def test_parse_tentative_description(self):
        session = {
            'course_id': '5',
            'code': 'PYT101',
            'title': 'Introduction to Python',
            'site': 'en ligne',
            'language': 'FR',
            'hours': '3',
            'instructor': 'Alice',
            'host': 'Bob',
            'assistants': 'Charlie, Dave',
            'template': '9999'
        }
        desc = manage_schedule.build_tentative_description(session)
        parsed = manage_schedule.parse_tentative_description(desc)

        self.assertEqual(parsed.get('Title'), 'Introduction to Python')
        self.assertEqual(parsed.get('Site'), 'en ligne')
        self.assertEqual(parsed.get('Language'), 'FR')
        self.assertEqual(parsed.get('Hours'), '3')
        self.assertEqual(parsed.get('Instructor'), 'Alice')
        self.assertEqual(parsed.get('Host'), 'Bob')
        self.assertEqual(parsed.get('Assistants'), 'Charlie, Dave')
        self.assertEqual(parsed.get('Course Code'), 'PYT101')
        self.assertEqual(parsed.get('Course ID'), '5')

    def test_parse_tentative_description_with_modifications(self):
        """Simulate a user editing the description in Google Calendar."""
        session = {
            'course_id': '5',
            'code': 'PYT101',
            'title': 'Introduction to Python',
            'site': 'en ligne',
            'language': 'FR',
            'hours': '3',
            'instructor': 'Alice',
            'host': 'Bob',
            'assistants': 'Charlie',
            'template': '9999'
        }
        original_desc = manage_schedule.build_tentative_description(session)

        # Simulate editing: change instructor, add assistant
        modified_desc = original_desc.replace('Instructor: Alice', 'Instructor: Xavier')
        modified_desc = modified_desc.replace('Assistants: Charlie', 'Assistants: Charlie, Eve')

        parsed = manage_schedule.parse_tentative_description(modified_desc)
        self.assertEqual(parsed.get('Instructor'), 'Xavier')
        self.assertEqual(parsed.get('Assistants'), 'Charlie, Eve')
        self.assertEqual(parsed.get('Host'), 'Bob')  # unchanged

    def test_parse_tentative_description_empty(self):
        self.assertEqual(manage_schedule.parse_tentative_description(''), {})
        self.assertEqual(manage_schedule.parse_tentative_description(None), {})

    def test_parse_tentative_description_old_format(self):
        """Old-format descriptions (no '--- Session Details ---' sentinel) return empty dict."""
        old_desc = "[TENTATIVE EVENT]\nInstructor: Alice\nHost: Bob"
        parsed = manage_schedule.parse_tentative_description(old_desc)
        # Without the sentinel, nothing is parsed (graceful degradation)
        self.assertEqual(parsed, {})

if __name__ == '__main__':
    unittest.main()
