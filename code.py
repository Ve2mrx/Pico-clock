# SPDX-FileCopyrightText: 2026 Martin Boissonneault
#
# SPDX-License-Identifier: MIT

"""NTP-synced clock for Raspberry Pi Pico W with dual BigSeg7x4 displays.

Synchronizes time from an NTP server to a DS3231 RTC and the RP2040's
built-in RTC. Displays hours and minutes on one 7-segment display,
seconds on another, with automatic DST adjustment and daily resync.
Configuration is read from settings.toml.
"""

import board
import busio
import digitalio
import microcontroller
import os
import ipaddress
import wifi
import socketpool
import time
from time import mktime
import rtc

import adafruit_ntp
from adafruit_datetime import datetime, timedelta
from cedargrove_dst_adjuster import adjust_dst
import adafruit_ds3231
from adafruit_ht16k33.segments import BigSeg7x4


def init_wifi(led):
    """Connect to WiFi using credentials from settings.toml.

    :param led: DigitalInOut for the on-board LED, set high on success.
    :return: SocketPool for network operations.
    """

    wifi.radio.hostname = 'PicoW-clock'

    print()
    print("Connecting to WiFi")
    print("SSID = ", os.getenv('CIRCUITPY_WIFI_SSID'))
    print(f"hostname= {wifi.radio.hostname}")

    wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'),
                       os.getenv('CIRCUITPY_WIFI_PASSWORD'))

    print("Connected to WiFi")
    led.value = True

    pool = socketpool.SocketPool(wifi.radio)
    return pool


def time_ntp_sync():
    """Synchronize the DS3231 and RP2040 RTCs to NTP time.

    Waits for the NTP second to roll over, then sets both RTCs at the
    boundary for maximum precision. Sets ntp_synced to True on success.

    :return: datetime of the synced time (UTC).
    """
    global ntp_synced

    now_rtc_time = ds_rtc.datetime
    now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
    print("RTC0       : ", now_datetime, "Sync'd? ", ntp_synced)

    ntp_start_time = ntp.datetime

    # Sleep through most of the current second
    time.sleep(0.9)

    # Tight-poll for the second boundary (sub-ms precision)
    ntp_count = 0
    poll_start = time.monotonic()
    while not ntp_synced:
        ntp_time = ntp.datetime

        if ntp_time > ntp_start_time:
            # Second just changed — set DS3231 immediately
            ds_rtc.datetime = ntp_time

            # Compensate for the delay of writing to the DS3231 above
            # so the RP2040 RTC stays in sync with it.
            rp_rtc.datetime = datetime.timetuple(
                datetime.fromtimestamp(mktime(ntp_time)) + timedelta(seconds=-1))

            if ntp_time == ntp.datetime:
                now_rtc_time = ds_rtc.datetime
                ntp_synced = True

                ntp_datetime = datetime.fromtimestamp(mktime(ntp_time))
                now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
                print("ntp1       : ", ntp_datetime)
                print("RTC DS3231 : ", now_datetime, "Sync'd? ", ntp_synced)
                print("RTC RP2040 : ", datetime.now())
                print("ntp now    : ", datetime.fromtimestamp(
                    mktime(ntp.datetime)))

        else:
            ntp_count += 1

    poll_time = time.monotonic() - poll_start
    print("start: ", ntp_start_time.tm_sec, "now: ", ntp_time.tm_sec)
    print("Count= ", ntp_count, "Poll time= ", poll_time, "s")

    return now_datetime


def calcNextSync(datetime_obj: object) -> object:
    """Calculates the next UTC time to sync.

    Reads NTP_SYNC_HOUR and NTP_SYNC_MINUTE from settings.toml.
    If today's sync time has passed, schedules for tomorrow.

    :param datetime_obj: current datetime (UTC).
    :return: next datetime to sync at (UTC).
    """

    sync_hour = int(os.getenv('NTP_SYNC_HOUR', "5"))
    sync_minute = int(os.getenv('NTP_SYNC_MINUTE', "0"))

    timeNextSync = datetime_obj.replace(
        hour=sync_hour, minute=sync_minute, second=0, microsecond=0)

    # If that time has already passed today, schedule for tomorrow
    if datetime_obj >= timeNextSync:
        timeNextSync = timeNextSync + timedelta(days=1)

    return timeNextSync


if __name__ == '__main__':
    # Hardware init
    i2c = busio.I2C(board.GP5, board.GP4)

    display = BigSeg7x4(i2c, address=(0x71, 0x70))
    displayMS = BigSeg7x4(i2c, address=(0x71))
    displayLS = BigSeg7x4(i2c, address=(0x70))
    display.fill(True)

    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    led.value = False

    rp_rtc = rtc.RTC()
    ds_rtc = adafruit_ds3231.DS3231(i2c)

    # Variable init
    time_offset = float(os.getenv('TIME_OFFSET', "0.0"))
    print("Time offset = ", time_offset)
    ntp_synced = False

    now_datetime = datetime.now()

    # Init WiFi
    pool = init_wifi(led)

    print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])
    print("My IP address is", wifi.radio.ipv4_address)

    # Ping to test connection
    ipv4 = ipaddress.ip_address("8.8.4.4")
    ping_result = wifi.radio.ping(ipv4)
    if ping_result is not None:
        print("Ping google.com: %f ms" % (ping_result * 1000))
    else:
        print("Ping google.com: failed")

    # Init NTP
    ntp_server = os.getenv('NTP_SERVER', "ca.pool.ntp.org")
    ntp = adafruit_ntp.NTP(pool, server=ntp_server, tz_offset=0)
    print(f"NTP server is {ntp_server}")

    while True:

        if not ntp_synced:
            display.fill(True)

            # Reconnect WiFi if disconnected
            if not wifi.radio.connected:
                print("WiFi disconnected, reconnecting...")
                led.value = False
                try:
                    wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'),
                                       os.getenv('CIRCUITPY_WIFI_PASSWORD'))
                    led.value = True
                    print("WiFi reconnected")
                except Exception as e:
                    print("WiFi reconnect failed:", e)
                    display.fill(True)
                    time.sleep(1)
                    microcontroller.reset()

            now_datetime = time_ntp_sync()
            timeNextSync = calcNextSync(now_datetime)
            print(f"now= {now_datetime}, next= {timeNextSync}")

            display.fill(False)

        now_datetime = datetime.now()

        # Apply timezone and DST adjustment
        now_datetime_local = now_datetime + timedelta(hours=time_offset)
        now_adj_time, is_dst = adjust_dst(now_datetime_local.timetuple())
        now_adj = datetime.fromtimestamp(mktime(now_adj_time))

        hour = now_adj.hour
        minute = now_adj.minute
        second = now_adj.second

        displayMS.print('{0:0>2d}{1:0>2d}'.format(hour, minute))
        displayLS.print('{0:0>2d}  '.format(second))

        # Toggle colon
        displayMS.colons[0] = displayLS.colons[1] = (second % 2 == 0)

        if now_datetime >= timeNextSync:
            ntp_synced = False
            print("--- Time sync requested!")
