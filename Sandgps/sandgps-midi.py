import logging
import textwrap
import time
import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bin.SSD1306 import SSD1306_128_32 as SSD1306

import smbus2
import RPi.GPIO as GPIO
from time import sleep
import i2cEncoderLibV2
import mido

from gps3.agps3threaded import AGPS3mechanism

def EncoderChange():
    encoder.writeLEDG(100)
    print ('Changed: %d' % (encoder.readCounter32()))
    encoder.writeLEDG(0)

def EncoderPush():
    encoder.writeLEDB(100)
    print ('Encoder Pushed!')
    encoder.writeLEDB(0)

def EncoderDoublePush():
    encoder.writeLEDB(100)
    encoder.writeLEDG(100)
    print ('Encoder Double Push!')
    encoder.writeLEDB(0)
    encoder.writeLEDG(0)

def EncoderMax():
    encoder.writeLEDR(100)
    print ('Encoder max!')
    encoder.writeLEDR(0)

def EncoderMin():
    encoder.writeLEDR(100)
    print ('Encoder min!')
    encoder.writeLEDR(0)

def Encoder_INT():
    encoder.updateStatus()

# RGB Encoder setup 
GPIO.setmode(GPIO.BCM)
bus = smbus2.SMBus(1)
INT_pin = 17
GPIO.setup(INT_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

using_gps = True

encoder = i2cEncoderLibV2.i2cEncoderLibV2(bus, 0x45)

encconfig = (i2cEncoderLibV2.INT_DATA | i2cEncoderLibV2.WRAP_ENABLE | i2cEncoderLibV2.DIRE_RIGHT | i2cEncoderLibV2.IPUP_ENABLE | i2cEncoderLibV2.RMOD_X1 | i2cEncoderLibV2.RGB_ENCODER)
encoder.begin(encconfig)

encoder.writeCounter(0)
encoder.writeMax(35)
encoder.writeMin(-20)
encoder.writeStep(1)
encoder.writeAntibouncingPeriod(8)
encoder.writeDoublePushPeriod(50)
encoder.writeGammaRLED(i2cEncoderLibV2.GAMMA_2)
encoder.writeGammaGLED(i2cEncoderLibV2.GAMMA_2)
encoder.writeGammaBLED(i2cEncoderLibV2.GAMMA_2)

encoder.onChange = EncoderChange
encoder.onButtonPush = EncoderPush
encoder.onButtonDoublePush = EncoderDoublePush
encoder.onMax = EncoderMax
encoder.onMin = EncoderMin

encoder.autoconfigInterrupt()
print ('Board ID code: 0x%X' % (encoder.readIDCode()))
print ('Board Version: 0x%X' % (encoder.readVersion()))

encoder.writeRGBCode(0x640000)
sleep(0.3)
encoder.writeRGBCode(0x006400)
sleep(0.3)
encoder.writeRGBCode(0x000064)
sleep(0.3)
encoder.writeRGBCode(0x00)

agps_thread = AGPS3mechanism()  # Instantiate AGPS3 Mechanisms
agps_thread.stream_data()  # From localhost (), or other hosts, by example, (host='gps.ddns.net')
agps_thread.run_thread()  # Throttle time to sleep after an empty lookup, default 0.2 second, default daemon=True


class Display:
    DEFAULT_BUSNUM = 1
    SCREENSHOT_PATH = "./img/examples/"

    def __init__(self, busnum = None):
        self.logger = logging.getLogger('Display')

        if not isinstance(busnum, int):
            busnum = Display.DEFAULT_BUSNUM

        self.display = SSD1306(busnum)
        self.clear()
        self.width = self.display.width
        self.height = self.display.height
        
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def clear(self):
        self.display.begin()
        self.display.clear()
        self.display.display()

    def prepare(self):
        self.draw.rectangle((0, 0, self.width, self.height), outline = 0, fill = 0)
        
    def drawtext(self,line, text):
        font = ImageFont.truetype("Arial.ttf", 20)
        if line == 1:
            self.draw.text((2, -4), text, font=font, fill=255)
        else:
            self.draw.text((2, 10), text, font=font, fill=255)
    

    def show(self):
        self.draw = ImageDraw.Draw(self.image)
        self.display.image(self.image)
        self.display.display()
        
# GPIO.add_event_detect(INT_pin, GPIO.FALLING, callback=Encoder_INT, bouncetime=10)

on = False
strike_count = int(time.strftime('%H'))
last_time =  int(time.time())

status_str = 'Sandbells'

encoder_colour = 0x000000
top_sec = False
top_min = False
top_hour = False

disp = Display()

channel = 12
velocity = 100
note = 36


def midi_on(channel = channel, velocity = velocity, note = note):
    msg_on = mido.Message(
    'note_on',
    channel = channel,
    velocity = velocity,
    note = note
    )
    outport.send(msg_on)
    
def midi_off(channel = channel, velocity = velocity, note = note):
    msg_off = mido.Message(
    'note_off',
    channel = channel,
    velocity = velocity,
    note = note
    )
    outport.send(msg_off)
    

while True:
    with mido.open_output('QmidiNet:port 0 128:0') as outport:
        if GPIO.input(INT_pin) == False: #
            Encoder_INT() #
            
        current_time = int(time.time())
        current_time = agps_thread.data_stream.time
        
        current_time_hour = current_time[11:13]
        current_time_minute = current_time[14:16]
        current_time_second = current_time[17:19]
        
        
        if current_time != last_time:
            if on:
                if using_gps:
                    encoder_colour = 0x000010
                else:
                    encoder_colour = 0x010000
                midi_on()
            else:
                if using_gps:
                    encoder_colour = 0x101000
                else:
                    encoder_colour = 0x001000
                midi_off()
                
            on = not on
            last_time = current_time
            # print(hex(encoder_colour))
            disp.prepare()
            if using_gps:
                time_str = current_time[11:19]
                status_str = 'gps:'
            else:
                time_str = datetime.datetime.fromtimestamp(last_time).strftime('%H:%M:%S')
            disp.drawtext(1,time_str)
            disp.drawtext(2,status_str)
            # print(time_str)

            if current_time[14:16] == '00':   #time.strftime('%M') == '00':
                if not top_min:
                    strike_count = int(current_time_hour)  # int(time.strftime('%H'))
                    if strike_count > 12:
                        strike_count = strike_count - 12
                    
                    encoder_colour = encoder_colour | 0x484848 # encoder.writeRGBCode(0x006400)
                    print('0 minute ', current_time)
                    print( 'not top_min Strike Count:-', strike_count)
                    top_min = True
                else:
                    strike_count = strike_count - 1 
                    print( 'Else Strike Count:-', strike_count)
                
                if strike_count > 0:
                    grab = time.time()
                    if (grab - int(grab)) > 0.5: 
                        encoder_colour = 0x000000
                        midi_on(note=24)
                    else:
                        encoder_colour = 0xFFFFFF
                        midi_off(note = 24)

                    
            elif current_time_minute == '15':
                if not top_min:
                    encoder_colour = encoder_colour | 0x484800 
                    print('15 minute ', current_time)
                    top_min = True
                    
            elif current_time_minute == '30':
                if not top_min:
                    encoder_colour = encoder_colour | 0x480048 
                    print('30 minute ', current_time)
                    top_min = True
                    
            elif current_time_minute == '45':
                if not top_min:
                    encoder_colour = encoder_colour | 0x004848 
                    print('45 minute ', current_time)
                    top_min = True
            else:
                if current_time_second == '00':
                    if not top_sec:
                        # encoder reset
                        encoder_colour =  0x004800 # encoder.writeRGBCode(0x000064)
                        top_sec = True
                        print('00 second ', current_time)
                else:
                    top_sec = False
                    
                top_min = False
                
                
            if current_time_hour == '00':
                encoder_colour = encoder_colour | 0x480000 # encoder.writeRGBCode(0x640000)
                print('00 hour ', current_time)
            encoder.writeRGBCode(encoder_colour)
            disp.show()
        # print(agps_thread.data_stream.time)

    

