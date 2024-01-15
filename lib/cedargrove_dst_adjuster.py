# SPDX-FileCopyrightText: Copyright (c) 2022 JG for Cedar Grove Maker Studios
#
# SPDX-License-Identifier: MIT
"""
`cedargrove_dst_adjuster`
================================================================================

A CircuitPython helper to adjust North American Standard Time (xST) to Daylight
Saving Time (DST).

* Author(s): JG

Implementation Notes
--------------------
**Hardware:**

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

"""

import time

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/CedarGroveStudios/CircuitPython_DST_Adjuster.git"

# pylint: disable=too-many-return-statements
def _detect_dst(datetime):
    """Determines if the North American Standard Time (xST) input is
    within the Daylight Saving Time (DST) window. Input to this function is
    expressed as a structured time object in Standard Time (xST). The function
    returns ``True`` if the datetime object is within the DST window, ``False``
    if the datetime object is outside of the DST window. The helper cannot
    detect DST for a structured time object that was encoded as DST.

    :param structured_time datetime: The Standard Time structured time
    input value. Can be any structured time value within the specified date
    calculation range of CircuitPython, currently January 1, 2000 00:00:00 to
    January 19, 2038 03:14:07. No default value.
    """

    # Fix weekday and yearday structured time errors
    datetime = time.localtime(time.mktime(datetime))

    # Convert Python time structure from Monday-origin to Sunday-origin.
    weekday = (datetime.tm_wday + 1) % 7

    # Get the date of the previous Sunday or today's date if Sunday.
    prev_sunday_date = datetime.tm_mday - weekday

    """ Test for March window opening threshold: Second Sunday occurs on the 8th
    through 14th of the month at 02:00 Standard Time (xST).
    """
    if datetime.tm_mon == 3:
        if prev_sunday_date <= 7:  # First Sunday of month or before
            return False  # xST
        if prev_sunday_date <= 14:  # Second Sunday of month
            # Determine current DST threshold
            #  year, March, previous Sunday date, 02 hours xST, 00 min, 00 sec
            dst_thresh = time.mktime(
                time.struct_time(
                    (datetime.tm_year, 3, prev_sunday_date, 2, 0, 0, 0, -1, -1)
                )
            )
            if time.mktime(datetime) < dst_thresh:
                return False  # xST
        return True  # DST

    """Test for November window closing threshold: First Sunday occurs on the
    1st through 7th of the month at 01:00 Standard Time (xST) = 02:00 Daylight
    Saving Time (xDT).
    """
    if datetime.tm_mon == 11:
        if prev_sunday_date < 1:  # Before first Sunday of month
            return True  # DST
        if prev_sunday_date <= 7:  # First Sunday of month
            # Determine current xST threshold
            #  year, November, previous Sunday date, 01 hours xDT, 00 min, 00 sec
            xst_thresh = time.mktime(
                time.struct_time(
                    (datetime.tm_year, 11, prev_sunday_date, 1, 0, 0, 0, -1, -1)
                )
            )
            if time.mktime(datetime) < xst_thresh:
                return True  # DST
        return False  # xST

    # Check for Standard Time window
    if datetime.tm_mon < 3 or datetime.tm_mon > 11:  # Dec - Feb: xST
        return False  # xST
    return True  # DST; datetime.tm_mon is Apr - Oct


def adjust_dst(datetime):
    """Converts North American Standard Time (xST) to Daylight Saving Time
    (DST). Input to this function is a structured time object in xST. The
    function returns a structured time object adjusted to a DST value if
    appropriate and a flag indicating the DST adjustment was made. The helper
    cannot correctly detect DST for a structured time object that is encoded as
    DST.

    :param structured_time datetime: The Standard Time structured time
    input value. Can be any structured time value within the specified date
    calculation range of CircuitPython, currently January 1, 2000 00:00:00 to
    January 19, 2038 03:14:07. No default value.
    """

    is_dst = _detect_dst(datetime)  # Determine if datetime is within DST window

    if is_dst:  # If DST, add an hour
        dst_date_time = time.mktime(datetime) + 3600
        return time.localtime(dst_date_time), True
    return datetime, False
