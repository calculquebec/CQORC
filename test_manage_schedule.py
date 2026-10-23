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

    def test_compute_role_summary(self):
        sessions = [
            {
                'course_id': '1', 'title': 'Course 1', 'start_date': '2026-09-20 10:00:00',
                'instructor': 'Alice', 'host': 'Bob', 'assistants': 'Charlie, David', 'hours': '3'
            },
            {
                'course_id': '2', 'title': 'Course 2', 'start_date': '2026-09-21 10:00:00',
                'instructor': 'Bob', 'host': 'Bob', 'assistants': 'Alice', 'hours': '2.5'
            },
            {
                'course_id': '3', 'title': 'Course 3', 'start_date': '2026-09-22 10:00:00',
                'instructor': 'Alice', 'host': '', 'assistants': '', 'hours': '1'
            },
            # Completely blank / placeholder row (should be skipped)
            {
                'course_id': '', 'title': '', 'start_date': '',
                'instructor': '', 'host': '', 'assistants': 'Dummy note', 'hours': ''
            }
        ]

        summary = manage_schedule.compute_role_summary(sessions)
        self.assertEqual(summary['total_sessions'], 3)

        # Alice: Instructor 2 (courses 1, 3), Assistant 1 (course 2) -> Total 3
        alice = summary['person_stats']['Alice']
        self.assertEqual(alice['roles']['instructor'], 2)
        self.assertEqual(alice['roles']['host'], 0)
        self.assertEqual(alice['roles']['assistants'], 1)
        self.assertEqual(alice['total_events'], 3)
        self.assertEqual(alice['total_hours'], 6.5)

        # Bob: Host 2 (courses 1, 2), Instructor 1 (course 2) -> Total 3
        bob = summary['person_stats']['Bob']
        self.assertEqual(bob['roles']['instructor'], 1)
        self.assertEqual(bob['roles']['host'], 2)
        self.assertEqual(bob['roles']['assistants'], 0)
        self.assertEqual(bob['total_events'], 3)
        self.assertEqual(bob['hours_by_role']['instructor'], 2.5)
        self.assertEqual(bob['hours_by_role']['host'], 5.5)
        self.assertEqual(bob['total_hours'], 8.0)

        # Charlie: Assistant 1 (course 1) -> Total 1
        charlie = summary['person_stats']['Charlie']
        self.assertEqual(charlie['total_events'], 1)
        self.assertEqual(charlie['roles']['assistants'], 1)
        self.assertEqual(charlie['total_hours'], 3.0)

        # David: Assistant 1 (course 1) -> Total 1
        david = summary['person_stats']['David']
        self.assertEqual(david['total_events'], 1)
        self.assertEqual(david['roles']['assistants'], 1)

        # Role totals & unassigned
        self.assertEqual(summary['role_totals']['instructor'], 3)
        self.assertEqual(summary['role_totals']['host'], 2)
        self.assertEqual(summary['role_totals']['assistants'], 3)
        self.assertEqual(summary['total_assignments'], 8)
        self.assertEqual(summary['unassigned']['instructor'], 0)
        self.assertEqual(summary['unassigned']['host'], 1)  # course 3 missing host
        self.assertEqual(summary['unassigned']['assistants'], 1)  # course 3 missing assistants

    def test_compute_role_summary_deduplication(self):
        """If someone is listed twice in the same role cell for a session, count once."""
        sessions = [
            {
                'course_id': '1', 'title': 'Course 1', 'start_date': '2026-09-20 10:00:00',
                'instructor': 'Alice', 'host': 'Bob', 'assistants': 'Charlie, Charlie', 'hours': '2'
            }
        ]
        summary = manage_schedule.compute_role_summary(sessions)
        self.assertEqual(summary['person_stats']['Charlie']['total_events'], 1)
        self.assertEqual(summary['person_stats']['Charlie']['roles']['assistants'], 1)
        self.assertEqual(summary['role_totals']['assistants'], 1)

    def test_sort_summary_items(self):
        items = [
            {'key': 'B', 'fullname': 'Bob', 'roles': {'instructor': 1, 'host': 2}, 'total_events': 3, 'total_hours': 10.0},
            {'key': 'A', 'fullname': 'Alice', 'roles': {'instructor': 4, 'host': 0}, 'total_events': 4, 'total_hours': 8.0},
            {'key': 'C', 'fullname': 'Charlie', 'roles': {'instructor': 0, 'host': 1}, 'total_events': 1, 'total_hours': 12.0},
        ]
        # Sort by total (default)
        sorted_tot = manage_schedule.sort_summary_items(items, sort_by="total")
        self.assertEqual([x['key'] for x in sorted_tot], ['A', 'B', 'C'])

        # Sort by instructor
        sorted_inst = manage_schedule.sort_summary_items(items, sort_by="instructor")
        self.assertEqual([x['key'] for x in sorted_inst], ['A', 'B', 'C'])

        # Sort by host
        sorted_host = manage_schedule.sort_summary_items(items, sort_by="host")
        self.assertEqual([x['key'] for x in sorted_host], ['B', 'C', 'A'])

        # Sort by hours
        sorted_hrs = manage_schedule.sort_summary_items(items, sort_by="hours")
        self.assertEqual([x['key'] for x in sorted_hrs], ['C', 'B', 'A'])

        # Sort by name
        sorted_name = manage_schedule.sort_summary_items(items, sort_by="name")
        self.assertEqual([x['key'] for x in sorted_name], ['A', 'B', 'C'])

    def test_build_summary_table_data_and_format(self):
        sessions = [
            {
                'course_id': '1', 'title': 'Course 1', 'start_date': '2026-09-20 10:00:00',
                'instructor': 'Alice', 'host': 'Bob', 'assistants': 'Charlie', 'hours': '3'
            }
        ]
        summary = manage_schedule.compute_role_summary(sessions)
        header, rows, totals_row, unassigned_row = manage_schedule.build_summary_table_data(summary)

        self.assertEqual(header, ['Key', 'Full Name', 'Institution', 'Instructor', 'Host', 'Assistants', 'Total Events', 'Total Hours'])
        self.assertEqual(len(rows), 3)
        self.assertEqual(totals_row[0], 'TOTALS')
        self.assertEqual(unassigned_row[0], 'UNASSIGNED')

        # Test text table formatting
        text_table = manage_schedule.format_summary_text_table(header, rows, totals_row, unassigned_row, title="Test Table")
        self.assertIn("Test Table", text_table)
        self.assertIn("Alice", text_table)
        self.assertIn("TOTALS", text_table)

        # Test CSV formatting
        csv_text = manage_schedule.format_summary_csv(header, rows, totals_row, unassigned_row)
        self.assertIn("Key,Full Name,Institution,Instructor,Host,Assistants,Total Events,Total Hours", csv_text)
        self.assertIn("Alice", csv_text)
        self.assertIn("TOTALS", csv_text)


