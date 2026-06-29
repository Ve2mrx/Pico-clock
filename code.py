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
import struct
import time
from time import mktime
import rtc

from adafruit_datetime import datetime, timedelta
from cedargrove_dst_adjuster import adjust_dst
import adafruit_ds3231
from adafruit_ht16k33.segments import BigSeg7x4

# Seconds from NTP epoch (1900-01-01) to Unix epoch (1970-01-01)
NTP_EPOCH_OFFSET = 2208988800


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


def sntp_query():
    """Query NTP servers with round-trip delay compensation.

    Tries each server in ntp_servers list until one responds.
    Uses the server's transmit timestamp (T3) plus half the
    measured round-trip time to compute accurate UTC.

    :return: (utc_secs, utc_frac, mono_ref) — seconds since Unix epoch,
             fractional second (0.0–1.0), and monotonic time at receive.
    """

    for server in ntp_servers:
        try:
            sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
            sock.settimeout(5)

            packet = bytearray(48)
            packet[0] = 0x23  # LI=0, VN=4, Mode=3 (client)

            mono_before = time.monotonic()
            sock.sendto(packet, (server, 123))

            buf = bytearray(48)
            sock.recvfrom_into(buf)
            mono_after = time.monotonic()
            sock.close()

            # Extract server receive (T2) and transmit (T3) timestamps
            t2_secs = struct.unpack("!I", buf[32:36])[0]
            t2_frac = struct.unpack("!I", buf[36:40])[0]
            t3_secs = struct.unpack("!I", buf[40:44])[0]
            t3_frac = struct.unpack("!I", buf[44:48])[0]

            rtt = mono_after - mono_before
            server_proc = (t3_secs - t2_secs) + (t3_frac - t2_frac) / 0x100000000
            network_delay = (rtt - server_proc) / 2

            # True UTC at receive = T3 + one-way network delay
            utc_secs = t3_secs - NTP_EPOCH_OFFSET
            utc_frac = t3_frac / 0x100000000 + network_delay

            if utc_frac >= 1.0:
                utc_secs += 1
                utc_frac -= 1.0
            elif utc_frac < 0.0:
                utc_secs -= 1
                utc_frac += 1.0

            print(f"SNTP [{server}]: rtt={rtt*1000:.1f}ms, delay={network_delay*1000:.1f}ms, frac={utc_frac:.3f}")

            return utc_secs, utc_frac, mono_after

        except Exception as e:
            print(f"SNTP [{server}]: failed — {e}")
            try:
                sock.close()
            except Exception:
                pass

    raise RuntimeError("All NTP servers unreachable")


def time_ntp_sync():
    """Synchronize the DS3231 and RP2040 RTCs using SNTP.

    Queries the NTP server with round-trip compensation, calculates the
    exact monotonic time of the next second boundary, then sleeps until
    that moment to set both RTCs with sub-ms precision.

    :return: datetime of the synced time (UTC).
    """
    global ntp_synced

    now_rtc_time = ds_rtc.datetime
    now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
    print("RTC0       : ", now_datetime, "Sync'd? ", ntp_synced)

    # Get accurate UTC with round-trip compensation
    utc_secs, utc_frac, mono_ref = sntp_query()

    # Calculate monotonic time of the next second boundary
    mono_at_boundary = mono_ref + (1.0 - utc_frac)
    next_second = utc_secs + 1

    # Pre-compute struct_time for the next second
    # RP2040 RTC reads back 1 second ahead of what is written
    next_tt = datetime.timetuple(datetime.fromtimestamp(next_second - 1))

    # Sleep until close to boundary, then busy-wait for precision
    remaining = mono_at_boundary - time.monotonic()
    if remaining > 0.01:
        time.sleep(remaining - 0.01)

    while time.monotonic() < mono_at_boundary:
        pass

    # Set RTCs at the boundary
    rp_rtc.datetime = next_tt
    ds_rtc.datetime = time.localtime(next_second)

    ntp_synced = True

    now_rtc_time = ds_rtc.datetime
    now_datetime = datetime.fromtimestamp(mktime(now_rtc_time))
    print("RTC DS3231 : ", now_datetime, "Sync'd? ", ntp_synced)
    print("RTC RP2040 : ", datetime.now())

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

    # Seed RP2040 RTC from battery-backed DS3231
    rp_rtc.datetime = ds_rtc.datetime

    # Variable init
    time_offset = float(os.getenv('TIME_OFFSET', "0.0"))
    print("Time offset = ", time_offset)
    ntp_synced = False

    now_datetime = datetime.now()

    # Init WiFi
    pool = init_wifi(led)

    print("My MAC addr:", ":".join("{:02X}".format(i) for i in wifi.radio.mac_address))
    print("My IP address is", wifi.radio.ipv4_address)

    # Ping to test connection
    ipv4 = ipaddress.ip_address("8.8.4.4")
    ping_result = wifi.radio.ping(ipv4)
    if ping_result is not None:
        print("Ping google.com: %f ms" % (ping_result * 1000))
    else:
        print("Ping google.com: failed")

    # Init NTP
    ntp_servers = [s.strip() for s in os.getenv('NTP_SERVERS', "pool.ntp.org").split(",")]
    print(f"NTP servers: {ntp_servers}")

    while True:

        if not ntp_synced:
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
            now_adj_time, is_dst = adjust_dst((now_datetime + timedelta(hours=time_offset)).timetuple())
            tz_label = os.getenv('DAYLIGHT_STRING', 'DST') if is_dst else os.getenv('STANDARD_STRING', 'STD')
            print(f"Local time: {datetime.fromtimestamp(mktime(now_adj_time))} {tz_label}")


        now_datetime = datetime.now()

        # Apply timezone and DST adjustment
        now_datetime_local = now_datetime + timedelta(hours=time_offset)
        now_adj_time, is_dst = adjust_dst(now_datetime_local.timetuple())
        now_adj = datetime.fromtimestamp(mktime(now_adj_time))
        tz_label = os.getenv('DAYLIGHT_STRING', 'DST') if is_dst else os.getenv('STANDARD_STRING', 'STD')

        hour = now_adj.hour
        minute = now_adj.minute
        second = now_adj.second

        displayMS.print('{0:0>2d}{1:0>2d}'.format(hour, minute))
        displayLS.print('{0:0>2d}  '.format(second))

        # Colon: solid ON when unsynced, toggling when synced
        if ntp_synced:
            displayMS.colons[0] = displayLS.colons[1] = (second % 2 == 0)
        else:
            displayMS.colons[0] = displayLS.colons[1] = True

        if now_datetime >= timeNextSync:
            ntp_synced = False
            print("--- Time sync requested!")
