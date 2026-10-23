#!/usr/bin/env python3
import os
import sys
import re
import argparse
import csv
import html
import io
import smtplib
import pytz
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from email.utils import formataddr

import CQORCcalendar
import interfaces.google.GCalInterface as GCalInterface
from common import get_config, get_title, Trainers

# Columns whose values must be kept intact from the source session
KEEP_COLUMNS = {
    'course_id',
    'template',
    'title',
    'code',
    'site',
    'instructor',
    'host',
    'assistants',
    'language',
    'hours',
}

# Date columns that must be adjusted by the session shift
DATE_COLUMNS = {
    'start_date',
    'end_date',
}


def parse_session_name(session_name):
    """
    Parses a session name like 'A26', 'H27', 'A2026', 'H2027'.
    Returns (semester_type, year).
    Semester type:
      'A' -> Automne (starts September 1)
      'H' -> Hiver (starts January 1)
    """
    m = re.match(r'^([AH])(\d{2}|\d{4})$', session_name.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(
            f"Invalid session format: '{session_name}'. Expected format like 'A26' or 'H27' (or 'A2026', 'H2027')."
        )
    sem = m.group(1).upper()
    yr_str = m.group(2)
    year = int(yr_str)
    if year < 100:
        year += 2000
    return sem, year


def get_session_start_date(session_name):
    """
    Returns the nominal start date for the session.
    Automne (A) starts September 1.
    Hiver (H) starts January 1.
    """
    sem, year = parse_session_name(session_name)
    if sem == 'A':
        return date(year, 9, 1)
    elif sem == 'H':
        return date(year, 1, 1)
    else:
        raise ValueError(f"Unsupported semester '{sem}'. Supported semesters are 'A' and 'H'.")


def get_first_monday(dt):
    """
    Returns the first Monday on or after the given date dt.
    Monday is weekday 0.
    """
    days_to_monday = (7 - dt.weekday()) % 7
    return dt + timedelta(days=days_to_monday)


def calculate_shift(from_session, to_session):
    """
    Calculates the timedelta shift between two sessions based on the first Monday
    on or after their respective nominal start dates.
    Guaranteed to be an exact multiple of 7 days (preserving day of the week).
    """
    from_start = get_session_start_date(from_session)
    to_start = get_session_start_date(to_session)

    from_monday = get_first_monday(from_start)
    to_monday = get_first_monday(to_start)

    shift = to_monday - from_monday
    return shift, from_monday, to_monday


def parse_datetime(dt_str):
    """
    Parses a datetime string in common formats.
    """
    if not dt_str:
        return None
    dt_str = str(dt_str).strip()
    if not dt_str:
        return None

    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        raise ValueError(f"Unable to parse datetime: '{dt_str}'")


def adjust_session(session, header, shift):
    """
    Given a session dict and a shift timedelta:
    - Retains KEEP_COLUMNS
    - Shifts DATE_COLUMNS by shift
    - Blanks out all other columns (IDs, extra metadata, etc.)
    Returns adjusted session dict.
    """
    new_session = {}
    for col in header:
        if col in KEEP_COLUMNS:
            new_session[col] = session.get(col) or ''
        elif col in DATE_COLUMNS:
            val = session.get(col)
            if val:
                try:
                    dt = parse_datetime(val)
                    if dt:
                        new_dt = dt + shift
                        new_session[col] = new_dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        new_session[col] = ''
                except ValueError as e:
                    print(f"Warning: could not parse date '{val}' in column '{col}': {e}")
                    new_session[col] = val
            else:
                new_session[col] = ''
        else:
            # Blank out all other columns (eventbrite_id, zoom_id, slack_channel, etc.)
            new_session[col] = ''
    return new_session


def init_gcal(global_config, args):
    """
    Initializes and returns the GCalInterface for the private Google Calendar.
    """
    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', args.secrets_dir)
    credentials_file = global_config['google']['credentials_file']
    credentials_file_path = os.path.join(secrets_dir, credentials_file)
    timezone = global_config['google.calendar'].get('timezone', global_config['global']['timezone'])
    calendar_id = global_config['google.calendar']['calendar_id']
    gcal = GCalInterface.GCalInterface(credentials_file_path, calendar_id, timezone)
    return gcal, timezone


def build_tentative_title(session):
    """
    Builds the tentative event title clearly identifying it as tentative.
    Includes title, site, code, and instructor if available.
    """
    title = get_title(session)
    instructor = (session.get('instructor') or '').strip()
    if instructor:
        return f"[TENTATIVE] {title} ({instructor})"
    return f"[TENTATIVE] {title}"


def build_tentative_description(session):
    """
    Builds the event description including all available metadata about the session.
    """
    lines = [
        "[TENTATIVE EVENT - SCHEDULE PLANNING]",
        "Note: This is a tentative planning event. No attendees are invited.",
        "",
        "--- Session Details ---",
        f"Course ID: {session.get('course_id') or ''}",
        f"Course Code: {session.get('code') or ''}",
        f"Title: {session.get('title') or ''}",
        f"Site: {session.get('site') or ''}",
        f"Language: {session.get('language') or ''}",
        f"Hours: {session.get('hours') or ''}",
        f"Instructor: {session.get('instructor') or ''}",
        f"Host: {session.get('host') or ''}",
        f"Assistants: {session.get('assistants') or ''}",
        f"Template: {session.get('template') or ''}",
    ]
    return "\n".join(lines)


# Fields that can be updated from the calendar description back to the sheet.
# Maps description key -> session dict key.
DESCRIPTION_SYNC_FIELDS = {
    'Title':       'title',
    'Site':        'site',
    'Language':    'language',
    'Hours':       'hours',
    'Instructor':  'instructor',
    'Host':        'host',
    'Assistants':  'assistants',
}


def parse_tentative_description(description_text):
    """
    Parses a tentative event description produced by build_tentative_description()
    and returns a dict of field values found in the "--- Session Details ---" block.

    Keys match the labels used in build_tentative_description (e.g. 'Title',
    'Instructor', 'Host', 'Assistants', etc.).  Values are stripped strings;
    absent or blank fields are returned as empty strings.
    """
    if not description_text:
        return {}

    parsed = {}
    in_details = False
    for line in description_text.splitlines():
        line = line.strip()
        if line == '--- Session Details ---':
            in_details = True
            continue
        if not in_details:
            continue
        if ':' in line:
            key, _, value = line.partition(':')
            parsed[key.strip()] = value.strip()

    return parsed


def format_dt_for_gcal(dt_str, tz_name):
    """
    Converts '%Y-%m-%d %H:%M:%S' string to ISO 8601 with timezone offset.
    """
    dt = parse_datetime(dt_str)
    tz = pytz.timezone(tz_name)
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    else:
        dt = dt.astimezone(tz)
    return dt.isoformat()


def format_gcal_dt_to_sheet(gcal_dt_str, tz_name):
    """
    Converts Google Calendar ISO string to '%Y-%m-%d %H:%M:%S' in the given timezone.
    """
    tz = pytz.timezone(tz_name)
    if 'T' not in gcal_dt_str:
        dt = datetime.strptime(gcal_dt_str, '%Y-%m-%d')
        return dt.strftime('%Y-%m-%d 00:00:00')
    dt = datetime.fromisoformat(gcal_dt_str)
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------------------
# Action 1: Create Sheet
# ---------------------------------------------------------------------------
def action_create_sheet(args, global_config):
    from_sheet = args.from_sheet or global_config['google']['calendar_sheet_name']
    to_sheet = args.to_sheet

    print(f"Action: create-sheet ({from_sheet} -> {to_sheet})")

    # Compute shift
    try:
        shift, from_monday, to_monday = calculate_shift(from_sheet, to_sheet)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    shift_weeks = shift.days // 7
    print(f"Source session '{from_sheet}' (first Monday: {from_monday})")
    print(f"Target session '{to_sheet}' (first Monday: {to_monday})")
    print(f"Date shift: {shift.days} days ({shift_weeks} weeks)\n")

    # Load source calendar using CQORCcalendar.Calendar
    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=from_sheet)
    except Exception as e:
        print(f"Error loading sheet '{from_sheet}' from Google spreadsheet: {e}")
        sys.exit(1)

    header = calendar.header
    all_sessions = calendar.get_all_sessions()

    # Filter and adjust sessions
    adjusted_sessions = []
    for s in all_sessions:
        if not s.get('course_id') and not s.get('title') and not s.get('code') and not s.get('start_date'):
            continue
        adjusted_sessions.append(adjust_session(s, header, shift))

    print(f"Processed {len(adjusted_sessions)} sessions from '{from_sheet}'.\n")

    sessions_to_show = adjusted_sessions if args.verbose else adjusted_sessions[:5]
    print(f"{'All' if args.verbose else 'Sample'} adjusted sessions:")
    for s in sessions_to_show:
        print(f"  Course {s.get('course_id')}: {s.get('code')} - {s.get('title')[:35]}")
        print(f"    New start: {s.get('start_date')} | New end: {s.get('end_date')}")

    if not args.verbose and len(adjusted_sessions) > 5:
        print(f"  ... and {len(adjusted_sessions) - 5} more sessions (use --verbose to see all).\n")

    if args.dry_run:
        print("[DRY RUN] Dry run enabled. No changes were made to Google Sheets.")
        return

    # Check target sheet existence
    sheet_exists = calendar.gsheets.sheet_exists(calendar.spreadsheet_id, to_sheet)
    if sheet_exists:
        if not args.overwrite:
            print(
                f"Error: Sheet '{to_sheet}' already exists in spreadsheet {calendar.spreadsheet_id}.\n"
                "Use --overwrite to overwrite it."
            )
            sys.exit(1)
        print(f"Target sheet '{to_sheet}' already exists. Overwrite enabled. Clearing old values...")
        calendar.gsheets.clear_values(calendar.spreadsheet_id, "A:Z", to_sheet)
    else:
        print(f"Creating new sheet '{to_sheet}'...")
        try:
            calendar.gsheets.duplicate_sheet(calendar.spreadsheet_id, from_sheet, to_sheet)
            calendar.gsheets.clear_values(calendar.spreadsheet_id, "A:Z", to_sheet)
        except Exception as e:
            print(f"Note: Could not duplicate sheet '{from_sheet}' ({e}), falling back to adding a blank sheet...")
            calendar.gsheets.add_sheet(calendar.spreadsheet_id, to_sheet)

    calendar.set_sessions(adjusted_sessions)
    print(f"Writing {len(adjusted_sessions)} sessions to sheet '{to_sheet}'...")
    calendar.update_spreadsheet(sheet_name=to_sheet)
    print(f"Successfully created and populated schedule in sheet '{to_sheet}'!")


