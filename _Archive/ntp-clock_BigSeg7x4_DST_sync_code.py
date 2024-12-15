# SPDX-FileCopyrightText: 2022 Martin Boissonneault
#
# SPDX-License-Identifier: 

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
#import ntptime

import adafruit_ntp

import adafruit_datetime as datetime
#, adafruit_datetime as timezone, adafruit_datetime as time, adafruit_datetime as date
from adafruit_datetime import datetime as datetime_2, timezone as timezone #, time, date, 

from cedargrove_dst_adjuster import adjust_dst

from adafruit_ht16k33.segments import BigSeg7x4

#  Hardware init
i2c = busio.I2C(board.GP5, board.GP4)
display = BigSeg7x4(i2c, address=(0x71, 0x70))
displayMS = BigSeg7x4(i2c, address=(0x71))
displayLS = BigSeg7x4(i2c, address=(0x70))
display.fill(1)

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False	# On-board LED, used to indicate Wi-Fi is connected

#  Variable init
time_offset = float(os.getenv('TIME_OFFSET'))
ntp_synced = False		# True when sync'd to NTP

print()
print("Connecting to WiFi")

#  connect to your SSID
wifi.radio.connect(os.getenv('WIFI_SSID'), os.getenv('WIFI_PASSWORD'))

print("Connected to WiFi")
led.value = True

pool = socketpool.SocketPool(wifi.radio)

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

#  prints IP address to REPL
print("My IP address is", wifi.radio.ipv4_address)

#  pings Google
ipv4 = ipaddress.ip_address("8.8.4.4")
print("Ping google.com: %f ms" % (wifi.radio.ping(ipv4)*1000))

#  get NTP time
ntp_server = os.getenv('NTP_SERVER')
ntp = adafruit_ntp.NTP(pool, server = ntp_server, tz_offset=0)
print("NTP server is'", ntp_server, "'")

ntp_start_time = ntp.datetime
#print("start : "
while ntp_synced := False:
    ntp_time = ntp.datetime
    if ntp_time > ntp_start_time:
        rtc.RTC().datetime = ntp_time
        ntp_synced = True
    #print(

#  Convert from struct_time to struct_datetime
ntp_datetime = datetime_2.fromtimestamp(mktime(ntp_time))
print("ntp_time     : ", ntp_time)
print("ntp_datetime : ", ntp_datetime)
print("ntp          : {0: >2d}:{1:0>2d}:{2:0>2d}.{3:0>6d}".format(ntp_datetime.hour, ntp_datetime.minute, ntp_datetime.second, ntp_datetime.microsecond))

now_datetime = datetime.datetime.now()
print("fetched : ", now_datetime)

#  clear display, we know what the time is!
display.fill(0)
