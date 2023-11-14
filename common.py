from datetime import datetime
import argparse
ISO_8061_FORMAT = "YYYY-MM-DD[THH:MM:SS[±HH:MM]]"

def to_iso8061(dt, tz=None):
    """
    Returns full long ISO 8061 datetime with timezone.

    eg:
        '2018-09-12' -> '2018-09-12T00:00:00-04:00'
        '2018-09-12T00:00:00+00:30' -> '2018-09-11T19:30:00-04:00'
    """
    if isinstance(dt, datetime):
        return dt.astimezone(tz)
    else:
        return datetime.fromisoformat(dt).astimezone(tz)

def valid_date(d):
    """ Validate date is in ISO 8061 format, otherwise raise. """
    try:
        return to_iso8061(d)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid ISO 8061 date value: {d!r}.")