# ---------------------------------------------------------------------------
# Action 2: Sync to Google Calendar (Tentative Events)
# ---------------------------------------------------------------------------
def action_sync_to_calendar(args, global_config):
    sheet_name = args.sheet or global_config['google']['calendar_sheet_name']
    print(f"Action: sync-to-calendar (Sheet: '{sheet_name}')")

    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    except Exception as e:
        print(f"Error loading sheet '{sheet_name}': {e}")
        sys.exit(1)

    gcal, tz_name = init_gcal(global_config, args)
    sessions = calendar.get_all_sessions()
    print(f"Synchronizing sessions from sheet '{sheet_name}' to private Google Calendar as tentative events...")

    created_count = 0
    updated_count = 0
    deleted_from_cal_count = 0
    skipped_count = 0
    existing_count = 0

    # 1. Handle Deletions in spreadsheet (events deleted from sheet -> delete from calendar)
    active_gcal_ids = {s.get('private_gcal_id') for s in sessions if s.get('private_gcal_id')}
    try:
        candidate_events = gcal.list_all_events(q="[TENTATIVE]")
        for ev in candidate_events:
            ev_id = ev['id']
            if ev.get('status') == 'cancelled':
                continue
            ext_sheet = ev.get('extendedProperties', {}).get('private', {}).get('sheet_name')
            summary = ev.get('summary', '')
            is_sheet_event = (ext_sheet == sheet_name) or ('[TENTATIVE]' in summary and not ext_sheet)
            if is_sheet_event and ev_id not in active_gcal_ids:
                # Event was deleted from the spreadsheet! Delete from Google Calendar
                if args.dry_run:
                    print(f"  [DRY RUN] Would delete tentative event from calendar (removed from sheet): {ev_id} ({summary})")
                    deleted_from_cal_count += 1
                else:
                    try:
                        gcal.delete_event(ev_id, send_updates="none")
                        print(f"  Deleted tentative event from calendar (removed from sheet): {ev_id} ({summary})")
                        deleted_from_cal_count += 1
                    except Exception as e:
                        print(f"  Warning: Could not delete orphaned event {ev_id}: {e}")
    except Exception as e:
        if args.verbose:
            print(f"Note: error searching tentative events for deletion check: {e}")

    # 2. Handle Additions & Updates in spreadsheet (events added/updated in sheet -> create/update on calendar)
    sheet_needs_save = False
    for session in sessions:
        course_id = session.get('course_id')
        code = session.get('code') or ''
        start_date = session.get('start_date')
        end_date = session.get('end_date')

        if not course_id and not session.get('title') and not start_date:
            continue
        if not start_date or not end_date:
            if args.verbose:
                print(f"  Skipping Course {course_id} ({code}): missing start_date or end_date")
            skipped_count += 1
            continue

        event_title = build_tentative_title(session)
        description = build_tentative_description(session)
        start_iso = format_dt_for_gcal(start_date, tz_name)
        end_iso = format_dt_for_gcal(end_date, tz_name)
        ext_props = {
            'private': {
                'course_id': str(course_id),
                'tentative': 'true',
                'sheet_name': str(sheet_name)
            }
        }

        existing_gcal_id = session.get('private_gcal_id')

        # Check if event exists on calendar
        ev = None
        if existing_gcal_id:
            try:
                ev = gcal.get_event(existing_gcal_id)
            except Exception:
                pass

        if not existing_gcal_id or not ev or ev.get('status') == 'cancelled':
            # Addition or Re-creation needed!
            if args.dry_run:
                action_label = "re-create" if existing_gcal_id else "create"
                print(f"  [DRY RUN] Would {action_label} tentative event for Course {course_id} ({code}):")
                print(f"    Title: {event_title}")
                print(f"    Start: {start_iso} | End: {end_iso}")
                created_count += 1
            else:
                try:
                    ev = gcal.create_event(
                        start_time=start_iso,
                        end_time=end_iso,
                        summary=event_title,
                        description=description,
                        attendees=None,
                        send_updates="none",
                        status="tentative",
                        extended_properties=ext_props
                    )
                    event_id = ev['id']
                    session['private_gcal_id'] = event_id
                    created_count += 1
                    sheet_needs_save = True
                    print(f"  Created tentative event {event_id} for Course {course_id} ({code}): {start_date}")
                except Exception as e:
                    print(f"  Error creating event for Course {course_id} ({code}): {e}")
        else:
            # Event already exists on calendar -> check for modifications in sheet
            gcal_start = ev['start'].get('dateTime') or ev['start'].get('date')
            gcal_end = ev['end'].get('dateTime') or ev['end'].get('date')
            new_start = format_gcal_dt_to_sheet(gcal_start, tz_name)
            new_end = format_gcal_dt_to_sheet(gcal_end, tz_name)
            gcal_desc = ev.get('description', '')
            gcal_summary = ev.get('summary', '')

            needs_update = False
            if new_start != start_date or new_end != end_date:
                needs_update = True
            if description.strip() != gcal_desc.strip():
                needs_update = True
            if event_title != gcal_summary:
                needs_update = True

            if needs_update or getattr(args, 'force', False):
                if args.dry_run:
                    print(f"  [DRY RUN] Would update Google Calendar event {existing_gcal_id} for Course {course_id} ({code}) with sheet changes.")
                    updated_count += 1
                else:
                    try:
                        gcal.update_event(
                            existing_gcal_id,
                            start_time=start_iso,
                            end_time=end_iso,
                            summary=event_title,
                            description=description,
                            attendees=None,
                            send_updates="none"
                        )
                        print(f"  Updated tentative event {existing_gcal_id} for Course {course_id} ({code})")
                        updated_count += 1
                    except Exception as e:
                        print(f"  Error updating event {existing_gcal_id} for Course {course_id}: {e}")
            else:
                if args.verbose:
                    print(f"  Course {course_id} ({code}): already up to date on calendar")
                existing_count += 1

    if not args.dry_run and sheet_needs_save:
        print(f"\nWriting updated Google Calendar IDs to sheet '{sheet_name}'...")
        calendar.update_spreadsheet(sheet_name=sheet_name, clear=True)

    print(f"\nSummary for sync-to-calendar:")
    print(f"  Created on calendar (additions): {created_count}")
    print(f"  Updated on calendar: {updated_count}")
    print(f"  Deleted from calendar (removed from sheet): {deleted_from_cal_count}")
    print(f"  Already existed & unchanged: {existing_count}")
    print(f"  Skipped (no dates): {skipped_count}")


# ---------------------------------------------------------------------------
# Action 3: Sync from Google Calendar to Spreadsheet
# ---------------------------------------------------------------------------
def action_sync_from_calendar(args, global_config):
    sheet_name = args.sheet or global_config['google']['calendar_sheet_name']
    print(f"Action: sync-from-calendar (Sheet: '{sheet_name}')")

    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    except Exception as e:
        print(f"Error loading sheet '{sheet_name}': {e}")
        sys.exit(1)

    gcal, tz_name = init_gcal(global_config, args)
    sessions = calendar.get_all_sessions()
    print(f"Checking for changes on private Google Calendar for sheet '{sheet_name}'...")

    updated_count = 0
    deleted_from_sheet_count = 0
    added_to_sheet_count = 0
    unchanged_count = 0
    missing_count = 0

    deleted_sessions = set()
    seen_gcal_ids = set()

    for session in sessions:
        course_id = session.get('course_id')
        code = session.get('code') or ''
        title = session.get('title') or ''
        gcal_id = session.get('private_gcal_id')

        if not course_id and not title and not session.get('start_date'):
            continue

        if not gcal_id:
            if args.verbose:
                print(f"  Course {course_id} ({code}): No private_gcal_id recorded (new in sheet).")
            missing_count += 1
            continue

        seen_gcal_ids.add(gcal_id)

        try:
            ev = gcal.get_event(gcal_id)
        except Exception as e:
            print(f"  Course {course_id} ({code}): Could not fetch event {gcal_id}: {e}")
            missing_count += 1
            continue

        # Check if event was deleted on Google Calendar
        if not ev or ev.get('status') == 'cancelled':
            # Event was deleted manually from Google Calendar!
            print(f"  Course {course_id} ({code} - {title[:30]}): DELETED on Google Calendar -> Removing from spreadsheet")
            deleted_sessions.add(id(session))
            deleted_from_sheet_count += 1
            continue

        session_changed = False
        changes = []

        # --- Check dates ---
        current_start = session.get('start_date') or ''
        current_end = session.get('end_date') or ''
        gcal_start = ev['start'].get('dateTime') or ev['start'].get('date')
        gcal_end = ev['end'].get('dateTime') or ev['end'].get('date')
        new_start = format_gcal_dt_to_sheet(gcal_start, tz_name)
        new_end = format_gcal_dt_to_sheet(gcal_end, tz_name)

        if new_start != current_start:
            changes.append(f"    Start:      {current_start!r} -> {new_start!r}")
            session['start_date'] = new_start
            session_changed = True
        if new_end != current_end:
            changes.append(f"    End:        {current_end!r} -> {new_end!r}")
            session['end_date'] = new_end
            session_changed = True

        # --- Check description fields (people & metadata) ---
        desc = ev.get('description') or ''
        parsed = parse_tentative_description(desc)

        for desc_key, session_key in DESCRIPTION_SYNC_FIELDS.items():
            new_val = parsed.get(desc_key, None)
            if new_val is None:
                # Field not found in description - skip (old format or manually removed)
                continue
            current_val = (session.get(session_key) or '').strip()
            new_val = new_val.strip()
            if new_val != current_val:
                label = f"{desc_key} ({session_key})"
                changes.append(f"    {label:<22} {current_val!r} -> {new_val!r}")
                session[session_key] = new_val
                session_changed = True

        if session_changed:
            print(f"  Course {course_id} ({code} - {title[:30]}): UPDATED")
            for ch in changes:
                print(ch)
            updated_count += 1
        else:
            if args.verbose:
                print(f"  Course {course_id} ({code}): unchanged ({current_start})")
            unchanged_count += 1

    # Check for tentative events created manually in Google Calendar that are not yet in the sheet
    added_sessions = []
    try:
        candidate_events = gcal.list_all_events(q="[TENTATIVE]")
        for ev in candidate_events:
            ev_id = ev['id']
            if ev.get('status') == 'cancelled':
                continue
            if ev_id in seen_gcal_ids:
                continue
            ext_sheet = ev.get('extendedProperties', {}).get('private', {}).get('sheet_name')
            if ext_sheet == sheet_name:
                desc = ev.get('description', '')
                parsed = parse_tentative_description(desc)
                gcal_start = ev['start'].get('dateTime') or ev['start'].get('date')
                gcal_end = ev['end'].get('dateTime') or ev['end'].get('date')

                new_session = {k: '' for k in calendar.header}
                new_session['course_id'] = parsed.get('Course ID') or ''
                new_session['code'] = parsed.get('Course Code') or ''
                new_session['title'] = parsed.get('Title') or ev.get('summary', '').replace('[TENTATIVE]', '').strip()
                new_session['site'] = parsed.get('Site') or ''
                new_session['language'] = parsed.get('Language') or ''
                new_session['hours'] = parsed.get('Hours') or ''
                new_session['instructor'] = parsed.get('Instructor') or ''
                new_session['host'] = parsed.get('Host') or ''
                new_session['assistants'] = parsed.get('Assistants') or ''
                new_session['template'] = parsed.get('Template') or ''
                new_session['start_date'] = format_gcal_dt_to_sheet(gcal_start, tz_name)
                new_session['end_date'] = format_gcal_dt_to_sheet(gcal_end, tz_name)
                new_session['private_gcal_id'] = ev_id

                added_sessions.append(new_session)
                print(f"  Course {new_session['course_id']} ({new_session['code']} - {new_session['title'][:30]}): ADDED on Google Calendar -> Adding to spreadsheet")
                added_to_sheet_count += 1
    except Exception as e:
        if args.verbose:
            print(f"Note: error checking for new calendar events: {e}")

    # Build the final list of sessions
    remaining_sessions = [s for s in sessions if id(s) not in deleted_sessions] + added_sessions

    has_sheet_changes = (updated_count > 0 or deleted_from_sheet_count > 0 or added_to_sheet_count > 0)
    if has_sheet_changes:
        if args.dry_run:
            print(f"\n[DRY RUN] Would update sheet '{sheet_name}' ({updated_count} updated, {deleted_from_sheet_count} deleted, {added_to_sheet_count} added).")
        else:
            print(f"\nWriting changes to sheet '{sheet_name}'...")
            calendar.set_sessions(remaining_sessions)
            calendar.update_spreadsheet(sheet_name=sheet_name, clear=True)
            print(f"Successfully updated sheet '{sheet_name}'.")
    else:
        print("\nNo changes detected on Google Calendar.")

    print(f"\nSummary for sync-from-calendar:")
    print(f"  Updated from calendar: {updated_count}")
    print(f"  Deleted from sheet (deleted from calendar): {deleted_from_sheet_count}")
    print(f"  Added to sheet (added from calendar): {added_to_sheet_count}")
    print(f"  Unchanged: {unchanged_count}")
    print(f"  Missing/No event: {missing_count}")



