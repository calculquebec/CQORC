#!/usr/bin/env python3
import os
import sys
import re
import argparse
from datetime import datetime, date, timedelta
import CQORCcalendar
from common import get_config

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


def main():
    parser = argparse.ArgumentParser(
        description="Create a new training schedule sheet in Google Spreadsheet from an existing session with adjusted dates."
    )
    parser.add_argument(
        "--from",
        dest="from_sheet",
        default=None,
        help="Source sheet name (e.g. A26). Defaults to calendar_sheet_name in secrets/config.cfg"
    )
    parser.add_argument(
        "--to",
        dest="to_sheet",
        required=True,
        help="Target sheet name to create (e.g. H27)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite target sheet if it already exists"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform a dry run without modifying the Google spreadsheet"
    )
    parser.add_argument(
        "--config_dir",
        default=".",
        help="Directory that holds the configuration files (default: .)"
    )
    parser.add_argument(
        "--secrets_dir",
        default="./secrets",
        help="Directory that holds the secrets files (default: ./secrets)"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print details of all adjusted sessions"
    )
    args = parser.parse_args()

    # Load configuration
    global_config = get_config(args)

    from_sheet = args.from_sheet or global_config['google']['calendar_sheet_name']
    to_sheet = args.to_sheet

    print(f"Managing schedule: {from_sheet} -> {to_sheet}")

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
        # Check if row is empty padding
        if not s.get('course_id') and not s.get('title') and not s.get('code') and not s.get('start_date'):
            continue
        adjusted_sessions.append(adjust_session(s, header, shift))

    print(f"Processed {len(adjusted_sessions)} sessions from '{from_sheet}'.\n")

    # Preview sessions
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
            # Try duplicate_sheet to preserve column widths, fonts, and frozen panes
            calendar.gsheets.duplicate_sheet(calendar.spreadsheet_id, from_sheet, to_sheet)
            calendar.gsheets.clear_values(calendar.spreadsheet_id, "A:Z", to_sheet)
        except Exception as e:
            print(f"Note: Could not duplicate sheet '{from_sheet}' ({e}), falling back to adding a blank sheet...")
            calendar.gsheets.add_sheet(calendar.spreadsheet_id, to_sheet)

    # Set new sessions on calendar and update target sheet
    calendar.set_sessions(adjusted_sessions)
    print(f"Writing {len(adjusted_sessions)} sessions to sheet '{to_sheet}'...")
    calendar.update_spreadsheet(sheet_name=to_sheet)
    print(f"Successfully created and populated schedule in sheet '{to_sheet}'!")


if __name__ == "__main__":
    main()
