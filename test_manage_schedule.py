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

if __name__ == '__main__':
    unittest.main()