# ---------------------------------------------------------------------------
# Action 4: Clear Tentative Events from Google Calendar
# ---------------------------------------------------------------------------
def action_clear_calendar(args, global_config):
    sheet_name = args.sheet or global_config['google']['calendar_sheet_name']
    print(f"Action: clear-calendar (Sheet: '{sheet_name}')")

    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    except Exception as e:
        print(f"Error loading sheet '{sheet_name}': {e}")
        sys.exit(1)

    gcal, tz_name = init_gcal(global_config, args)
    sessions = calendar.get_all_sessions()
    print(f"Clearing tentative events from private Google Calendar for sheet '{sheet_name}'...")

    deleted_count = 0
    cleared_sheet_ids = 0
    seen_event_ids = set()

    # Delete tentative events referenced by private_gcal_id in the sheet
    for session in sessions:
        gcal_id = session.get('private_gcal_id')
        if not gcal_id:
            continue

        ev = None
        try:
            ev = gcal.get_event(gcal_id)
        except Exception:
            pass

        if ev:
            is_tentative = (
                '[TENTATIVE]' in (ev.get('summary') or '') or
                ev.get('status') == 'tentative' or
                ev.get('extendedProperties', {}).get('private', {}).get('tentative') == 'true'
            )
            if not is_tentative and not getattr(args, 'force', False):
                print(
                    f"  Skipping event {gcal_id} (Course {session.get('course_id')}, '{ev.get('summary')}'): "
                    "Not a tentative event. (Use --force to delete anyway)"
                )
                continue

        if gcal_id not in seen_event_ids:
            seen_event_ids.add(gcal_id)
            if args.dry_run:
                print(f"  [DRY RUN] Would delete event {gcal_id} (Course {session.get('course_id')})")
                deleted_count += 1
            else:
                try:
                    success = gcal.delete_event(gcal_id, send_updates="none")
                    if success:
                        deleted_count += 1
                        if args.verbose:
                            print(f"  Deleted event {gcal_id} (Course {session.get('course_id')})")
                except Exception as e:
                    print(f"  Warning: Could not delete event {gcal_id}: {e}")

        if not args.dry_run:
            session['private_gcal_id'] = ''
        cleared_sheet_ids += 1

    # In addition, search for any tentative events on Google Calendar for this sheet
    try:
        candidate_events = gcal.list_all_events(q="[TENTATIVE]")
        for ev in candidate_events:
            ev_id = ev['id']
            if ev_id in seen_event_ids:
                continue
            ext_sheet = ev.get('extendedProperties', {}).get('private', {}).get('sheet_name')
            summary = ev.get('summary', '')
            if ext_sheet == sheet_name or ('[TENTATIVE]' in summary and not ext_sheet):
                seen_event_ids.add(ev_id)
                if args.dry_run:
                    print(f"  [DRY RUN] Would delete extra tentative event {ev_id} ({summary})")
                    deleted_count += 1
                else:
                    try:
                        gcal.delete_event(ev_id, send_updates="none")
                        deleted_count += 1
                        if args.verbose:
                            print(f"  Deleted extra tentative event {ev_id} ({summary})")
                    except Exception as e:
                        print(f"  Warning: Could not delete extra event {ev_id}: {e}")
    except Exception as e:
        if args.verbose:
            print(f"Note: querying tentative events by text: {e}")

    if not args.dry_run and cleared_sheet_ids > 0:
        print(f"\nClearing private_gcal_id column in sheet '{sheet_name}'...")
        calendar.update_spreadsheet(sheet_name=sheet_name)

    print(f"\nSummary for clear-calendar:")
    print(f"  Deleted events from calendar: {deleted_count}")
    print(f"  Cleared IDs in sheet: {cleared_sheet_ids}")


