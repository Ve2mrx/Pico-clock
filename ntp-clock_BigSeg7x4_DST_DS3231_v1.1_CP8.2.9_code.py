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

import adafruit_ds3231
from adafruit_ht16k33.segments import BigSeg7x4

#  Hardware init
i2c = busio.I2C(board.GP5, board.GP4)

display = BigSeg7x4(i2c, address=(0x71, 0x70))
displayMS = BigSeg7x4(i2c, address=(0x71))
displayLS = BigSeg7x4(i2c, address=(0x70))
display.fill(1)

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False    # On-board LED, used to indicate Wi-Fi is connected

rp_rtc = rtc.RTC()
rtc = adafruit_ds3231.DS3231(i2c)

#  Variable init
#print(type(os.getenv('TIME_OFFSET')))
print("Time offset = ",float(str(os.getenv('TIME_OFFSET', "0.0"))))
time_offset = float(os.getenv('TIME_OFFSET', "0.0"))
ntp_synced = False    # True when sync'd to NTP

print()
print("Connecting to WiFi")

#  connect to your SSID
print("SSID = ", os.getenv('CIRCUITPY_WIFI_SSID'), ", Password = ", os.getenv('CIRCUITPY_WIFI_PASSWORD'))
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print("Connected to WiFi")
led.value = True

pool = socketpool.SocketPool(wifi.radio)

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

#  prints IP address to REPL
print("My IP address is", wifi.radio.ipv4_address)

#  pings Google to test connection
ipv4 = ipaddress.ip_address("8.8.4.4")
print("Ping google.com: %f ms" % (wifi.radio.ping(ipv4)*1000))

#  get NTP time
ntp_server = os.getenv('NTP_SERVER', "ca.pool.ntp.org")
ntp = adafruit_ntp.NTP(pool, server = ntp_server, tz_offset=0)
print("NTP server is '", ntp_server, "'")

def time_ntp_sync():
    global ntp_synced
    
    now_rtc_time = rtc.datetime
    ntp_count = 0
    now_datetime = datetime_2.fromtimestamp(mktime(now_rtc_time))
    #now_datetime = now_rtc_time
    print("RTC0       : ", now_datetime, "Sync'd? ", ntp_synced)
    #print("ntp1       : ")
    
    ntp_start_time = ntp_time = ntp.datetime
    #ntp_start_ts = datetime_2.fromtimestamp(mktime(ntp_start_time)).timestamp()
    
    
    while ntp_synced == False:    
        ntp_time = ntp.datetime
        #ntp_sec = datetime_2.fromtimestamp(mktime(ntp_time)).second
        #print("ntp_start_ts :", ntp_start_ts, " , " , ntp_ts)
        
        if ntp_time > ntp_start_time:
            rtc.datetime = ntp_time
            #rtc.datetime = ntp_time
            #rtc.datetime = ntp_time
            #rtc.datetime = ntp_time
            #rtc.datetime = ntp_time
            
            rp_rtc.datetime = datetime_2.timetuple(datetime_2.fromtimestamp(mktime(ntp_time)) + datetime.timedelta(seconds = -1))
            #rp_rtc.datetime = datetime_2.timetuple(ntp_time_offset)
            
            
            if ntp_time == ntp.datetime:
                #rtc.datetime = ntp_time            
                now_rtc_time = rtc.datetime
                
                ntp_synced = True
                #print("Sync'd? ", ntp_synced)
                
                ntp_datetime = datetime_2.fromtimestamp(mktime(ntp_time))
                now_datetime = datetime_2.fromtimestamp(mktime(now_rtc_time))
                #now_datetime = now_rtc_time
                print("ntp1       : ", ntp_datetime)
                print("RTC DS3231 : ", now_datetime, "Sync'd? ", ntp_synced)
                print("RTC RP2040 : ", datetime.datetime.now())
                print("ntp now    : ", datetime_2.fromtimestamp(mktime(ntp.datetime)))
                
        else:
            ntp_count += 1
            time.sleep(0.05)
            
    print("start: ", ntp_start_time.tm_sec, "now: ", ntp_time.tm_sec)
    print("Count= ", ntp_count, "Time= ", ntp_count * 0.05, "s")

    #ntp_time_datetime = datetime_2.fromtimestamp(mktime(ntp_time))
    #print("ntp : ", datetime_2.fromtimestamp(mktime(ntp.datetime)))
    #now_datetime = datetime.datetime.now()

    #  clear display, we know what the time is!
    display.fill(0)
    return(ntp_synced)

time_ntp_sync()

while True:
    #now_rtc_time = rtc.datetime
    
    #print("DS3231 : ", datetime_2.fromtimestamp(mktime(now_rtc_time)))
    #print("RP2040 : ", datetime_2.fromtimestamp(mktime(rp_rtc.datetime)))
    #print("ntp    : ", datetime_2.fromtimestamp(mktime(ntp.datetime)))
    
    #now_datetime = datetime_2.fromtimestamp(mktime(now_rtc_time))
    #now_datetime = now_rtc_time
    now_datetime = datetime.datetime.now()
    #now_datetime = datetime.time()

    # Apply timezone
    now_datetime = now_datetime + datetime.timedelta(hours = time_offset)
    
    # Check datetime and adjust if DST
    now_adj_time, is_dst = adjust_dst(now_datetime.timetuple())
    #print("now_adj_time : ", now_adj_time)

    #  Convert from struct_time to struct_datetime
    now_adj = datetime_2.fromtimestamp(mktime(now_adj_time))
    
    if is_dst:
        flag_text = "DST"
    else:
        flag_text = "xST"

    #print("now     : ", now_datetime)
    #print("now_adj : ", now_adj, flag_text)
    
    hour = now_adj.hour
    minute = now_adj.minute
    second = now_adj.second
    
    displayMS.print('{0:0>2d}{1:0>2d}'.format(hour,minute))
    displayLS.print('{0:0>2d}  '.format(second))
    #print('{0:0>2d}:{1:0>2d}.{2:0>2d}  '.format(hour,minute,second))
    
    # Toggle colon
    displayMS.colons[0] = displayLS.colons[1] = (second % 2) - 1
    
    # Wait a quarter second (less than 1 second to prevent colon blinking getting in phase with odd/even seconds).
    #time.sleep(0.001)