class TestCheckConflicts(unittest.TestCase):
    """Tests for the check-conflicts helpers."""

    # ------------------------------------------------------------------
    # intervals_overlap
    # ------------------------------------------------------------------
    def test_intervals_overlap_no_overlap(self):
        from datetime import datetime
        s1 = datetime(2026, 9, 21, 9, 0)
        e1 = datetime(2026, 9, 21, 11, 0)
        s2 = datetime(2026, 9, 21, 12, 0)
        e2 = datetime(2026, 9, 21, 14, 0)
        self.assertFalse(manage_schedule.intervals_overlap(s1, e1, s2, e2))
        self.assertFalse(manage_schedule.intervals_overlap(s2, e2, s1, e1))

    def test_intervals_overlap_adjacent(self):
        from datetime import datetime
        s1 = datetime(2026, 9, 21, 9, 0)
        e1 = datetime(2026, 9, 21, 12, 0)
        s2 = datetime(2026, 9, 21, 12, 0)  # touching at boundary → NOT overlapping
        e2 = datetime(2026, 9, 21, 14, 0)
        self.assertFalse(manage_schedule.intervals_overlap(s1, e1, s2, e2))

    def test_intervals_overlap_overlapping(self):
        from datetime import datetime
        s1 = datetime(2026, 9, 21, 9, 0)
        e1 = datetime(2026, 9, 21, 13, 0)
        s2 = datetime(2026, 9, 21, 12, 0)
        e2 = datetime(2026, 9, 21, 14, 0)
        self.assertTrue(manage_schedule.intervals_overlap(s1, e1, s2, e2))
        self.assertTrue(manage_schedule.intervals_overlap(s2, e2, s1, e1))

    def test_intervals_overlap_contained(self):
        from datetime import datetime
        outer_s = datetime(2026, 9, 21, 9, 0)
        outer_e = datetime(2026, 9, 21, 17, 0)
        inner_s = datetime(2026, 9, 21, 11, 0)
        inner_e = datetime(2026, 9, 21, 13, 0)
        self.assertTrue(manage_schedule.intervals_overlap(outer_s, outer_e, inner_s, inner_e))
        self.assertTrue(manage_schedule.intervals_overlap(inner_s, inner_e, outer_s, outer_e))

    # ------------------------------------------------------------------
    # collect_session_assignments
    # ------------------------------------------------------------------
    def _make_session(self, course_id='1', title='Test', start='2026-09-21 09:00:00',
                      end='2026-09-21 11:00:00', instructor='alice', host='bob',
                      assistants='carol', hours='2'):
        return {
            'course_id': course_id, 'title': title,
            'start_date': start, 'end_date': end,
            'instructor': instructor, 'host': host, 'assistants': assistants,
            'hours': hours,
        }

    def test_collect_session_assignments_basic(self):
        sessions = [self._make_session()]
        result = manage_schedule.collect_session_assignments(sessions)
        keys = [(a['trainer_key'], a['role']) for a in result]
        self.assertIn(('alice', 'instructor'), keys)
        self.assertIn(('bob', 'host'), keys)
        self.assertIn(('carol', 'assistants'), keys)

    def test_collect_session_assignments_multiple_assistants(self):
        sessions = [self._make_session(assistants='carol, dave')]
        result = manage_schedule.collect_session_assignments(sessions)
        asst_keys = [a['trainer_key'] for a in result if a['role'] == 'assistants']
        self.assertIn('carol', asst_keys)
        self.assertIn('dave', asst_keys)

    def test_collect_session_assignments_skips_blank(self):
        sessions = [{'course_id': '', 'title': '', 'start_date': '', 'end_date': ''}]
        result = manage_schedule.collect_session_assignments(sessions)
        self.assertEqual(result, [])

    def test_collect_session_assignments_skips_no_dates(self):
        sessions = [{'course_id': '1', 'title': 'X', 'start_date': '', 'end_date': ''}]
        result = manage_schedule.collect_session_assignments(sessions)
        self.assertEqual(result, [])

    def test_collect_session_assignments_custom_roles(self):
        sessions = [self._make_session()]
        result = manage_schedule.collect_session_assignments(sessions, roles=['instructor'])
        self.assertEqual([a['role'] for a in result], ['instructor'])

    # ------------------------------------------------------------------
    # resolve_trainer_emails  (no trainers DB → falls back gracefully)
    # ------------------------------------------------------------------
    def test_resolve_trainer_emails_no_trainers(self):
        assignments = [{'trainer_key': 'alice', 'course_id': '1', 'title': 'T',
                        'start_date': '2026-09-21 09:00:00', 'end_date': '2026-09-21 11:00:00',
                        'hours': '2', 'role': 'instructor'}]
        enriched, email_map = manage_schedule.resolve_trainer_emails(assignments, trainers=None)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]['calendar_email'], '')
        self.assertEqual(email_map, {})

    # ------------------------------------------------------------------
    # detect_conflicts
    # ------------------------------------------------------------------
    def _make_aware(self, dt_str):
        import pytz
        tz = pytz.timezone('America/Toronto')
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        return tz.localize(dt)

    def _assignment(self, start='2026-09-21 09:00:00', end='2026-09-21 11:00:00', email='a@example.com'):
        return {
            'course_id': '1', 'title': 'Test', 'role': 'instructor',
            'trainer_key': 'alice', 'fullname': 'Alice', 'institution': 'U',
            'calendar_email': email, 'hours': '2',
            'start_date': start, 'end_date': end,
        }

    def test_detect_conflicts_no_busy(self):
        assignment = self._assignment()
        # Build freebusy results: trainer is free
        import pytz
        utc = pytz.utc
        tz = pytz.timezone('America/Toronto')
        start_aware = tz.localize(datetime(2026, 9, 21, 9, 0, 0)).astimezone(utc)
        end_aware = tz.localize(datetime(2026, 9, 21, 11, 0, 0)).astimezone(utc)
        time_min = start_aware.isoformat()
        time_max = end_aware.isoformat()
        freebusy = {(time_min, time_max): {'a@example.com': {'busy': []}}}
        conflicts, inaccessible = manage_schedule.detect_conflicts(
            [assignment], freebusy, 'America/Toronto'
        )
        self.assertEqual(conflicts, [])
        self.assertEqual(inaccessible, [])

    def test_detect_conflicts_with_overlap(self):
        assignment = self._assignment()
        import pytz
        utc = pytz.utc
        tz = pytz.timezone('America/Toronto')
        start_aware = tz.localize(datetime(2026, 9, 21, 9, 0, 0)).astimezone(utc)
        end_aware = tz.localize(datetime(2026, 9, 21, 11, 0, 0)).astimezone(utc)
        time_min = start_aware.isoformat()
        time_max = end_aware.isoformat()
        # Trainer has a busy slot that overlaps
        busy_start = tz.localize(datetime(2026, 9, 21, 10, 0, 0)).astimezone(utc).isoformat()
        busy_end = tz.localize(datetime(2026, 9, 21, 12, 0, 0)).astimezone(utc).isoformat()
        freebusy = {(time_min, time_max): {'a@example.com': {'busy': [
            {'start': busy_start, 'end': busy_end}
        ]}}}
        conflicts, inaccessible = manage_schedule.detect_conflicts(
            [assignment], freebusy, 'America/Toronto'
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['trainer_key'], 'alice')
        self.assertEqual(inaccessible, [])

    def test_detect_conflicts_inaccessible_calendar(self):
        assignment = self._assignment()
        import pytz
        utc = pytz.utc
        tz = pytz.timezone('America/Toronto')
        start_aware = tz.localize(datetime(2026, 9, 21, 9, 0, 0)).astimezone(utc)
        end_aware = tz.localize(datetime(2026, 9, 21, 11, 0, 0)).astimezone(utc)
        time_min = start_aware.isoformat()
        time_max = end_aware.isoformat()
        freebusy = {(time_min, time_max): {'a@example.com': {
            'errors': [{'domain': 'calendar', 'reason': 'notFound'}]
        }}}
        conflicts, inaccessible = manage_schedule.detect_conflicts(
            [assignment], freebusy, 'America/Toronto'
        )
        self.assertEqual(conflicts, [])
        self.assertEqual(len(inaccessible), 1)
        self.assertEqual(inaccessible[0]['trainer_key'], 'alice')

    def test_detect_conflicts_no_email_skipped(self):
        assignment = self._assignment(email='')
        freebusy = {}
        conflicts, inaccessible = manage_schedule.detect_conflicts(
            [assignment], freebusy, 'America/Toronto'
        )
        self.assertEqual(conflicts, [])
        self.assertEqual(inaccessible, [])

    # ------------------------------------------------------------------
    # format_conflicts_text_table and format_conflicts_csv
    # ------------------------------------------------------------------
    def test_format_conflicts_text_table_no_conflicts(self):
        text = manage_schedule.format_conflicts_text_table([], [], 'America/Toronto')
        self.assertIn("No scheduling conflicts found", text)

    def test_format_conflicts_text_table_with_conflict(self):
        conflict = {
            'course_id': '1', 'title': 'Test', 'role': 'instructor',
            'trainer_key': 'alice', 'fullname': 'Alice Smith', 'institution': 'U',
            'calendar_email': 'a@example.com', 'hours': '2',
            'start_date': '2026-09-21 09:00:00', 'end_date': '2026-09-21 11:00:00',
            'busy_start': '2026-09-21 10:00', 'busy_end': '2026-09-21 12:00',
            'status': 'conflict',
        }
        text = manage_schedule.format_conflicts_text_table([conflict], [], 'America/Toronto')
        self.assertIn("Alice Smith", text)
        self.assertIn("CONFLICTS", text)

    def test_format_conflicts_csv_headers(self):
        csv_text = manage_schedule.format_conflicts_csv([], [])
        self.assertIn("Status", csv_text)
        self.assertIn("Trainer Name", csv_text)
        self.assertIn("Busy Start", csv_text)

    def test_column_letter(self):
        self.assertEqual(manage_schedule.column_letter(0), 'A')
        self.assertEqual(manage_schedule.column_letter(25), 'Z')
        self.assertEqual(manage_schedule.column_letter(26), 'AA')
        self.assertEqual(manage_schedule.column_letter(27), 'AB')

    def test_build_summary_formula_rows(self):
        sessions = [
            {'course_id': 'C1', 'title': 'T', 'start_date': '2027-01-05', 'instructor': 'Julie', 'host': 'JulieFL', 'hours': '3'},
            {'course_id': 'C2', 'title': 'T', 'start_date': '2027-01-06', 'instructor': 'Julie', 'host': '', 'hours': '2'},
        ]
        source_header = ['course_id', 'title', 'start_date', 'instructor', 'host', 'hours']
        summary = manage_schedule.compute_role_summary(sessions, roles=['instructor', 'host'])
        header, rows, totals_row, unassigned_row = manage_schedule.build_summary_formula_rows(
            summary, source_header, "H27"
        )
        self.assertEqual(header, ['Key', 'Full Name', 'Institution', 'Instructor', 'Host', 'Total Events', 'Total Hours'])
        self.assertEqual([r[0] for r in rows], ['Julie', 'JulieFL'])
        # Instructor count for Julie reads column D of H27 and matches the exact key only
        self.assertEqual(rows[0][3], '=SUMPRODUCT(--REGEXMATCH(\'H27\'!D2:D,"(?:^|,)\\s*Julie\\s*(?:,|$)"))')
        self.assertEqual(rows[0][5], '=SUM(D2:E2)')
        self.assertIn("IFERROR(VALUE('H27'!F2:F),0)", rows[0][6])
        self.assertEqual(totals_row[3], '=SUM(D2:D3)')
        self.assertIn("LEN(TRIM('H27'!E2:E))=0", unassigned_row[4])

    def test_formula_arg_separator(self):
        self.assertEqual(manage_schedule.formula_arg_separator('en_US'), ',')
        self.assertEqual(manage_schedule.formula_arg_separator('fr_CA'), ';')
        self.assertEqual(manage_schedule.formula_arg_separator(None), ',')

    def test_build_summary_formula_rows_semicolon_separator(self):
        sessions = [{'course_id': 'C1', 'title': 'T', 'start_date': '2027-01-05', 'instructor': 'Julie', 'hours': '3'}]
        summary = manage_schedule.compute_role_summary(sessions, roles=['instructor'])
        _, rows, _, _ = manage_schedule.build_summary_formula_rows(
            summary, ['course_id', 'title', 'start_date', 'instructor', 'hours'], "H27", arg_sep=';'
        )
        self.assertIn("REGEXMATCH('H27'!D2:D;\"", rows[0][3])
        self.assertIn("IFERROR(VALUE('H27'!E2:E);0)", rows[0][5])

    def test_build_summary_formula_rows_missing_column(self):
        summary = manage_schedule.compute_role_summary([], roles=['instructor'])
        with self.assertRaises(ValueError):
            manage_schedule.build_summary_formula_rows(summary, ['course_id'], "H27")


if __name__ == '__main__':
    unittest.main()