# ---------------------------------------------------------------------------
# Role Summary Helpers and Action
# ---------------------------------------------------------------------------
def load_trainers(global_config, args):
    """
    Attempts to load the Trainers database from global_config and args/secrets_dir.
    Returns a Trainers instance or None if not found/error.
    """
    try:
        trainers_db = global_config.get('global', 'trainers_db', fallback=None)
    except Exception:
        trainers_db = None
    if not trainers_db:
        return None

    secrets_dir = os.environ.get('CQORC_SECRETS_DIR', getattr(args, 'secrets_dir', './secrets'))
    candidate_paths = [
        trainers_db,
        os.path.join(secrets_dir, os.path.basename(trainers_db)),
        os.path.join(getattr(args, 'config_dir', '.'), trainers_db),
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                return Trainers(p)
            except Exception as e:
                if getattr(args, 'verbose', False):
                    print(f"Warning: could not load trainers database from '{p}': {e}")
                return None
    return None


def get_trainer_info(trainers, key):
    """
    Looks up trainer in Trainers database by exact match or case-insensitive match.
    Returns (fullname, home_institution). Falls back to (key, '').
    """
    if not trainers or not key:
        return key, ''

    # Exact match
    try:
        fn = trainers.fullname(key).strip()
        inst = trainers.home_institution(key).strip()
        return fn, inst
    except (KeyError, Exception):
        pass

    # Case-insensitive match fallback
    try:
        for k in trainers.trainers():
            if k.lower() == key.lower():
                return trainers.fullname(k).strip(), trainers.home_institution(k).strip()
    except Exception:
        pass

    return key, ''


def person_matches(trainer_key, name_arg, trainers):
    """
    Returns True if trainer_key refers to the same person as name_arg.
    Matches by trainer database key (case-insensitive) or, when a trainers
    database is available, by full name (case-insensitive).
    """
    name_arg_norm = name_arg.strip().lower()
    if trainer_key.strip().lower() == name_arg_norm:
        return True
    if trainers:
        fullname, _ = get_trainer_info(trainers, trainer_key)
        if fullname.strip().lower() == name_arg_norm:
            return True
    return False


def get_trainer_email(trainers, key):
    """
    Returns the trainer's primary email address (for notifications), or ''
    if unavailable. Matches by trainer database key, case-insensitively.
    """
    if not trainers or not key:
        return ''
    try:
        return trainers.email(key)
    except Exception:
        pass
    try:
        for k in trainers.trainers():
            if k.lower() == key.strip().lower():
                return trainers.email(k)
    except Exception:
        pass
    return ''


def get_trainer_firstname(trainers, key, fallback):
    """
    Returns the trainer's first name from the trainers database (matching by
    key, case-insensitively), or the first word of `fallback` if unavailable.
    """
    if trainers and key:
        try:
            return trainers.firstname(key).strip()
        except Exception:
            pass
        try:
            for k in trainers.trainers():
                if k.lower() == key.strip().lower():
                    return trainers.firstname(k).strip()
        except Exception:
            pass
    return (fallback or '').split()[0] if fallback else fallback


def send_schedule_email(global_config, to_email, subject, body_text, html_body=None, verbose=False):
    """
    Sends an email using the Gmail SMTP credentials configured in [email]
    (user/password) -- see secrets.cfg.sample / README.md.

    body_text is always sent as the plain-text part. When html_body is also
    given, the message becomes multipart/alternative so HTML-capable clients
    render html_body instead (plain text in most email clients uses a
    proportional font, which breaks space-aligned ASCII tables).

    Returns True on success, prints an error and returns False on failure.
    """
    try:
        # Strip whitespace and any accidental surrounding quotes -- configparser
        # does not treat quotes specially, so "user = \"foo@bar.com\"" in a .cfg
        # file yields the literal quote characters in the value.
        gmail_user = global_config['email']['user'].strip().strip('"\'')
        gmail_password = global_config['email']['password'].strip().strip('"\'')
    except Exception as e:
        print(f"Error: could not read [email] user/password from configuration: {e}")
        return False

    # Optional display name shown as the sender (e.g. "Caroline Baril"), while
    # still authenticating and sending through the configured mailbox address.
    from_name = global_config['email'].get('from_name', '').strip().strip('"\'')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = formataddr((from_name, gmail_user)) if from_name else gmail_user
    msg['To'] = to_email
    msg.set_content(body_text)
    if html_body:
        msg.add_alternative(html_body, subtype='html')

    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        if verbose:
            print(f"  Email sent to {to_email}.")
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {type(e).__name__}: {e}")
        return False


def compute_role_summary(sessions, roles=None, trainers=None):
    """
    Computes summary statistics for role involvement across course sessions.

    Args:
        sessions: list of session dictionaries from Calendar/sheet.
        roles: list of role column names to inspect (default: ['instructor', 'host', 'assistants']).
        trainers: optional Trainers object to look up full names and institutions.

    Returns:
        dict with:
            'roles': list of role names
            'person_stats': dict of person_key -> dict of statistics
            'role_totals': dict of role -> total assignment count
            'total_assignments': int
            'unassigned': dict of role -> count of sessions with no one assigned
            'total_sessions': int (valid non-empty course sessions)
    """
    if roles is None:
        roles = ['instructor', 'host', 'assistants']
    else:
        roles = [r.strip().lower() for r in roles if r.strip()]

    stats = {}
    unassigned = {r: 0 for r in roles}
    role_totals = {r: 0 for r in roles}
    total_sessions = 0

    for s in sessions:
        cid = (s.get('course_id') or '').strip()
        title = (s.get('title') or '').strip()
        sdate = (s.get('start_date') or '').strip()
        # Skip completely blank or placeholder instruction rows
        if not cid and not title and not sdate:
            continue

        total_sessions += 1

        h_str = s.get('hours') or '0'
        try:
            h_val = float(str(h_str).replace(',', '.'))
        except (ValueError, TypeError):
            h_val = 0.0

        for r in roles:
            val = s.get(r) or ''
            people = [p.strip() for p in val.split(',') if p.strip()]
            # Deduplicate per session while preserving order
            seen_people = []
            for p in people:
                if p not in seen_people:
                    seen_people.append(p)

            if not seen_people:
                unassigned[r] += 1
            else:
                role_totals[r] += len(seen_people)
                for p in seen_people:
                    if p not in stats:
                        fullname, inst = get_trainer_info(trainers, p)
                        stats[p] = {
                            'key': p,
                            'fullname': fullname,
                            'institution': inst,
                            'roles': {role: 0 for role in roles},
                            'total_events': 0,
                            'hours_by_role': {role: 0.0 for role in roles},
                            'total_hours': 0.0
                        }
                    stats[p]['roles'][r] += 1
                    stats[p]['total_events'] += 1
                    stats[p]['hours_by_role'][r] += h_val
                    stats[p]['total_hours'] += h_val

    total_assignments = sum(role_totals.values())

    return {
        'roles': roles,
        'person_stats': stats,
        'role_totals': role_totals,
        'total_assignments': total_assignments,
        'unassigned': unassigned,
        'total_sessions': total_sessions
    }


# Valid sort keys (role names are added dynamically when validating)
SORT_BY_STATIC_KEYS = ["total", "hours", "name", "key", "institution"]


def get_valid_sort_keys(roles):
    """Return all valid --sort-by values given the active role list."""
    return SORT_BY_STATIC_KEYS + list(roles)


def validate_sort_by(sort_by, roles):
    """
    Validate the --sort-by argument. Exits with a helpful message on failure.
    Returns the normalised (lower-cased) sort key.
    """
    sort_by_norm = (sort_by or "total").lower()
    valid = get_valid_sort_keys(roles)
    if sort_by_norm not in valid:
        print(
            f"Error: invalid --sort-by value '{sort_by}'.\n"
            f"Valid options are: {', '.join(valid)}"
        )
        sys.exit(1)
    return sort_by_norm


def sort_summary_items(person_stats_list, sort_by="total", roles=None, by_hours=False):
    """
    Sorts a list of person_stats dicts according to sort_by criterion.

    When by_hours=True the primary numeric key for role-based and 'total'
    sorts switches from event count to hours so the display order matches
    the metric being shown.
    """
    sort_by = (sort_by or "total").lower()
    roles = roles or ['instructor', 'host', 'assistants']

    if sort_by in roles:
        if by_hours:
            return sorted(
                person_stats_list,
                key=lambda x: (-x['hours_by_role'].get(sort_by, 0.0), -x['total_hours'], x['fullname'].lower())
            )
        return sorted(
            person_stats_list,
            key=lambda x: (-x['roles'].get(sort_by, 0), -x['total_events'], x['fullname'].lower())
        )
    elif sort_by in ("hours", "total_hours"):
        return sorted(
            person_stats_list,
            key=lambda x: (-x['total_hours'], -x['total_events'], x['fullname'].lower())
        )
    elif sort_by in ("name", "fullname"):
        return sorted(
            person_stats_list,
            key=lambda x: (x['fullname'].lower(), x['key'].lower())
        )
    elif sort_by == "key":
        return sorted(
            person_stats_list,
            key=lambda x: x['key'].lower()
        )
    elif sort_by == "institution":
        return sorted(
            person_stats_list,
            key=lambda x: (
                x['institution'].lower(),
                -(x['total_hours'] if by_hours else x['total_events']),
                x['fullname'].lower()
            )
        )
    else:  # default "total"
        if by_hours:
            return sorted(
                person_stats_list,
                key=lambda x: (-x['total_hours'], -x['total_events'], x['fullname'].lower())
            )
        return sorted(
            person_stats_list,
            key=lambda x: (-x['total_events'], -x['total_hours'], x['fullname'].lower())
        )


def build_summary_table_data(summary_data, sort_by="total", by_hours=False):
    """
    Converts summary_data into (header, rows, totals_row, unassigned_row).
    """
    roles = summary_data['roles']
    person_stats = summary_data['person_stats']
    role_totals = summary_data['role_totals']
    unassigned = summary_data['unassigned']

    grand_total_hours = sum(item['total_hours'] for item in person_stats.values())
    sorted_stats = sort_summary_items(list(person_stats.values()), sort_by=sort_by, roles=roles, by_hours=by_hours)

    if by_hours:
        role_headers = [f"{r.capitalize()} (hrs)" for r in roles]
        header = ['Key', 'Full Name', 'Institution'] + role_headers + ['Total Hours', 'Total Events']

        rows = []
        for item in sorted_stats:
            row = [item['key'], item['fullname'], item['institution']]
            for r in roles:
                row.append(f"{item['hours_by_role'].get(r, 0.0):g}")
            row.append(f"{item['total_hours']:g}")
            row.append(str(item['total_events']))
            rows.append(row)

        totals_row = ['TOTALS', '', '']
        for r in roles:
            tot_h = sum(item['hours_by_role'].get(r, 0.0) for item in person_stats.values())
            totals_row.append(f"{tot_h:g}")
        totals_row.append(f"{grand_total_hours:g}")
        totals_row.append(str(summary_data['total_assignments']))

        unassigned_row = ['UNASSIGNED', '(sessions missing role)', '']
        for r in roles:
            unassigned_row.append(str(unassigned.get(r, 0)))
        unassigned_row.append('')
        unassigned_row.append('')
    else:
        role_headers = [r.capitalize() for r in roles]
        header = ['Key', 'Full Name', 'Institution'] + role_headers + ['Total Events', 'Total Hours']

        rows = []
        for item in sorted_stats:
            row = [item['key'], item['fullname'], item['institution']]
            for r in roles:
                row.append(str(item['roles'].get(r, 0)))
            row.append(str(item['total_events']))
            row.append(f"{item['total_hours']:g}")
            rows.append(row)

        totals_row = ['TOTALS', '', '']
        for r in roles:
            totals_row.append(str(role_totals.get(r, 0)))
        totals_row.append(str(summary_data['total_assignments']))
        totals_row.append(f"{grand_total_hours:g}")

        unassigned_row = ['UNASSIGNED', '(sessions missing role)', '']
        for r in roles:
            unassigned_row.append(str(unassigned.get(r, 0)))
        unassigned_row.append('')
        unassigned_row.append('')

    return header, rows, totals_row, unassigned_row


# ---------------------------------------------------------------------------
# Institution Grouping
# ---------------------------------------------------------------------------

def build_institution_map(summary_data):
    """
    Groups person_stats by institution.
    Returns a dict: institution -> {'people': [...], 'hours_by_role': {...},
    'total_hours': float, 'total_events': int}, ordered by descending total
    hours then alphabetically by institution name.
    """
    roles = summary_data['roles']
    person_stats = summary_data['person_stats']

    raw = {}
    for p in person_stats.values():
        inst = (p.get('institution') or 'Unspecified').strip() or 'Unspecified'
        if inst not in raw:
            raw[inst] = {
                'institution': inst,
                'people': [],
                'hours_by_role': {r: 0.0 for r in roles},
                'total_hours': 0.0,
                'total_events': 0,
            }
        raw[inst]['people'].append(p)
        raw[inst]['total_hours'] += p['total_hours']
        raw[inst]['total_events'] += p['total_events']
        for r in roles:
            raw[inst]['hours_by_role'][r] += p['hours_by_role'].get(r, 0.0)

    return dict(
        sorted(raw.items(), key=lambda kv: (-kv[1]['total_hours'], kv[0].lower()))
    )


def build_institution_grouped_table_data(summary_data, sort_by="total", by_hours=False):
    """
    Builds a grouped-by-institution table.  Each institution block shows its
    individual trainers (sorted by sort_by) followed by a subtotal row.

    Returns (header, blocks, grand_totals_row) where blocks is a list of
    (institution_label, person_rows, subtotals_row) tuples.  Column layout
    always shows hours (most informative for the grouped view) plus an
    institution share column.
    """
    roles = summary_data['roles']
    person_stats = summary_data['person_stats']
    inst_map = build_institution_map(summary_data)

    grand_total_hours = sum(item['total_hours'] for item in person_stats.values())
    grand_total_events = sum(item['total_events'] for item in person_stats.values())
    grand_role_hours = {r: sum(p['hours_by_role'].get(r, 0.0) for p in person_stats.values()) for r in roles}

    role_headers = [f"{r.capitalize()} (hrs)" for r in roles]
    header = ['Institution / Trainer', 'Key'] + role_headers + ['Total Hours', 'Total Events', '% of Hours']

    blocks = []
    for inst, entry in inst_map.items():
        inst_pct = (entry['total_hours'] / grand_total_hours * 100) if grand_total_hours > 0 else 0.0

        sorted_people = sort_summary_items(entry['people'], sort_by=sort_by, roles=roles, by_hours=by_hours)

        person_rows = []
        for p in sorted_people:
            p_pct = (p['total_hours'] / grand_total_hours * 100) if grand_total_hours > 0 else 0.0
            row = [f"  {p['fullname']}", p['key']]
            for r in roles:
                row.append(f"{p['hours_by_role'].get(r, 0.0):g}")
            row.append(f"{p['total_hours']:g}")
            row.append(str(p['total_events']))
            row.append(f"{p_pct:.1f}%")
            person_rows.append(row)

        n = len(entry['people'])
        subtotals_row = [f"  Subtotal {inst} ({n} trainer{'s' if n != 1 else ''})", '']
        for r in roles:
            subtotals_row.append(f"{entry['hours_by_role'][r]:g}")
        subtotals_row.append(f"{entry['total_hours']:g}")
        subtotals_row.append(str(entry['total_events']))
        subtotals_row.append(f"{inst_pct:.1f}%")

        blocks.append((inst, person_rows, subtotals_row))

    grand_totals_row = [f"GRAND TOTAL ({len(person_stats)} trainers)", '']
    for r in roles:
        grand_totals_row.append(f"{grand_role_hours[r]:g}")
    grand_totals_row.append(f"{grand_total_hours:g}")
    grand_totals_row.append(str(grand_total_events))
    grand_totals_row.append("100.0%")

    return header, blocks, grand_totals_row


def format_institution_grouped_text_table(header, blocks, grand_totals_row, title=None):
    """
    Formats the institution-grouped summary as an ASCII text table.
    Institution names appear as section banners; person rows are indented.
    """
    all_rows = [header]
    for _inst, person_rows, subtotals_row in blocks:
        all_rows.extend(person_rows)
        all_rows.append(subtotals_row)
    all_rows.append(grand_totals_row)

    col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(header))]

    fmt_parts = []
    for i, w in enumerate(col_widths):
        if i < 2:
            fmt_parts.append(f"{{:<{w}}}")
        else:
            fmt_parts.append(f"{{:>{w}}}")
    fmt = "  ".join(fmt_parts)

    total_width = sum(col_widths) + 2 * (len(col_widths) - 1)
    sep = "  ".join(["-" * w for w in col_widths])

    lines = []
    if title:
        lines.append(title)
        lines.append("=" * max(len(title), total_width))

    lines.append(fmt.format(*header))
    lines.append(sep)

    for inst, person_rows, subtotals_row in blocks:
        lines.append(f"[ {inst} ]")
        for row in person_rows:
            lines.append(fmt.format(*row))
        lines.append(fmt.format(*subtotals_row))
        lines.append(sep)

    lines.append(fmt.format(*grand_totals_row))
    lines.append("=" * total_width)
    return "\n".join(lines)


