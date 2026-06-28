# SPDX-FileCopyrightText: 2024 Martin Boissonneault
#
# SPDX-License-Identifier: MIT

import board
import busio
import digitalio

import os
import ipaddress
import wifi
import socketpool
import time
from time import mktime
import rtc
# import ntptime
import microcontroller

import adafruit_ntp

# import adafruit_datetime as datetime
# , adafruit_datetime as timezone, adafruit_datetime as time, adafruit_datetime as date
from adafruit_datetime import datetime, timedelta  # , timezone , time, date,

from cedargrove_dst_adjuster import adjust_dst

import adafruit_ds3231
from adafruit_ht16k33.segments import BigSeg7x4


def init_wifi(led):
    wifi.radio.hostname = 'PicoW-clock'

    print()
    print("Connecting to WiFi")

    #  connect to your SSID
    print("SSID = ", os.getenv('CIRCUITPY_WIFI_SSID'))
    print(f"hostname= {wifi.radio.hostname}")

    wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'),
                       os.getenv('CIRCUITPY_WIFI_PASSWORD'))

    print("Connected to WiFi")
    led.value = True

    pool = socketpool.SocketPool(wifi.radio)
    return pool


def time_ntp_sync():
    global ntp_synced

    now_rtc_time = ds_rtc.datetime
    now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
    # now_datetime = now_rtc_time
    print("RTC0       : ", now_datetime, "Sync'd? ", ntp_synced)
    # print("ntp1       : ")

    ntp_start_time = ntp.datetime
    # ntp_start_ts = datetime_2.fromtimestamp(mktime(ntp_start_time)).timestamp()

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

            rp_rtc.datetime = datetime.timetuple(
                datetime.fromtimestamp(mktime(ntp_time)) + timedelta(seconds=-1))
            # rp_rtc.datetime = datetime_2.timetuple(ntp_time_offset)

            if ntp_time == ntp.datetime:
                # rtc.datetime = ntp_time
                now_rtc_time = ds_rtc.datetime

                ntp_synced = True
                # print("Sync'd? ", ntp_synced)

                ntp_datetime = datetime.fromtimestamp(mktime(ntp_time))
                now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
                # now_datetime = now_rtc_time
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

    #  clear display, we know what the time is!
    # display.fill(0)
    return now_datetime


def calcNextSync(datetime_obj: object) -> object:
    """
    Calculates the next UTC time to sync

    :param Adafruit_datetime datetime object datetime_obj: initial datetime

    :return Adafruit_datetime datetime object timeNextSync: Next datetime to sync at
    """

    # extract date from datetime obj and set the time to 00:00:00.0
    datetime_date = datetime_obj.replace(
        hour=0, minute=0, second=0, microsecond=0)

    # timeNextSync = datetime_date + timedelta(seconds=15)    # DEBUG

    # Add a day to the datetime
    timeNextSync = datetime_date + timedelta(days=1)

    return timeNextSync


if __name__ == '__main__':
    #  Hardware init
    i2c = busio.I2C(board.GP5, board.GP4)

    display = BigSeg7x4(i2c, address=(0x71, 0x70))
    displayMS = BigSeg7x4(i2c, address=(0x71))
    displayLS = BigSeg7x4(i2c, address=(0x70))
    display.fill(True)

    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    led.value = False    # On-board LED, used to indicate Wi-Fi is connected

    rp_rtc = rtc.RTC()
    ds_rtc = adafruit_ds3231.DS3231(i2c)

    #  Variable init
    # print(type(os.getenv('TIME_OFFSET')))
    print("Time offset = ", float(os.getenv('TIME_OFFSET', "0.0")))
    time_offset = float(os.getenv('TIME_OFFSET', "0.0"))
    ntp_synced = False    # True when sync'd to NTP

    now_datetime = datetime.now()

    # Init WiFi
    pool = init_wifi(led)

    #  prints MAC address to REPL
    print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

    #  prints IP address to REPL
    print("My IP address is", wifi.radio.ipv4_address)

    #  pings Google to test connection
    ipv4 = ipaddress.ip_address("8.8.4.4")
    ping_result = wifi.radio.ping(ipv4)
    if ping_result is not None:
        print("Ping google.com: %f ms" % (ping_result * 1000))
    else:
        print("Ping google.com: failed")

    #  get NTP time
    ntp_server = os.getenv('NTP_SERVER', "ca.pool.ntp.org")
    ntp = adafruit_ntp.NTP(pool, server=ntp_server, tz_offset=0)
    print(f"NTP server is {ntp_server}")

    while True:

        if not ntp_synced:
            #  blank display, we don't know what the time is!
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

            #  clear display, we know what the time is!
            display.fill(False)

        now_datetime = datetime.now()

        # Apply timezone
        now_datetime_local = now_datetime + timedelta(hours=time_offset)

        # Check datetime and adjust if DST
        now_adj_time, is_dst = adjust_dst(now_datetime_local.timetuple())
        # print("now_adj_time : ", now_adj_time)

        #  Convert from struct_time to struct_datetime
        now_adj = datetime.fromtimestamp(mktime(now_adj_time))

        if is_dst:
            flag_text = "DST"
        else:
            flag_text = "xST"

        # print("now     : ", now_datetime)
        # print("now_adj : ", now_adj, flag_text)

        hour = now_adj.hour
        minute = now_adj.minute
        second = now_adj.second

        displayMS.print('{0:0>2d}{1:0>2d}'.format(hour, minute))
        displayLS.print('{0:0>2d}  '.format(second))
        # print('{0:0>2d}:{1:0>2d}.{2:0>2d}  '.format(hour,minute,second))

        # Toggle colon
        displayMS.colons[0] = displayLS.colons[1] = (second % 2 == 0)

        # Wait a quarter second (less than 1 second to prevent colon blinking getting in phase with odd/even seconds).
        # time.sleep(0.001)

        if now_datetime >= timeNextSync:
            ntp_synced = False
            print("--- Time sync requested!")
