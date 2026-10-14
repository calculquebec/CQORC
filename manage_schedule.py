#!/usr/bin/env python3
import os
import sys
import re
import argparse
import pytz
from datetime import datetime, date, timedelta

import CQORCcalendar
import interfaces.google.GCalInterface as GCalInterface
from common import get_config, get_title

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
    skipped_count = 0
    existing_count = 0

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

        existing_gcal_id = session.get('private_gcal_id')
        if existing_gcal_id and not getattr(args, 'force', False):
            # Check if event still exists on calendar
            try:
                ev = gcal.get_event(existing_gcal_id)
                if ev and ev.get('status') != 'cancelled':
                    if args.verbose:
                        print(f"  Course {course_id} ({code}): already has gcal event {existing_gcal_id}, skipping")
                    existing_count += 1
                    continue
            except Exception:
                pass

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

        if args.dry_run:
            print(f"  [DRY RUN] Would create tentative event for Course {course_id} ({code}):")
            print(f"    Title: {event_title}")
            print(f"    Start: {start_iso} | End: {end_iso}")
            print(f"    Attendees: None (nobody invited)")
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
                if args.verbose or created_count <= 5:
                    print(f"  Created tentative event {event_id} for Course {course_id} ({code}): {start_date}")
            except Exception as e:
                print(f"  Error creating event for Course {course_id} ({code}): {e}")

    if not args.dry_run and created_count > 0:
        print(f"\nWriting updated Google Calendar IDs to sheet '{sheet_name}'...")
        calendar.update_spreadsheet(sheet_name=sheet_name)

    print(f"\nSummary for sync-to-calendar:")
    print(f"  Tentative events created: {created_count}")
    print(f"  Already existed on calendar: {existing_count}")
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
    print(f"Checking for moved events on private Google Calendar for sheet '{sheet_name}'...")

    updated_count = 0
    unchanged_count = 0
    missing_count = 0

    for session in sessions:
        course_id = session.get('course_id')
        code = session.get('code') or ''
        title = session.get('title') or ''
        current_start = session.get('start_date') or ''
        current_end = session.get('end_date') or ''
        gcal_id = session.get('private_gcal_id')

        if not course_id and not title:
            continue

        if not gcal_id:
            if args.verbose:
                print(f"  Course {course_id} ({code}): No private_gcal_id recorded.")
            missing_count += 1
            continue

        try:
            ev = gcal.get_event(gcal_id)
        except Exception as e:
            print(f"  Course {course_id} ({code}): Could not fetch event {gcal_id}: {e}")
            missing_count += 1
            continue

        if not ev or ev.get('status') == 'cancelled':
            if args.verbose:
                print(f"  Course {course_id} ({code}): Event {gcal_id} not found or cancelled on calendar.")
            missing_count += 1
            continue

        gcal_start = ev['start'].get('dateTime') or ev['start'].get('date')
        gcal_end = ev['end'].get('dateTime') or ev['end'].get('date')

        new_start = format_gcal_dt_to_sheet(gcal_start, tz_name)
        new_end = format_gcal_dt_to_sheet(gcal_end, tz_name)

        if new_start != current_start or new_end != current_end:
            print(f"  Course {course_id} ({code} - {title[:30]}): MOVED")
            print(f"    Start: {current_start} -> {new_start}")
            print(f"    End:   {current_end} -> {new_end}")
            session['start_date'] = new_start
            session['end_date'] = new_end
            updated_count += 1
        else:
            if args.verbose:
                print(f"  Course {course_id} ({code}): unchanged ({current_start})")
            unchanged_count += 1

    if updated_count > 0:
        if args.dry_run:
            print(f"\n[DRY RUN] Would update {updated_count} session(s) in sheet '{sheet_name}'.")
        else:
            print(f"\nWriting {updated_count} updated session(s) to sheet '{sheet_name}'...")
            calendar.update_spreadsheet(sheet_name=sheet_name)
            print(f"Successfully updated sheet '{sheet_name}'.")
    else:
        print("\nNo schedule changes detected on Google Calendar.")

    print(f"\nSummary for sync-from-calendar:")
    print(f"  Moved/Updated: {updated_count}")
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
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Manage session training schedules and Google Calendar synchronization."
    )
    # Global options / Top-level fallback flags
    parser.add_argument(
        "--action",
        choices=["create-sheet", "sync-to-calendar", "sync-from-calendar", "clear-calendar"],
        help="Action to execute (create-sheet, sync-to-calendar, sync-from-calendar, clear-calendar)"
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Sheet name to operate on (for calendar actions)"
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
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