def format_institution_grouped_csv(header, blocks, grand_totals_row):
    """Formats the institution-grouped summary as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for inst, person_rows, subtotals_row in blocks:
        writer.writerow([f"[ {inst} ]"] + [''] * (len(header) - 1))
        for row in person_rows:
            writer.writerow(row)
        writer.writerow(subtotals_row)
    writer.writerow(grand_totals_row)
    return output.getvalue()


def format_summary_text_table(header, rows, totals_row, unassigned_row, title=None):
    """
    Formats the summary data as an ASCII/text table.
    """
    all_rows = [header] + rows + [totals_row, unassigned_row]
    col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(header))]

    # Right-align numeric columns (starting from index 3)
    fmt_parts = []
    for i, w in enumerate(col_widths):
        if i >= 3:
            fmt_parts.append(f"{{:>{w}}}")
        else:
            fmt_parts.append(f"{{:<{w}}}")
    fmt = "  ".join(fmt_parts)

    total_width = sum(col_widths) + 2 * (len(col_widths) - 1)
    lines = []
    if title:
        lines.append(title)
        lines.append("=" * max(len(title), total_width))

    lines.append(fmt.format(*header))
    lines.append("  ".join(["-" * w for w in col_widths]))

    for r in rows:
        lines.append(fmt.format(*r))

    lines.append("  ".join(["-" * w for w in col_widths]))
    lines.append(fmt.format(*totals_row))
    lines.append(fmt.format(*unassigned_row))
    lines.append("=" * total_width)

    return "\n".join(lines)


def format_summary_csv(header, rows, totals_row, unassigned_row):
    """
    Formats the summary data as CSV text.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    writer.writerow(totals_row)
    writer.writerow(unassigned_row)
    return output.getvalue()


def action_summary(args, global_config):
    """
    Action: create a summary of how many times each person is involved for each type
    of role over the course of a session.  Supports flat and institution-grouped views.
    """
    sheet_name = (
        getattr(args, 'sheet', None)
        or getattr(args, 'from_sheet', None)
        or global_config['google'].get('calendar_sheet_name')
    )
    if not sheet_name:
        print("Error: --sheet must be specified (or google.calendar_sheet_name set in config).")
        sys.exit(1)

    csv_arg = getattr(args, 'csv', None)
    quiet = (csv_arg == '-')   # suppress stdout status lines when streaming CSV

    if quiet:
        sys.stderr.write(f"Loading session schedule from sheet '{sheet_name}'...\n")
    else:
        print(f"Loading session schedule from sheet '{sheet_name}'...")

    calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    sessions = calendar.get_all_sessions()
    trainers = load_trainers(global_config, args)

    roles_arg = getattr(args, 'roles', 'instructor,host,assistants')
    if isinstance(roles_arg, str):
        roles = [r.strip().lower() for r in roles_arg.split(',') if r.strip()]
    else:
        roles = list(roles_arg)

    by_hours = getattr(args, 'by_hours', False)
    sort_by_raw = getattr(args, 'sort_by', 'total')
    group_by_inst = getattr(args, 'group_by_institution', False)

    # Validate --sort-by before doing any work
    sort_by = validate_sort_by(sort_by_raw, roles)

    summary_data = compute_role_summary(sessions, roles=roles, trainers=trainers)

    title_base = f"Session '{sheet_name}' Role Involvements Summary ({summary_data['total_sessions']} sessions)"

    if group_by_inst:
        # ----------------------------------------------------------------
        # Grouped-by-institution view
        # ----------------------------------------------------------------
        g_title = title_base + " — Grouped by Institution"
        header, blocks, grand_totals_row = build_institution_grouped_table_data(
            summary_data, sort_by=sort_by, by_hours=by_hours
        )

        if quiet:
            csv_text = format_institution_grouped_csv(header, blocks, grand_totals_row)
            sys.stdout.write(csv_text)
        else:
            table_text = format_institution_grouped_text_table(header, blocks, grand_totals_row, title=g_title)
            print("\n" + table_text)

            if csv_arg:
                csv_text = format_institution_grouped_csv(header, blocks, grand_totals_row)
                try:
                    with open(csv_arg, 'w', newline='', encoding='utf-8') as f:
                        f.write(csv_text)
                    print(f"\nSummary exported to CSV file '{csv_arg}'.")
                except Exception as e:
                    print(f"\nError exporting to CSV file '{csv_arg}': {e}")

        write_sheet = getattr(args, 'write_sheet', None)
        if write_sheet and not quiet:
            target_sheet = (
                f"{sheet_name}-by-institution"
                if (write_sheet is True or not isinstance(write_sheet, str) or not write_sheet.strip())
                else write_sheet.strip()
            )
            print(f"\nWriting grouped summary to Google Sheet '{target_sheet}'...")
            try:
                if not calendar.gsheets.sheet_exists(calendar.spreadsheet_id, target_sheet):
                    if getattr(args, 'verbose', False):
                        print(f"Creating new sheet tab '{target_sheet}'...")
                    calendar.gsheets.add_sheet(calendar.spreadsheet_id, target_sheet)
                sheet_values = [header]
                for inst, person_rows, subtotals_row in blocks:
                    sheet_values.append([f"[ {inst} ]"] + [''] * (len(header) - 1))
                    sheet_values.extend(person_rows)
                    sheet_values.append(subtotals_row)
                sheet_values.append(grand_totals_row)
                calendar.gsheets.clear_values(calendar.spreadsheet_id, "A:Z", target_sheet)
                calendar.gsheets.update_values(calendar.spreadsheet_id, "A:Z", sheet_values, target_sheet)
                print(f"Successfully saved grouped summary to sheet tab '{target_sheet}'.")
            except Exception as e:
                print(f"Error writing grouped summary to Google Sheet: {e}")
    else:
        # ----------------------------------------------------------------
        # Flat (per-person) view
        # ----------------------------------------------------------------
        header, rows, totals_row, unassigned_row = build_summary_table_data(
            summary_data, sort_by=sort_by, by_hours=by_hours
        )

        if quiet:
            csv_text = format_summary_csv(header, rows, totals_row, unassigned_row)
            sys.stdout.write(csv_text)
        else:
            table_text = format_summary_text_table(header, rows, totals_row, unassigned_row, title=title_base)
            print("\n" + table_text)

            if csv_arg:
                csv_text = format_summary_csv(header, rows, totals_row, unassigned_row)
                try:
                    with open(csv_arg, 'w', newline='', encoding='utf-8') as f:
                        f.write(csv_text)
                    print(f"\nSummary exported to CSV file '{csv_arg}'.")
                except Exception as e:
                    print(f"\nError exporting to CSV file '{csv_arg}': {e}")

        write_sheet = getattr(args, 'write_sheet', None)
        if write_sheet and not quiet:
            target_sheet = (
                f"{sheet_name}-summary"
                if (write_sheet is True or not isinstance(write_sheet, str) or not write_sheet.strip())
                else write_sheet.strip()
            )
            print(f"\nWriting summary to Google Sheet '{target_sheet}'...")
            try:
                if not calendar.gsheets.sheet_exists(calendar.spreadsheet_id, target_sheet):
                    if getattr(args, 'verbose', False):
                        print(f"Creating new sheet tab '{target_sheet}'...")
                    calendar.gsheets.add_sheet(calendar.spreadsheet_id, target_sheet)
                sheet_values = [header] + rows + [totals_row, unassigned_row]
                calendar.gsheets.clear_values(calendar.spreadsheet_id, "A:Z", target_sheet)
                calendar.gsheets.update_values(calendar.spreadsheet_id, "A:Z", sheet_values, target_sheet)
                print(f"Successfully saved summary to sheet tab '{target_sheet}'.")
            except Exception as e:
                print(f"Error writing summary to Google Sheet: {e}")



