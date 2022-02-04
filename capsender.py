#!/usr/bin/python

import threading, time
import serial
from datetime import timedelta
from serial.serialutil import Timeout
from cobs import cobs
from pycrc.algorithms import Crc
from CheckSRTEncoding import fix_encoding, replace_newlines, add_style_codes

class CaptionSender:
    crc = Crc(width=16, poly=0x1021, reflect_in=False, xor_in=0x1d0f, reflect_out=False, xor_out=0x0000)
    displayCaption = b'\x14\x2c\x14\x2c\x14\x2F\x14\x2f'
    clearCaption = b'\x14\x2c\x14\x2c'
    signature = (b"\x11\x4A\x11\x4A\x17\x23\x17\x23\x17\x23\x17\x23Captions Provided by"
                 b"\x11\x62\x11\x62\x17\x23\x17\x23\x17\x23\x17\x23\x17\x22\x17\x22\x14\x28\x14\x28\x10\x28\x10\x28TheLooseArrow\x11\x34\x11\x34")
    
    def __init__(self, subtitle_generator, comport):
        self.subtitle_generator = subtitle_generator
        #load the first subtitle
        self.subtitles = next(self.subtitle_generator)
        self.open_comport(comport)
        self.caption_timer = None
        self.signature_timer = None
        
    def open_comport(self, comport):
        #setup arduino serial port
        self.arduino = serial.Serial(port=comport, baudrate=19200, timeout=10)
        self.arduino.read_until(b'b')
        print("Begin")
        self.arduino.timeout = 2

    def set_start_time(self, start_time):
        #Set the timestamp of when the movie started 
        self.start_time = start_time

    def get_time(self):
        return time.time() - self.start_time

    def start_timer(self, sub_start, callback):
        
        interval = sub_start/timedelta(seconds=1) - self.get_time()

        if(interval <= 0):
            callback()
        else:
            self.caption_timer = threading.Timer(interval, callback)
            self.caption_timer.start()

    def start_sig_timer(self, sig_start):
        if sig_start > 0:
            interval = sig_start - self.get_time()
            self.signature_timer = threading.Timer(interval, self.send_signature_data)
            self.signature_timer.start()

    def start_first_timer(self):
        #send the subtitle data 1 second prior to when it will be displayed onscreen
        sub_start = self.subtitles.start+timedelta(seconds=-1)

        self.start_timer(sub_start, self.send_caption_data)

    def fast_forward(self, new_time):
        #fast forward to the correct subtitle
        if(new_time >= self.subtitles.end/timedelta(seconds=1)):
            for self.subtitles in self.subtitle_generator:
                if(new_time <= self.subtitles.end/timedelta(seconds=1)):
                    break
            
    def stop_timers(self):
        if self.caption_timer is not None:
            self.caption_timer.cancel()
        if self.signature_timer is not None:
            self.signature_timer.cancel()
            
    def read_until_custom(self, expected=b'\r', expected2=b'\a', size=None):
        """\
        Read until an expected sequence is found (line feed by default), the size
        is exceeded or until timeout occurs.
        """
        lenterm = len(expected)
        lenterm2 = len(expected2)
        line = bytearray()
        timeout = Timeout(self.arduino._timeout)
        while True:
            c = self.arduino.read(1)
            if c:
                #reset timeout if data is incoming
                timeout.restart(self.arduino._timeout)
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

    def send_caption_data(self):
        #add control codes for text styles
        fixed = add_style_codes(self.subtitles.content)
        #fix the srt encoding to make sure the CC are properly displayed
        fixed = fix_encoding(bytes(fixed, 'utf-8'))
        #Replace newlines with cursor positions for popon captions
        fixed = replace_newlines(fixed)
        checksum = self.crc.table_driven(fixed)

        encoded = cobs.encode(fixed + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')

        print(self.subtitles.content)

        data = self.read_until_custom(b'\r', b'\a')

        if data == b'\a':
            self.send_caption_data()
            return
        elif data == b'\r':
            self.start_timer(self.subtitles.start, self.display_caption)
        else:
            print("No Response from arduino")

    def display_caption(self):
        checksum = self.crc.table_driven(self.displayCaption)
        encoded = cobs.encode(self.displayCaption + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')
        data = self.read_until_custom(b'\r', b'\a')

        if data == b'\a':
            self.display_caption()
            return
        elif data == b'\r':
            try:
                caption_end_time = self.subtitles.end
                self.subtitles = next(self.subtitle_generator)

                #if the next subtitle is more than a second away, clear the current caption
                if ((self.subtitles.start  - caption_end_time)/timedelta(seconds=1)) > 1:
                    self.start_timer(caption_end_time, self.clear_caption)
                else:
                    #Next caption is <= 1 second away so send the data immediately
                    self.send_caption_data()

            except StopIteration:
                self.start_timer(caption_end_time, self.clear_last_caption)
                print("Done.")
                return

    def clear_caption(self):
        checksum = self.crc.table_driven(self.clearCaption)
        encoded = cobs.encode(self.clearCaption + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')

        print("Caption Cleared")

        data = self.read_until_custom(b'\r', b'\a')

        if data == b'\a':
            self.clear_caption()
            return
        elif data == b'\r':
            #send the subtitle data 1 second prior to when it will be displayed onscreen
            sub_start = self.subtitles.start + timedelta(seconds=-1)
            self.start_timer(sub_start, self.send_caption_data)
        else:
            print("No Response from arduino")

    def clear_last_caption(self):
        checksum = self.crc.table_driven(self.clearCaption)
        encoded = cobs.encode(self.clearCaption + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')

        print("Caption Cleared")

        data = self.read_until_custom(b'\r', b'\a')

        if data == b'\a':
            self.clear_last_caption()
            return

    def set_signature(self, signature):
        self.signature = signature
        
    def send_signature_data(self):

        checksum = self.crc.table_driven(self.signature)

        encoded = cobs.encode(self.signature + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')

        data = self.read_until_custom(b'\r', b'\a')

        print("Displaying Signature")

        if data == b'\a':
            self.send_signature_data()
            return
        elif data == b'\r':
            self.display_signature()
        else:
            print("No Response from arduino")

    def display_signature(self):
        checksum = self.crc.table_driven(self.displayCaption)
        encoded = cobs.encode(self.displayCaption + checksum.to_bytes(2, 'big'))
        self.arduino.write(encoded + b'\x00')
        data = self.read_until_custom(b'\r', b'\a')

        if data == b'\a':
            self.display_signature()
            return
    
