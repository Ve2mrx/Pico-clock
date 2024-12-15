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
import adafruit_datetime as datetime

import adafruit_ntp
import rtc
#import ntptime
from adafruit_ht16k33.segments import Seg7x4

time_offset = float(os.getenv('TIME_OFFSET'))

i2c = busio.I2C(board.GP3, board.GP2)
display = Seg7x4(i2c, address=(0x71, 0x70))
display.fill(1)

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

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

ntp_server = os.getenv('NTP_SERVER')
ntp = adafruit_ntp.NTP(pool, server = ntp_server, tz_offset=0)
print("NTP server is", ntp_server)
rtc.RTC().datetime = ntp.datetime

display.fill(0)

while True:
    #print(ntp.datetime)
    
    now = datetime.datetime.now()
    
    # Apply timezone
    now = now + datetime.timedelta(hours = time_offset)
    
    #print(now)
    
    hour = now.hour
    minute = now.minute
    second = now.second
    
    display.print('{0: >2d}{1:0>2d}.{2:0>2d}  '.format(hour,minute,second))
    #print('{0: >2d}:{1:0>2d}.{2:0>2d}  '.format(hour,minute,second))
    
    # Toggle colon
    display.colon = (second % 2)              # Toggle colon at 1Hz
    # Wait a quarter second (less than 1 second to prevent colon blinking getting in phase with odd/even seconds).
    time.sleep(0.05)