# ---------------------------------------------------------------------------
# Check Conflicts Helpers and Action
# ---------------------------------------------------------------------------

def _parse_iso_to_aware(iso_str, fallback_tz=None):
    """
    Parse an ISO 8601 datetime string returned by Google APIs to a
    timezone-aware datetime object.  If the string has no offset the
    fallback_tz (a pytz timezone) is used.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
    except Exception:
        return None
    if dt.tzinfo is None and fallback_tz is not None:
        dt = fallback_tz.localize(dt)
    return dt


def intervals_overlap(start1, end1, start2, end2):
    """Return True when two half-open time intervals [start1, end1) and [start2, end2) overlap."""
    return start1 < end2 and start2 < end1


# Human-friendly French labels for role column names (e.g. 'instructor' -> 'Formateur')
ROLE_LABELS = {
    'instructor': 'Formateur',
    'host': 'Hôte',
    'assistants': 'Assistant',
}


def role_label(role):
    """Returns a human-friendly label for a role column name."""
    return ROLE_LABELS.get(role, role.capitalize())


def collect_session_assignments(sessions, roles=None):
    """
    Extract trainer assignments from sessions.

    Returns a list of dicts:
        {
            'course_id': str,
            'title': str,
            'start_date': str,       # raw value from sheet
            'end_date': str,
            'hours': str,
            'role': str,
            'trainer_key': str,
        }
    Only sessions that have both start_date and end_date are included.
    """
    if roles is None:
        roles = ['instructor', 'host', 'assistants']
    assignments = []
    for s in sessions:
        cid = (s.get('course_id') or '').strip()
        title = (s.get('title') or '').strip()
        start_date = (s.get('start_date') or '').strip()
        end_date = (s.get('end_date') or '').strip()

        if not cid and not title and not start_date:
            continue  # blank placeholder row
        if not start_date or not end_date:
            continue  # can't check conflicts without dates

        for role in roles:
            val = s.get(role) or ''
            for tk in [p.strip() for p in val.split(',') if p.strip()]:
                assignments.append({
                    'course_id': cid,
                    'title': title,
                    'start_date': start_date,
                    'end_date': end_date,
                    'hours': (s.get('hours') or '').strip(),
                    'role': role,
                    'trainer_key': tk,
                })
    return assignments


def resolve_trainer_emails(assignments, trainers, verbose=False):
    """
    Enrich assignments with trainer fullname and calendar_email.
    Returns (enriched_assignments, email_to_key_map) where:
        enriched_assignments: list of assignment dicts with 'fullname' and 'calendar_email' added
        email_to_key_map: dict {email: trainer_key}  (first key wins on collision)
    """
    enriched = []
    email_to_key = {}
    for a in assignments:
        tk = a['trainer_key']
        fullname, inst = get_trainer_info(trainers, tk)
        cal_email = ''
        if trainers:
            # Try exact match first, then case-insensitive
            resolved_key = None
            try:
                _ = trainers.fullname(tk)
                resolved_key = tk
            except Exception:
                pass
            if not resolved_key:
                try:
                    for k in trainers.trainers():
                        if k.lower() == tk.lower():
                            resolved_key = k
                            break
                except Exception:
                    pass
            if resolved_key:
                try:
                    cal_email = trainers.calendar_email(resolved_key)
                except Exception:
                    pass
        if not cal_email:
            if verbose:
                print(f"  Warning: no calendar email for trainer '{tk}', skipping conflict check for this trainer.")
        else:
            email_to_key.setdefault(cal_email, tk)
        enriched.append({**a, 'fullname': fullname, 'institution': inst, 'calendar_email': cal_email})
    return enriched, email_to_key


def query_freebusy_batched(gcal, assignments_with_email, tz_name, verbose=False):
    """
    Query FreeBusy API for all unique (session time window, email) combinations.
    Groups queries by overlapping time windows to reduce API calls.

    Returns:
        dict mapping (time_min_iso, time_max_iso) -> {email: {'busy': [...], 'errors': [...]}}
    """
    from collections import defaultdict

    tz = pytz.timezone(tz_name)

    # Group emails by their (start, end) window
    window_emails = defaultdict(set)
    for a in assignments_with_email:
        if not a['calendar_email']:
            continue
        try:
            start_dt = parse_datetime(a['start_date'])
            end_dt = parse_datetime(a['end_date'])
        except Exception:
            continue
        if not start_dt or not end_dt:
            continue
        # Localise and convert to UTC ISO
        start_aware = tz.localize(start_dt) if start_dt.tzinfo is None else start_dt
        end_aware = tz.localize(end_dt) if end_dt.tzinfo is None else end_dt
        time_min = start_aware.astimezone(pytz.utc).isoformat()
        time_max = end_aware.astimezone(pytz.utc).isoformat()
        window_emails[(time_min, time_max)].add(a['calendar_email'])

    BATCH_SIZE = 50  # Google FreeBusy supports up to ~50 items per query
    results = {}
    for (time_min, time_max), emails in window_emails.items():
        emails_list = sorted(emails)
        for i in range(0, len(emails_list), BATCH_SIZE):
            batch = emails_list[i:i + BATCH_SIZE]
            try:
                cal_data = gcal.get_freebusy(time_min, time_max, batch)
                if (time_min, time_max) not in results:
                    results[(time_min, time_max)] = {}
                results[(time_min, time_max)].update(cal_data)
                if verbose:
                    print(f"  FreeBusy queried for {len(batch)} calendar(s) in window {time_min} — {time_max}")
            except Exception as e:
                if verbose:
                    print(f"  Warning: FreeBusy query failed for window {time_min}—{time_max}: {e}")
    return results


def detect_conflicts(assignments_with_email, freebusy_results, tz_name):
    """
    Cross-reference trainer assignments against FreeBusy results.

    Returns a list of conflict dicts:
        {
            'course_id', 'title', 'start_date', 'end_date', 'hours',
            'role', 'trainer_key', 'fullname', 'institution', 'calendar_email',
            'busy_start', 'busy_end',   # strings from FreeBusy API
            'status',  # 'conflict' | 'inaccessible' | 'ok'
        }
    """
    tz = pytz.timezone(tz_name)
    utc = pytz.utc
    conflicts = []
    inaccessible = []

    for a in assignments_with_email:
        email = a.get('calendar_email', '')
        if not email:
            continue  # already warned at resolution stage

        try:
            start_dt = parse_datetime(a['start_date'])
            end_dt = parse_datetime(a['end_date'])
        except Exception:
            continue
        if not start_dt or not end_dt:
            continue

        start_aware = tz.localize(start_dt) if start_dt.tzinfo is None else start_dt.astimezone(tz)
        end_aware = tz.localize(end_dt) if end_dt.tzinfo is None else end_dt.astimezone(tz)
        time_min = start_aware.astimezone(utc).isoformat()
        time_max = end_aware.astimezone(utc).isoformat()

        cal_info = freebusy_results.get((time_min, time_max), {}).get(email)
        if cal_info is None:
            # No result at all for this email/window — query may have failed
            continue

        errors = cal_info.get('errors', [])
        if errors:
            inaccessible.append({
                **a,
                'status': 'inaccessible',
                'busy_start': '',
                'busy_end': '',
                'errors': errors,
            })
            continue

        busy_intervals = cal_info.get('busy', [])
        found_conflict = False
        for interval in busy_intervals:
            b_start = _parse_iso_to_aware(interval.get('start', ''), utc)
            b_end = _parse_iso_to_aware(interval.get('end', ''), utc)
            if b_start is None or b_end is None:
                continue
            if intervals_overlap(start_aware.astimezone(utc), end_aware.astimezone(utc), b_start, b_end):
                conflicts.append({
                    **a,
                    'status': 'conflict',
                    'busy_start': b_start.astimezone(tz).strftime('%Y-%m-%d %H:%M'),
                    'busy_end': b_end.astimezone(tz).strftime('%Y-%m-%d %H:%M'),
                })
                found_conflict = True
                # Report all overlapping intervals (a trainer could have multiple conflicts)

    return conflicts, inaccessible


def format_conflicts_text_table(conflicts, inaccessible, tz_name):
    """
    Formats conflict and inaccessible-calendar results as a human-readable ASCII table.
    """
    lines = []

    if conflicts:
        header = ['Date', 'Course', 'Title', 'Role', 'Trainer', 'Session Time', 'Busy Interval']
        rows = []
        for c in conflicts:
            try:
                start_dt = parse_datetime(c['start_date'])
                end_dt = parse_datetime(c['end_date'])
                session_time = f"{start_dt.strftime('%H:%M')} – {end_dt.strftime('%H:%M')}" if start_dt and end_dt else ''
                date_str = start_dt.strftime('%Y-%m-%d') if start_dt else c['start_date']
            except Exception:
                session_time = f"{c['start_date']} – {c['end_date']}"
                date_str = c['start_date']
            rows.append([
                date_str,
                c['course_id'],
                (c['title'] or '')[:40],
                c['role'],
                c['fullname'] or c['trainer_key'],
                session_time,
                f"{c['busy_start']} – {c['busy_end']}",
            ])

        all_rows = [header] + rows
        col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(header))]
        fmt = '  '.join(f'{{:<{w}}}' for w in col_widths)
        sep = '  '.join('-' * w for w in col_widths)
        total_width = sum(col_widths) + 2 * (len(col_widths) - 1)

        title = f"⚠  SCHEDULING CONFLICTS ({len(conflicts)} found)"
        lines.append(title)
        lines.append('=' * max(len(title), total_width))
        lines.append(fmt.format(*header))
        lines.append(sep)
        for r in rows:
            lines.append(fmt.format(*r))
        lines.append('=' * max(len(title), total_width))
    else:
        lines.append("No scheduling conflicts found.")

    if inaccessible:
        lines.append('')
        lines.append(f"Calendars inaccessible (no free/busy data): {len(inaccessible)}")
        seen = set()
        for c in inaccessible:
            key = (c['trainer_key'], c['calendar_email'])
            if key not in seen:
                seen.add(key)
                err_msg = '; '.join(e.get('reason', str(e)) for e in c.get('errors', []))
                lines.append(f"  {c['fullname'] or c['trainer_key']} <{c['calendar_email']}>: {err_msg}")

    return '\n'.join(lines)


def format_conflicts_csv(conflicts, inaccessible):
    """
    Formats conflict and inaccessible-calendar results as CSV.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Status', 'Date', 'Course ID', 'Title', 'Role', 'Trainer Key',
                     'Trainer Name', 'Institution', 'Calendar Email',
                     'Session Start', 'Session End', 'Busy Start', 'Busy End'])
    for c in conflicts:
        writer.writerow([
            'conflict',
            c['start_date'].split(' ')[0] if c['start_date'] else '',
            c['course_id'],
            c['title'],
            c['role'],
            c['trainer_key'],
            c['fullname'] or c['trainer_key'],
            c.get('institution', ''),
            c['calendar_email'],
            c['start_date'],
            c['end_date'],
            c['busy_start'],
            c['busy_end'],
        ])
    for c in inaccessible:
        err_msg = '; '.join(e.get('reason', str(e)) for e in c.get('errors', []))
        writer.writerow([
            'inaccessible',
            c['start_date'].split(' ')[0] if c['start_date'] else '',
            c['course_id'],
            c['title'],
            c['role'],
            c['trainer_key'],
            c['fullname'] or c['trainer_key'],
            c.get('institution', ''),
            c['calendar_email'],
            c['start_date'],
            c['end_date'],
            '',
            '',
        ])
    return output.getvalue()


