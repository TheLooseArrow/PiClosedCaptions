#!/usr/bin/python

import vlc
import srt
import serial
import threading, time
import argparse
from datetime import timedelta
from serial.serialutil import Timeout
from cobs import cobs
from pycrc.algorithms import Crc
from CheckSRTEncoding import fix_encoding, replace_newlines, add_style_codes

crc = Crc(width=16, poly=0x1021, reflect_in=False, xor_in=0x1d0f, reflect_out=False, xor_out=0x0000)

def MovieFinished(event, player):
    print("\nEvent reports - finished")
    player.stop()

def read_until_custom(self, expected=b'\r', expected2=b'\a', size=None):
    """\
    Read until an expected sequence is found (line feed by default), the size
    is exceeded or until timeout occurs.
    """
    lenterm = len(expected)
    lenterm2 = len(expected2)
    line = bytearray()
    timeout = Timeout(self._timeout)
    while True:
        c = self.read(1)
        if c:
            #reset timeout if data is incoming
            timeout.restart(self._timeout)
            line += c
            #check for 2 different line terminators
            if (line[-lenterm:] == expected) or (line[-lenterm2:] == expected2):
                break
            if size is not None and len(line) >= size:
                break
        else:
            break
        if timeout.expired():
            break
    return bytes(line)

def SyncTimeStamp(event, player):
    #sync the start time with the media player time
    global start_time
    start_time = time.time() - (player.get_time()/1000)

def StartFirstTimer(event, player, subtitle_generator, subtitles, movie_start):
    global start_time
    start_time = time.time() - movie_start

    print(f"StartTime: {media_player.get_time()}")

    #send the subtitle data 1 second prior to when it will be displayed onscreen
    interval = get_interval(subtitles.start+timedelta(seconds=-1))

    start_timer(interval, subtitles, player, subtitle_generator, SendCaptionData)

def get_time():
    global start_time
    return time.time() - start_time

def get_interval(sub_start):
    return sub_start/timedelta(seconds=1) - get_time()

def start_timer(interval, subtitles, player, subtitle_generator, callback):
    global timer

    if(interval <= 0):
        callback(subtitles, player, subtitle_generator)
    else:
        timer = threading.Timer(interval, callback, args=(subtitles, player, subtitle_generator))
        timer.start()

def stop_timer():
    global timer
    timer.cancel()

def SendCaptionData(subtitles, player, subtitle_generator):
    #add control codes for text styles
    fixed = add_style_codes(subtitles.content)
    #fix the srt encoding to make sure the CC are properly displayed
    fixed = fix_encoding(bytes(fixed, 'utf-8'))
    #Replace newlines with cursor positions for popon captions
    fixed = replace_newlines(fixed)
    checksum = crc.table_driven(fixed)

    encoded = cobs.encode(fixed + checksum.to_bytes(2, 'big'))
    arduino.write(encoded + b'\x00')

    print(subtitles.content)

    data = read_until_custom(arduino, b'\r', b'\a')

    if data == b'\a':
        SendCaptionData(subtitles, player, subtitle_generator)
        return
    elif data == b'\r':
        interval = get_interval(subtitles.start)
        start_timer(interval, subtitles, player, subtitle_generator, DisplayCaption)
    else:
        print("No Response from arduino")

def DisplayCaption(subtitles, player, subtitle_generator):
    displayCaption = b'\x14\x2c\x14\x2c\x14\x2F\x14\x2f'
    checksum = crc.table_driven(displayCaption)
    encoded = cobs.encode(displayCaption + checksum.to_bytes(2, 'big'))
    arduino.write(encoded + b'\x00')
    data = read_until_custom(arduino, b'\r', b'\a')

    if data == b'\a':
        DisplayCaption(subtitles, player, subtitle_generator)
        return
    elif data == b'\r':
        try:
            caption_end_time = subtitles.end
            subtitles = next(subtitle_generator)

            #if the next subtitle is more than a second away, clear the current caption
            if ((subtitles.start  - caption_end_time)/timedelta(seconds=1)) > 1:
                interval = get_interval(caption_end_time)
                start_timer(interval, subtitles, player, subtitle_generator, ClearCaption)
            else:
                #send the subtitle data 1 second prior to when it will be displayed onscreen
                interval = get_interval(subtitles.start + timedelta(seconds=-1))
                start_timer(interval, subtitles, player, subtitle_generator, SendCaptionData)

        except StopIteration:
            print("Done.")
            return

def ClearCaption(subtitles, player, subtitle_generator):
    clearCaption = b'\x14\x2c\x14\x2c'
    checksum = crc.table_driven(clearCaption)
    encoded = cobs.encode(clearCaption + checksum.to_bytes(2, 'big'))
    arduino.write(encoded + b'\x00')

    print("Caption Cleared")

    data = read_until_custom(arduino, b'\r', b'\a')

    if data == b'\a':
        ClearCaption(subtitles, player, subtitle_generator)
        return
    elif data == b'\r':
        #send the subtitle data 1 second prior to when it will be displayed onscreen
        interval = get_interval(subtitles.start + timedelta(seconds=-1))
        start_timer(interval, subtitles, player, subtitle_generator, SendCaptionData)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s","--subfile", default='Subtitle.srt', help="subtitle filename (default: Subtitle.srt)")
    parser.add_argument("-m","--moviefile", default='Movie', help="movie filename (default: Movie)")
    parser.add_argument("-c","--comport", default='/dev/ttyACM0', help="comport for arduino (default: /dev/ttyACM0)")
    parser.add_argument("-t","--starttime", default=0, type=float, help="time in seconds that the movie will start playing")
    return parser.parse_args()
    
#args = get_args(sys.argv[1:])
args = parse_args()

#setup arduino serial port
arduino = serial.Serial(port=args.comport, baudrate=19200, timeout=10)
arduino.read_until(b'b')
print("Begin")
arduino.timeout = 2

#open SRT file
srtfile = open(args.subfile, "r", encoding="utf-8-sig")

# create subtitle generator
subtitle_generator = srt.parse(srtfile)

# get the first subtitle
subtitles = next(subtitle_generator)

# creating vlc media player object
#instance = vlc.Instance("--aout=adummy")
instance = vlc.Instance()
media_player = instance.media_player_new()

# media object
media = instance.media_new_path(args.moviefile)

#start movie at a certain timestamp
movie_start = args.starttime
media.add_option(f'start-time={movie_start}')
#fast forward to the correct subtitle
if(movie_start >= subtitles.end/timedelta(seconds=1)):
    for subtitles in subtitle_generator:
        if(movie_start <= subtitles.end/timedelta(seconds=1)):
            break

#disable VLC player subtitles
media.add_option("no-sub-autodetect-file")

# setting media to the media player
media_player.set_media(media)

events = media_player.event_manager()
events.event_attach(vlc.EventType.MediaPlayerEndReached, MovieFinished, media_player)
events.event_attach(vlc.EventType.MediaPlayerTimeChanged, SyncTimeStamp, media_player)
events.event_attach(vlc.EventType.MediaPlayerPlaying, StartFirstTimer, media_player, subtitle_generator, subtitles, movie_start)
#events.event_attach(vlc.EventType.MediaPlayerForward, FastForward, media_player, subtitle_generator)

# start playing video
media_player.play()

start_time = time.time()

input("Press Enter to stop...")

media_player.stop()
timer.cancel()
srtfile.close()