def action_check_conflicts(args, global_config):
    """
    Action: fetch trainer free/busy data from Google Calendar, compare against
    session assignments, and report potential scheduling conflicts.
    """
    sheet_name = (
        getattr(args, 'sheet', None)
        or global_config['google'].get('calendar_sheet_name')
    )
    if not sheet_name:
        print("Error: --sheet must be specified (or google.calendar_sheet_name set in config).")
        sys.exit(1)

    roles_arg = getattr(args, 'roles', 'instructor,host,assistants')
    roles = [r.strip().lower() for r in roles_arg.split(',') if r.strip()]
    csv_arg = getattr(args, 'csv', None)
    quiet = (csv_arg == '-')
    verbose = getattr(args, 'verbose', False)

    if not quiet:
        print(f"Action: check-conflicts (Sheet: '{sheet_name}', Roles: {', '.join(roles)})")

    # Load sheet sessions
    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    except Exception as e:
        print(f"Error loading sheet '{sheet_name}': {e}")
        sys.exit(1)

    sessions = calendar.get_all_sessions()
    if not quiet:
        print(f"Loaded {len(sessions)} session rows from sheet '{sheet_name}'.")

    # Load trainers DB for calendar email lookup
    trainers = load_trainers(global_config, args)
    if not trainers and not quiet:
        print("Warning: trainers database not found; trainer name/email resolution will be limited.")

    # Collect assignments
    assignments = collect_session_assignments(sessions, roles=roles)
    if not quiet:
        print(f"Found {len(assignments)} trainer-role assignments to check.")

    if not assignments:
        print("No assignments found to check for conflicts.")
        return

    # Enrich with calendar emails
    assignments_with_email, _ = resolve_trainer_emails(assignments, trainers, verbose=verbose)

    checkable = [a for a in assignments_with_email if a['calendar_email']]
    if not quiet:
        no_email = len(assignments_with_email) - len(checkable)
        if no_email:
            print(f"  {no_email} assignment(s) have no calendar email and will be skipped.")
        print(f"  Querying FreeBusy data for {len(checkable)} assignment(s) across "
              f"{len({a['calendar_email'] for a in checkable})} unique trainer calendar(s)...")

    # Init Google Calendar interface
    gcal, tz_name = init_gcal(global_config, args)

    # Query FreeBusy API (batched)
    freebusy_results = query_freebusy_batched(gcal, checkable, tz_name, verbose=verbose)

    # Detect conflicts
    conflicts, inaccessible = detect_conflicts(assignments_with_email, freebusy_results, tz_name)

    # Output
    if quiet:
        sys.stdout.write(format_conflicts_csv(conflicts, inaccessible))
    else:
        print()
        print(format_conflicts_text_table(conflicts, inaccessible, tz_name))

        if csv_arg:
            csv_text = format_conflicts_csv(conflicts, inaccessible)
            try:
                with open(csv_arg, 'w', newline='', encoding='utf-8') as f:
                    f.write(csv_text)
                print(f"\nConflict report exported to '{csv_arg}'.")
            except Exception as e:
                print(f"\nError writing CSV file '{csv_arg}': {e}")

        print(f"\nSummary for check-conflicts:")
        print(f"  Assignments checked: {len(checkable)}")
        print(f"  Conflicts found:     {len(conflicts)}")
        print(f"  Inaccessible calendars: {len({c['calendar_email'] for c in inaccessible})}")


# ---------------------------------------------------------------------------
# Action: Person Schedule
# ---------------------------------------------------------------------------
def build_person_schedule_table_data(assignments):
    """
    Converts a list of assignment dicts (from collect_session_assignments,
    already filtered down to a single person) into (header, rows), sorted
    chronologically by start date.
    """
    header = ['Date', 'Titre', 'Rôle']
    rows = []
    for a in sorted(assignments, key=lambda x: (x['start_date'], x['course_id'])):
        try:
            dt = parse_datetime(a['start_date'])
        except Exception:
            dt = None
        date_str = dt.strftime('%Y-%m-%d') if dt else a['start_date']
        rows.append([date_str, (a['title'] or '')[:70], role_label(a['role'])])
    return header, rows


def group_assignments_by_person(assignments, trainers=None):
    """
    Groups assignments by trainer_key.

    Returns a list of (display_name, trainer_key, assignments_for_person)
    tuples, sorted alphabetically by display name (case-insensitive).
    display_name is the trainer's full name when available in the trainers
    database, otherwise the raw trainer_key.
    """
    groups = {}
    for a in assignments:
        groups.setdefault(a['trainer_key'], []).append(a)

    result = []
    for tk, items in groups.items():
        fullname, _ = get_trainer_info(trainers, tk)
        display_name = fullname if fullname and fullname != tk else tk
        result.append((display_name, tk, items))

    result.sort(key=lambda x: x[0].lower())
    return result


def format_person_schedule_text_table(header, rows, title=None):
    """
    Formats the person-schedule data as an ASCII text table.
    """
    all_rows = [header] + rows
    col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(header))]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    total_width = sum(col_widths) + 2 * (len(col_widths) - 1)

    lines = []
    if title:
        lines.append(title)
        lines.append("=" * max(len(title), total_width))

    lines.append(fmt.format(*header))
    lines.append("  ".join(["-" * w for w in col_widths]))
    for r in rows:
        lines.append(fmt.format(*r))
    lines.append("=" * total_width)
    return "\n".join(lines)


def format_person_schedule_csv(header, rows):
    """Formats a single person's schedule data as CSV text."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    return output.getvalue()


def format_person_schedule_html_table(header, rows):
    """
    Formats a single person's schedule data as an HTML table, with inline
    styles so it renders consistently in email clients (which generally
    render plain text in a proportional font, breaking space-aligned ASCII
    tables, and often strip <style> blocks).
    """
    cell_style = "border:1px solid #ccc;padding:6px 10px;text-align:left;"
    head_style = cell_style + "background:#f0f0f0;font-weight:bold;"

    thead = "".join(f'<th style="{head_style}">{html.escape(str(h))}</th>' for h in header)
    body_rows = []
    for r in rows:
        cells = "".join(f'<td style="{cell_style}">{html.escape(str(c))}</td>' for c in r)
        body_rows.append(f"<tr>{cells}</tr>")

    return (
        '<table style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;">'
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def format_all_person_schedules_csv(groups):
    """
    Formats per-person schedule groups (from group_assignments_by_person) as
    a single CSV, with a '[ Name ]' banner row and its own header before
    each person's block, and a blank row separating people.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    header = ['Date', 'Titre', 'Rôle']
    for i, (display_name, _tk, items) in enumerate(groups):
        if i > 0:
            writer.writerow([])
        writer.writerow([f"[ {display_name} ]"] + [''] * (len(header) - 1))
        writer.writerow(header)
        _, rows = build_person_schedule_table_data(items)
        for r in rows:
            writer.writerow(r)
    return output.getvalue()


def action_person_schedule(args, global_config):
    """
    Action: build a table of every session a given person is involved in
    (as instructor/trainer, host, or assistant), showing the date, course
    and role held for each.
    """
    sheet_name = (
        getattr(args, 'sheet', None)
        or global_config['google'].get('calendar_sheet_name')
    )
    if not sheet_name:
        print("Error: --sheet must be specified (or google.calendar_sheet_name set in config).")
        sys.exit(1)

    name_arg = getattr(args, 'name', None)
    email_requested = getattr(args, 'email', False)
    if email_requested and not name_arg:
        print("Error: --email requires --name (pick a single trainer to email their schedule to).")
        sys.exit(1)

    roles_arg = getattr(args, 'roles', 'instructor,host,assistants')
    roles = [r.strip().lower() for r in roles_arg.split(',') if r.strip()]
    csv_arg = getattr(args, 'csv', None)
    quiet = (csv_arg == '-')   # suppress stdout status lines when streaming CSV

    if not quiet:
        who = f"Name: '{name_arg}'" if name_arg else "all trainers"
        print(f"Action: person-schedule (Sheet: '{sheet_name}', {who})")

    try:
        calendar = CQORCcalendar.Calendar(global_config, args, sheet_name=sheet_name)
    except Exception as e:
        print(f"Error loading sheet '{sheet_name}': {e}")
        sys.exit(1)

    sessions = calendar.get_all_sessions()
    trainers = load_trainers(global_config, args)

    assignments = collect_session_assignments(sessions, roles=roles)

    if name_arg:
        # Single person: one table.
        matches = [a for a in assignments if person_matches(a['trainer_key'], name_arg, trainers)]
        if not matches:
            print(f"No sessions found for '{name_arg}' in sheet '{sheet_name}'.")
            return
        fullname, _ = get_trainer_info(trainers, matches[0]['trainer_key'])
        display_name = fullname if fullname and fullname != matches[0]['trainer_key'] else name_arg
        groups = [(display_name, matches[0]['trainer_key'], matches)]
    else:
        # No --name: everyone, as independent tables.
        if not assignments:
            print(f"No assignments found in sheet '{sheet_name}'.")
            return
        groups = group_assignments_by_person(assignments, trainers)

    if quiet:
        sys.stdout.write(format_all_person_schedules_csv(groups))
    else:
        for display_name, _tk, items in groups:
            header, rows = build_person_schedule_table_data(items)
            title = f"Horaire de {display_name} — Feuille « {sheet_name} » ({len(rows)} séance{'s' if len(rows) != 1 else ''})"
            print("\n" + format_person_schedule_text_table(header, rows, title=title))

        if csv_arg:
            csv_text = format_all_person_schedules_csv(groups)
            try:
                with open(csv_arg, 'w', newline='', encoding='utf-8') as f:
                    f.write(csv_text)
                print(f"\nSchedule exported to CSV file '{csv_arg}'.")
            except Exception as e:
                print(f"\nError exporting to CSV file '{csv_arg}': {e}")

    if email_requested:
        display_name, trainer_key, items = groups[0]
        to_email = get_trainer_email(trainers, trainer_key)
        if not to_email:
            print(f"Error: no email address found for '{display_name}' in the trainers database.")
            sys.exit(1)

        header, rows = build_person_schedule_table_data(items)
        table_text = format_person_schedule_text_table(header, rows)
        table_html = format_person_schedule_html_table(header, rows)
        firstname = get_trainer_firstname(trainers, trainer_key, display_name)
        intro = (
            "Tu trouveras ton horaire de formation dans le tableau plus bas. "
            "Pour t'aider, tu peux utiliser l'agenda « Formations CQ - Privé » "
            "dans ton calendrier Google où un horaire tentatif y a été créé. "
            "STP me contacter par Slack pour me dire si tout est beau ou s'il "
            "y a un conflit avec ton horaire."
        )
        footer = "(Ceci est un message envoyé par un script automatisé)"
        body_text = (
            f"Bonjour {firstname},\n\n"
            f"{intro}\n\n"
            f"{table_text}\n\n"
            f"{footer}\n"
        )
        body_html = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;">'
            f"<p>Bonjour {html.escape(firstname)},</p>"
            f"<p>{html.escape(intro)}</p>"
            f"{table_html}"
            f'<p style="color:#666;font-size:12px;">{html.escape(footer)}</p>'
            "</div>"
        )
        subject = f"Horaire — Session {sheet_name}"

        print(f"\nEnvoi de l'horaire par courriel à {display_name} <{to_email}>...")
        if send_schedule_email(global_config, to_email, subject, body_text, html_body=body_html, verbose=getattr(args, 'verbose', False)):
            print(f"Courriel envoyé à {to_email}.")
        else:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Manage session training schedules and Google Calendar synchronization."
    )
    # Global options / Top-level fallback flags
    parser.add_argument(
        "--action",
        choices=["create-sheet", "sync-to-calendar", "sync-from-calendar", "clear-calendar", "summary", "role-summary", "roles-summary", "check-conflicts", "person-schedule"],
        help="Action to execute (create-sheet, sync-to-calendar, sync-from-calendar, clear-calendar, summary, check-conflicts, person-schedule)"
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Sheet name to operate on (for calendar and summary actions)"
    )
    parser.add_argument(
        "--from",
        dest="from_sheet",
        default=None,
        help="Source sheet name (e.g. A26) for create-sheet"
    )
    parser.add_argument(
        "--to",
        dest="to_sheet",
        default=None,
        help="Target sheet name to create (e.g. H27) for create-sheet"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite target sheet if it already exists (create-sheet)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force recreating events even if gcal ID is already set (sync-to-calendar)"
    )
    parser.add_argument(
        "--roles",
        default="instructor,host,assistants",
        help="Comma-separated roles for summary (default: instructor,host,assistants)"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Trainer key or full name to look up (person-schedule)"
    )
    parser.add_argument(
        "--email",
        action="store_true",
        default=False,
        help="Email the schedule to the trainer's own address (person-schedule; requires --name)"
    )
    parser.add_argument(
        "--sort-by",
        default="total",
        help="Sort summary by: total, hours, name, key, institution, or any role name (default: total)"
    )
    parser.add_argument(
        "--by-hours",
        action="store_true",
        default=False,
        help="Display breakdown of hours instead of event counts in the summary; when combined with --sort-by, sorts by hours"
    )
    parser.add_argument(
        "--group-by-institution",
        action="store_true",
        default=False,
        help="Group summary output by institution with subtotals (always shows hours breakdown)"
    )
    parser.add_argument(
        "--write-sheet",
        nargs="?",
        const=True,
        default=None,
        help="Write summary table to Google Sheet (optional sheet name; defaults to <sheet>-summary or <sheet>-by-institution when grouped)"
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Export summary table to CSV file (or '-' for stdout)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform a dry run without modifying Google Sheets or Calendar"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print detailed progress"
    )
    parser.add_argument(
        "--config_dir",
        default=".",
        help="Directory that holds configuration files (default: .)"
    )
    parser.add_argument(
        "--secrets_dir",
        default="./secrets",
        help="Directory that holds secrets files (default: ./secrets)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="subcommand", help="Available actions")

    # Subcommand: create-sheet
    p_create = subparsers.add_parser("create-sheet", help="Create a new schedule sheet from an existing session")
    p_create.add_argument("--from", dest="from_sheet", default=None, help="Source sheet name (e.g. A26)")
    p_create.add_argument("--to", dest="to_sheet", required=True, help="Target sheet name (e.g. H27)")
    p_create.add_argument("--overwrite", action="store_true", default=False, help="Overwrite target sheet if exists")
    p_create.add_argument("--dry-run", action="store_true", default=False, help="Dry run")
    p_create.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_create.add_argument("--config_dir", default=".", help="Config dir")
    p_create.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: sync-to-calendar
    p_to_cal = subparsers.add_parser("sync-to-calendar", help="Synchronize sheet sessions to private Google Calendar as tentative events")
    p_to_cal.add_argument("--sheet", default=None, help="Sheet name (default: calendar_sheet_name in config)")
    p_to_cal.add_argument("--force", action="store_true", default=False, help="Force recreating events")
    p_to_cal.add_argument("--dry-run", action="store_true", default=False, help="Dry run")
    p_to_cal.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_to_cal.add_argument("--config_dir", default=".", help="Config dir")
    p_to_cal.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: sync-from-calendar
    p_from_cal = subparsers.add_parser("sync-from-calendar", help="Synchronize moved events from Google Calendar back to spreadsheet")
    p_from_cal.add_argument("--sheet", default=None, help="Sheet name (default: calendar_sheet_name in config)")
    p_from_cal.add_argument("--dry-run", action="store_true", default=False, help="Dry run")
    p_from_cal.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_from_cal.add_argument("--config_dir", default=".", help="Config dir")
    p_from_cal.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: clear-calendar
    p_clear = subparsers.add_parser("clear-calendar", help="Clear tentative events from private Google Calendar")
    p_clear.add_argument("--sheet", default=None, help="Sheet name (default: calendar_sheet_name in config)")
    p_clear.add_argument("--force", action="store_true", default=False, help="Force deleting events even if not marked tentative")
    p_clear.add_argument("--dry-run", action="store_true", default=False, help="Dry run")
    p_clear.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_clear.add_argument("--config_dir", default=".", help="Config dir")
    p_clear.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: summary
    p_summary = subparsers.add_parser(
        "summary",
        aliases=["role-summary", "roles-summary"],
        help="Summary of how many times each person is involved for each type of role over the course of a session"
    )
    p_summary.add_argument("--sheet", default=None, help="Sheet name to summarize (e.g. A26; default: calendar_sheet_name in config)")
    p_summary.add_argument("--roles", default="instructor,host,assistants", help="Comma-separated roles (default: instructor,host,assistants)")
    p_summary.add_argument(
        "--sort-by", default="total",
        help="Sort by: total, hours, name, key, institution, or any role name (default: total)"
    )
    p_summary.add_argument("--by-hours", action="store_true", default=False, help="Display breakdown of hours instead of event counts; when combined with --sort-by, sorts by hours")
    p_summary.add_argument(
        "--group-by-institution", action="store_true", default=False,
        help="Group output by institution with subtotals and a grand total (always shows hours breakdown)"
    )
    p_summary.add_argument("--write-sheet", nargs="?", const=True, default=None, help="Write summary table to Google Sheet (optional sheet name; defaults to <sheet>-summary or <sheet>-by-institution when grouped)")
    p_summary.add_argument("--csv", default=None, help="Export summary table to CSV file (or '-' for stdout)")
    p_summary.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_summary.add_argument("--config_dir", default=".", help="Config dir")
    p_summary.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: check-conflicts
    p_conflicts = subparsers.add_parser(
        "check-conflicts",
        help="Fetch trainer free/busy data from Google Calendar and report scheduling conflicts"
    )
    p_conflicts.add_argument("--sheet", default=None, help="Sheet name (default: calendar_sheet_name in config)")
    p_conflicts.add_argument("--roles", default="instructor,host,assistants", help="Comma-separated roles to check (default: instructor,host,assistants)")
    p_conflicts.add_argument("--csv", default=None, help="Export conflict report to CSV file (or '-' for stdout)")
    p_conflicts.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_conflicts.add_argument("--config_dir", default=".", help="Config dir")
    p_conflicts.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    # Subcommand: person-schedule
    p_person = subparsers.add_parser(
        "person-schedule",
        help="List every session a given person is involved in (as trainer/host/assistant), with date, course and role; omit --name to list everyone"
    )
    p_person.add_argument("--name", default=None, help="Trainer key or full name to look up (omit to list everyone)")
    p_person.add_argument("--email", action="store_true", default=False, help="Email the schedule to the trainer's own address (requires --name)")
    p_person.add_argument("--sheet", default=None, help="Sheet name (default: calendar_sheet_name in config)")
    p_person.add_argument("--roles", default="instructor,host,assistants", help="Comma-separated roles to check (default: instructor,host,assistants)")
    p_person.add_argument("--csv", default=None, help="Export schedule to CSV file (or '-' for stdout)")
    p_person.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")
    p_person.add_argument("--config_dir", default=".", help="Config dir")
    p_person.add_argument("--secrets_dir", default="./secrets", help="Secrets dir")

    args = parser.parse_args()

    # Determine action
    action = args.subcommand or args.action
    if not action:
        if args.to_sheet:
            action = "create-sheet"
        else:
            parser.print_help()
            sys.exit(1)

    # Normalize action name
    action = action.replace("_", "-")

    # Load configuration
    global_config = get_config(args)

    if action == "create-sheet":
        if not getattr(args, 'to_sheet', None):
            print("Error: --to is required for create-sheet action.")
            sys.exit(1)
        action_create_sheet(args, global_config)
    elif action == "sync-to-calendar":
        action_sync_to_calendar(args, global_config)
    elif action == "sync-from-calendar":
        action_sync_from_calendar(args, global_config)
    elif action == "clear-calendar":
        action_clear_calendar(args, global_config)
    elif action in ("summary", "role-summary", "roles-summary"):
        action_summary(args, global_config)
    elif action == "check-conflicts":
        action_check_conflicts(args, global_config)
    elif action == "person-schedule":
        action_person_schedule(args, global_config)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
